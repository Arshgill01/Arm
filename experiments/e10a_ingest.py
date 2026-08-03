#!/usr/bin/env python3
"""Validate E10a native Arm cache-divergence calibration evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
    )
    from experiments.e9a_ingest import expected_server_argv
    from experiments.e9c_ingest import (
        validate_process_cpu,
        validate_source_and_build,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import load_object, load_tasks, reference_predictions, sha256_file
    from e9a_ingest import expected_server_argv
    from e9c_ingest import validate_process_cpu, validate_source_and_build


LETTERS = ("A", "B", "C", "D")
ARTIFACT_INPUTS = {
    "selected_manifest": "selected-manifest.json",
    "models": "models-manifest.json",
    "tasks": "tasks-manifest.json",
    "e9a_contract": "e9a-contract.json",
    "e9c_manifest": "e9c-manifest.json",
}


def jensen_shannon(left: dict[str, float], right: dict[str, float]) -> float:
    if set(left) != set(right) or not left:
        raise ValueError("candidate distributions use different support")
    midpoint = {key: (left[key] + right[key]) / 2 for key in left}

    def divergence(source: dict[str, float]) -> float:
        return sum(
            probability * math.log(probability / midpoint[key])
            for key, probability in source.items()
            if probability > 0
        )

    return (divergence(left) + divergence(right)) / 2


def pair_metrics(cache_off: dict[str, Any], cache_on: dict[str, Any]) -> dict[str, Any]:
    if cache_off["prompt_sha256"] != cache_on["prompt_sha256"]:
        raise ValueError("paired cache requests use different prompt tokens")
    left = cache_off["candidate_probabilities"]
    right = cache_on["candidate_probabilities"]
    left_top2 = {item["candidate"] for item in cache_off["candidate_ranking"][:2]}
    right_top2 = {item["candidate"] for item in cache_on["candidate_ranking"][:2]}
    return {
        "index": cache_off["index"],
        "task_id": cache_off["task_id"],
        "prefix_marker": cache_off["prefix_marker"],
        "prompt_sha256": cache_off["prompt_sha256"],
        "cache_off_prediction": cache_off["prediction"],
        "cache_on_prediction": cache_on["prediction"],
        "semantic_drift": cache_off["prediction"] != cache_on["prediction"],
        "cache_off_reference_match": cache_off["reference_match"],
        "cache_on_reference_match": cache_on["reference_match"],
        "cache_off_top1_margin": cache_off["top1_margin"],
        "cache_on_top1_margin": cache_on["top1_margin"],
        "jensen_shannon_nats": jensen_shannon(left, right),
        "maximum_absolute_probability_delta": max(
            abs(left[candidate] - right[candidate]) for candidate in LETTERS
        ),
        "top2_set_overlap": len(left_top2 & right_top2) / len(left_top2 | right_top2),
        "cache_off_candidate_probabilities": left,
        "cache_on_candidate_probabilities": right,
    }


def separation_summary(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    drifted = [pair for pair in pairs if pair["semantic_drift"]]
    stable = [pair for pair in pairs if not pair["semantic_drift"]]
    fingerprint_labels: dict[str, set[bool]] = {}
    for pair in pairs:
        fingerprint = (
            f"p{pair['prefix_cardinality']}:l{pair['shared_prefix_tokens']}:"
            f"{pair['prompt_sha256']}"
        )
        fingerprint_labels.setdefault(fingerprint, set()).add(pair["semantic_drift"])
    repeated_labels_stable = all(
        len(labels) == 1 for labels in fingerprint_labels.values()
    )

    margin_separable = False
    margin_interval = None
    if drifted and stable:
        maximum_drift_margin = max(pair["cache_on_top1_margin"] for pair in drifted)
        minimum_stable_margin = min(pair["cache_on_top1_margin"] for pair in stable)
        margin_separable = maximum_drift_margin < minimum_stable_margin
        margin_interval = {
            "maximum_drifted_cache_margin": maximum_drift_margin,
            "minimum_stable_cache_margin": minimum_stable_margin,
            "strict_gap": minimum_stable_margin - maximum_drift_margin,
            "interpretation": (
                "A future cache-only guard may fall back when cached margin is at "
                "or below a separately frozen threshold inside this open interval."
            ),
        }

    divergence_separable = False
    divergence_interval = None
    if drifted and stable:
        minimum_drift_divergence = min(pair["jensen_shannon_nats"] for pair in drifted)
        maximum_stable_divergence = max(pair["jensen_shannon_nats"] for pair in stable)
        divergence_separable = maximum_stable_divergence < minimum_drift_divergence
        divergence_interval = {
            "maximum_stable_js_nats": maximum_stable_divergence,
            "minimum_drifted_js_nats": minimum_drift_divergence,
            "strict_gap": minimum_drift_divergence - maximum_stable_divergence,
            "interpretation": (
                "Pair divergence is diagnostic only because it requires an uncached "
                "comparison and is not a cache-only serving signal."
            ),
        }

    return {
        "paired_requests": len(pairs),
        "semantic_drift_pairs": len(drifted),
        "stable_pairs": len(stable),
        "unique_prompt_fingerprints": len(fingerprint_labels),
        "repeated_drift_labels_stable": repeated_labels_stable,
        "cached_top1_margin_separable": margin_separable,
        "cached_top1_margin_interval": margin_interval,
        "paired_divergence_separable": divergence_separable,
        "paired_divergence_interval": divergence_interval,
        "drifted_request_shape_fingerprints": sorted(
            {
                (
                    f"p{pair['prefix_cardinality']}:l{pair['shared_prefix_tokens']}:"
                    f"{pair['prompt_sha256']}"
                )
                for pair in drifted
            }
        ),
    }


def validate_recipe(recipe: dict[str, Any], contract: dict[str, Any]) -> None:
    model = recipe.get("model", {})
    server = recipe.get("server_path")
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E10a"
        or recipe.get("profile_name") != "e7c_final"
        or recipe.get("source") != contract["service"]
        or recipe.get("service") != contract["service"]
        or model.get("sha256") != contract["selected"]["model_sha256"]
        or model.get("size_bytes") != contract["selected"]["model_size_bytes"]
        or not isinstance(server, str)
        or not server.endswith("/bin/llama-server")
        or not isinstance(model_path, str)
        or not model_path.endswith(".gguf")
        or contract["service"]["source_commit"][:9]
        not in recipe.get("server_version", "")
    ):
        raise ValueError("E10a recipe differs from the frozen E7c service")
    expected = expected_server_argv(
        server,
        model_path,
        candidate=contract["selected"]["candidate"],
        profile_name="e7c_final",
    )
    if recipe.get("argv") != expected:
        raise ValueError("E10a server argv differs from E7c")


def validate_distribution(case: dict[str, Any]) -> None:
    probabilities = case.get("candidate_probabilities")
    ranking = case.get("candidate_ranking")
    raw_mass = case.get("raw_candidate_probability_mass")
    discarded = case.get("discarded_top_probability_entries")
    if (
        not isinstance(probabilities, dict)
        or set(probabilities) != set(LETTERS)
        or any(
            not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            for value in probabilities.values()
        )
        or not math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-5)
        or not isinstance(ranking, list)
        or len(ranking) != len(LETTERS)
        or not isinstance(raw_mass, (int, float))
        or not math.isfinite(raw_mass)
        or not 0 < raw_mass <= 1.00001
        or type(discarded) is not int
        or discarded < 0
    ):
        raise ValueError("E10a candidate distribution is invalid")
    expected = [
        {"candidate": candidate, "probability": probability}
        for candidate, probability in sorted(
            probabilities.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    if ranking != expected or case.get("prediction") != expected[0]["candidate"]:
        raise ValueError("E10a candidate ranking differs from probabilities")
    margin = expected[0]["probability"] - expected[1]["probability"]
    if not math.isclose(case.get("top1_margin", -1), margin, rel_tol=1e-12):
        raise ValueError("E10a top-1 margin differs from probabilities")


def validate_case(
    case: dict[str, Any],
    *,
    index: int,
    task_id: str,
    marker: str,
    marker_index: int,
    reference: str,
    maximum_prompt_tokens: int,
) -> None:
    if (
        case.get("index") != index
        or case.get("task_id") != task_id
        or case.get("prefix_marker") != marker
        or case.get("prefix_marker_index") != marker_index
        or case.get("reference_prediction") != reference
        or type(case.get("prompt_tokens")) is not int
        or not 0 < case["prompt_tokens"] <= maximum_prompt_tokens
        or not isinstance(case.get("prompt_sha256"), str)
        or len(case["prompt_sha256"]) != 64
        or case.get("http_status") != 200
        or case.get("error") is not None
        or case.get("sampled_prediction") not in LETTERS
        or not isinstance(case.get("sampled_tokens"), list)
        or len(case["sampled_tokens"]) != 1
        or case.get("generated_tokens") != 1
    ):
        raise ValueError("E10a case identity or grammar output differs")
    validate_distribution(case)
    if case.get("reference_match") is not (case["prediction"] == reference):
        raise ValueError("E10a reference flag differs")
    for name in (
        "http_ms",
        "encode_ms",
        "decode_ms",
        "cached_tokens",
        "evaluated_prompt_tokens",
        "response_tokens_cached",
        "response_tokens_evaluated",
    ):
        value = case.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"E10a case has invalid {name}")


def validate_cell(
    cell_dir: Path,
    *,
    contract: dict[str, Any],
    point_index: int,
    cell_index: int,
    cardinality: int,
    shared_tokens: int,
    cache_prompt: bool,
    repetition: int,
    references: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    recipe = load_object(cell_dir / "recipe.json")
    validate_recipe(recipe, contract)
    timed = (cell_dir / "server-time.log").read_text(errors="replace")
    commands = [line for line in timed.splitlines() if "Command being timed:" in line]
    if len(commands) != 1 or not all(
        argument in commands[0] for argument in recipe["argv"]
    ):
        raise ValueError(f"{cell_dir.name} timed command differs from its recipe")
    readiness = load_object(cell_dir / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not math.isfinite(ready_ms)
        or not 0 <= ready_ms <= contract["validity"]["maximum_ready_ms"]
    ):
        raise ValueError(f"{cell_dir.name} readiness evidence is invalid")

    probe = load_object(cell_dir / "probe.json")
    parameters = probe.get("parameters", {})
    workload = contract["workload"]
    expected_parameters = {
        "prefix_cardinality": cardinality,
        "shared_prefix_tokens": shared_tokens,
        "cache_prompt": cache_prompt,
        "repetition": repetition,
        "measured_requests": len(workload["task_ids"]),
        "client_concurrency": workload["client_concurrency"],
        "seed": workload["seed"],
        "candidate_scoring": contract["candidate_scoring"],
    }
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E10a"
        or any(
            parameters.get(name) != value for name, value in expected_parameters.items()
        )
        or type(parameters.get("server_pid")) is not int
        or parameters["server_pid"] <= 0
    ):
        raise ValueError(f"{cell_dir.name} probe parameters differ")
    pid = int((cell_dir / "server-pid.txt").read_text().strip())
    if parameters["server_pid"] != pid:
        raise ValueError(f"{cell_dir.name} server PID binding differs")

    construction = contract["prompt_construction"]
    expected_repetitions = construction["native_common_filler_repetitions"]
    prefix = probe.get("prefix_recipe", {})
    prefix_ids = prefix.get("common_prefix_token_ids")
    if (
        prefix.get("target_shared_prefix_tokens") != shared_tokens
        or prefix.get("common_filler_repetitions") != expected_repetitions
        or not isinstance(prefix_ids, list)
        or len(prefix_ids) != shared_tokens
        or any(type(token) is not int for token in prefix_ids)
        or prefix.get("variant_marker_token_ids")
        != construction["variant_marker_token_ids"]
        or prefix.get("common_prefix_sha256")
        != hashlib.sha256(
            json.dumps(prefix_ids, separators=(",", ":")).encode()
        ).hexdigest()
    ):
        raise ValueError(f"{cell_dir.name} prefix construction differs")

    active_markers = construction["variant_markers"][:cardinality]
    warmups = probe.get("warmups")
    if not isinstance(warmups, list) or len(warmups) != cardinality:
        raise ValueError(f"{cell_dir.name} warmup count differs")
    for index, warmup in enumerate(warmups):
        validate_case(
            warmup,
            index=index,
            task_id=workload["warmup_task_id"],
            marker=active_markers[index],
            marker_index=index,
            reference=references[workload["warmup_task_id"]],
            maximum_prompt_tokens=construction["maximum_prompt_tokens"],
        )

    cases = probe.get("cases")
    if not isinstance(cases, list) or len(cases) != len(workload["task_ids"]):
        raise ValueError(f"{cell_dir.name} measured case count differs")
    for index, (case, task_id) in enumerate(zip(cases, workload["task_ids"])):
        marker_index = index % cardinality
        validate_case(
            case,
            index=index,
            task_id=task_id,
            marker=active_markers[marker_index],
            marker_index=marker_index,
            reference=references[task_id],
            maximum_prompt_tokens=construction["maximum_prompt_tokens"],
        )

    result = probe.get("result", {})
    elapsed = result.get("elapsed_seconds")
    requests_per_second = result.get("requests_per_second")
    if (
        not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed <= 0
        or not isinstance(requests_per_second, (int, float))
        or not math.isclose(requests_per_second, len(cases) / elapsed, rel_tol=1e-12)
    ):
        raise ValueError(f"{cell_dir.name} throughput evidence differs")
    process_cpu = validate_process_cpu(
        probe.get("process_cpu"),
        server_pid=pid,
        requests=len(cases),
        elapsed_seconds=elapsed,
    )
    process = parse_time_output(timed)
    shell_exit = int((cell_dir / "server-shell-exit.txt").read_text().strip())
    slots = json.loads((cell_dir / "slots.json").read_text())
    if (
        shell_exit not in contract["validity"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"] > contract["validity"]["maximum_process_rss_kib"]
        or not isinstance(slots, list)
        or len(slots) != contract["service"]["server_parallel_slots"]
        or "llamacpp:" not in (cell_dir / "metrics.txt").read_text()
    ):
        raise ValueError(f"{cell_dir.name} process evidence differs")

    failures = sum(
        case.get("http_status") != 200 or case.get("error") is not None
        for case in cases
    )
    mismatches = sum(
        case.get("prediction") != case["reference_prediction"] for case in cases
    )
    if (
        result.get("failures") != failures
        or result.get("reference_prediction_mismatches") != mismatches
    ):
        raise ValueError(f"{cell_dir.name} result counts differ from raw cases")
    return (
        {
            "point_index": point_index,
            "cell_index": cell_index,
            "prefix_cardinality": cardinality,
            "shared_prefix_tokens": shared_tokens,
            "cache_prompt": cache_prompt,
            "repetition": repetition,
            "ready_ms": float(ready_ms),
            "requests_per_second": float(requests_per_second),
            "server_process_cpu": process_cpu,
            "process": process,
            "server_shell_exit_status": shell_exit,
            "failures": failures,
            "reference_prediction_mismatches": mismatches,
        },
        cases,
    )


def summarize_point(
    *,
    cardinality: int,
    shared_tokens: int,
    cells: list[dict[str, Any]],
    samples: dict[tuple[bool, int], list[dict[str, Any]]],
) -> dict[str, Any]:
    performance: dict[str, Any] = {}
    for cache_prompt, name in ((False, "cache_off"), (True, "cache_on")):
        state_cells = [cell for cell in cells if cell["cache_prompt"] is cache_prompt]
        raw = [
            case
            for repetition in (1, 2)
            for case in samples[(cache_prompt, repetition)]
        ]
        performance[name] = {
            "cache_prompt": cache_prompt,
            "repetitions": state_cells,
            "requests_per_second": summarize(
                [cell["requests_per_second"] for cell in state_cells]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in raw]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in raw]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in raw]),
            "cached_tokens": summarize([float(case["cached_tokens"]) for case in raw]),
            "evaluated_prompt_tokens": summarize(
                [float(case["evaluated_prompt_tokens"]) for case in raw]
            ),
            "server_cpu_seconds_per_request": summarize(
                [
                    cell["server_process_cpu"]["seconds_per_request"]
                    for cell in state_cells
                ]
            ),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in state_cells]
            ),
            "reference_prediction_mismatches": sum(
                case["prediction"] != case["reference_prediction"] for case in raw
            ),
            "candidate_accuracy": sum(case["reference_match"] for case in raw)
            / len(raw),
        }

    pairs = []
    for repetition in (1, 2):
        off = samples[(False, repetition)]
        on = samples[(True, repetition)]
        for left, right in zip(off, on):
            pair = pair_metrics(left, right)
            pair["repetition"] = repetition
            pair["prefix_cardinality"] = cardinality
            pair["shared_prefix_tokens"] = shared_tokens
            pairs.append(pair)
    off = performance["cache_off"]
    on = performance["cache_on"]
    return {
        "prefix_cardinality": cardinality,
        "shared_prefix_tokens": shared_tokens,
        "performance": performance,
        "ratios": {
            "throughput": on["requests_per_second"]["median"]
            / off["requests_per_second"]["median"],
            "p95_http_latency": on["http_ms"]["p95"] / off["http_ms"]["p95"],
            "cpu_seconds_per_request": on["server_cpu_seconds_per_request"]["median"]
            / off["server_cpu_seconds_per_request"]["median"],
        },
        "calibration": separation_summary(pairs),
        "pairs": pairs,
    }


def build_manifest(
    evidence_dir: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E10a":
        raise ValueError("unsupported E10a contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E10a contract")
    for name, artifact_name in ARTIFACT_INPUTS.items():
        source = root / contract["inputs"][f"{name}_path"]
        expected = contract["inputs"][f"{name}_sha256"]
        if (
            sha256_file(source) != expected
            or sha256_file(evidence_dir / artifact_name) != expected
        ):
            raise ValueError(f"E10a {name} input differs")
    for name in ("probe", "ingest"):
        if (
            sha256_file(root / contract["inputs"][f"{name}_path"])
            != contract["inputs"][f"{name}_sha256"]
        ):
            raise ValueError(f"E10a {name} code differs")
    for patch in load_object(evidence_dir / "e9a-contract.json")["profiles"][
        "e7c_final"
    ]["source"]["patches"]:
        if sha256_file(root / patch["path"]) != patch["sha256"]:
            raise ValueError(f"E10a patch differs: {patch['path']}")

    build = validate_source_and_build(evidence_dir, contract)
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["selected_manifest_path"]),
        contract["selected"]["candidate"],
    )
    task_ids = {task["id"] for task in tasks}
    workload = contract["workload"]
    if not set(workload["task_ids"] + [workload["warmup_task_id"]]).issubset(task_ids):
        raise ValueError("E10a workload contains an unknown task")

    point_order = contract["execution"]["point_order"]
    cell_order = contract["execution"]["within_point_order"]
    if (
        len(point_order) * len(cell_order)
        != contract["execution"]["total_fresh_process_cells"]
    ):
        raise ValueError("E10a cell count differs from its execution contract")
    points = []
    all_cells = []
    for point_index, point in enumerate(point_order, 1):
        cardinality = point["prefix_cardinality"]
        shared_tokens = point["shared_prefix_tokens"]
        cells = []
        samples: dict[tuple[bool, int], list[dict[str, Any]]] = {}
        for within_index, spec in enumerate(cell_order, 1):
            cache = spec["cache_prompt"]
            repetition = spec["repetition"]
            global_index = (point_index - 1) * len(cell_order) + within_index
            name = (
                f"{global_index:02d}-p{cardinality}-l{shared_tokens}-"
                f"cache_{'on' if cache else 'off'}-r{repetition}"
            )
            cell, raw = validate_cell(
                evidence_dir / "cells" / name,
                contract=contract,
                point_index=point_index,
                cell_index=global_index,
                cardinality=cardinality,
                shared_tokens=shared_tokens,
                cache_prompt=cache,
                repetition=repetition,
                references=references,
            )
            cells.append(cell)
            all_cells.append(cell)
            samples[(cache, repetition)] = raw
        points.append(
            summarize_point(
                cardinality=cardinality,
                shared_tokens=shared_tokens,
                cells=cells,
                samples=samples,
            )
        )

    all_pairs = [pair for point in points for pair in point["pairs"]]
    aggregate = separation_summary(all_pairs)
    zero_failures = sum(cell["failures"] for cell in all_cells) == 0
    cache_mechanism = all(
        point["performance"]["cache_off"]["cached_tokens"]["max"]
        == contract["validity"]["required_cache_off_tokens_per_request"]
        and point["performance"]["cache_on"]["cached_tokens"]["min"]
        >= point["shared_prefix_tokens"]
        for point in points
    )
    proceed = (
        zero_failures
        and cache_mechanism
        and aggregate["semantic_drift_pairs"] > 0
        and aggregate["repeated_drift_labels_stable"]
        and aggregate["cached_top1_margin_separable"]
    )
    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E10a":
        raise ValueError("E10a provenance differs")
    platform = {
        **parse_lscpu((evidence_dir / "lscpu.txt").read_text()),
        "uname": (evidence_dir / "uname.txt").read_text().strip(),
        "python": (evidence_dir / "python-version.txt").read_text().strip(),
        "compiler": (evidence_dir / "compiler.txt").read_text().strip(),
        "environment": load_object(evidence_dir / "environment.json"),
    }
    if platform["architecture"] != contract["validity"]["required_architecture"]:
        raise ValueError("E10a did not run on native Arm64")
    run_id = str(provenance["github_run_id"])
    status = (
        "valid_cache_margin_separable"
        if proceed
        else "valid_cache_calibration_no_drift"
        if zero_failures and cache_mechanism and aggregate["semantic_drift_pairs"] == 0
        else "valid_cache_margin_not_separable"
        if zero_failures and cache_mechanism
        else "invalid_cache_calibration"
    )
    return {
        "schema_version": 1,
        "experiment_id": "E10a",
        "status": status,
        "scope": contract["scope"],
        "source": {
            "artifact_name": (
                f"e10a-cache-divergence-{run_id}-{provenance['github_run_attempt']}"
            ),
            "github_run_url": (
                f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}"
            ),
            "artifact_retention_days": 90,
        },
        "contract": contract,
        "provenance": provenance,
        "platform": platform,
        "selection": {
            "candidate": contract["selected"]["candidate"],
            "model_sha256": contract["selected"]["model_sha256"],
            "model_size_bytes": contract["selected"]["model_size_bytes"],
        },
        "build": build,
        "validation": {
            "all_input_hashes_match": True,
            "native_arm64_same_job": True,
            "exact_e7c_service": True,
            "fresh_server_per_cell": True,
            "bounded_predeclared_calibration": True,
            "raw_candidate_probabilities_retained": True,
            "zero_request_failures": zero_failures,
            "cache_mechanism_observed": cache_mechanism,
            "guard_threshold_selected": False,
            "holdout_observed": False,
            "energy_claim_allowed": False,
            "performance_promotion_allowed": False,
            "claim_scope": contract["claim_boundary"],
        },
        "aggregate_calibration": aggregate,
        "proceed_to_frozen_holdout": proceed,
        "points": points,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
