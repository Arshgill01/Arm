#!/usr/bin/env python3
"""Validate the focused repacked FFN gate/up activation-reuse experiment."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e2_ingest import elapsed_seconds
    from experiments.e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
    )
    from experiments.e7a_ingest import (
        summarize_service_performance,
        validate_cell,
        validate_runtime_closure,
    )
    from experiments.e20a_ingest import parse_node_timing
    from experiments.e20c_freeze import INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e2_ingest import elapsed_seconds
    from e5b_ingest import load_object, load_tasks, reference_predictions, sha256_file
    from e7a_ingest import (
        summarize_service_performance,
        validate_cell,
        validate_runtime_closure,
    )
    from e20a_ingest import parse_node_timing
    from e20c_freeze import INPUT_PATHS


FFN_NAME = re.compile(r"^ffn_(gate|up)-(\d+)$")


def validate_inputs(evidence: Path, root: Path, contract: dict[str, Any]) -> None:
    for name, relative in INPUT_PATHS.items():
        expected_path = contract["inputs"][f"{name}_path"]
        expected_sha = contract["inputs"][f"{name}_sha256"]
        if expected_path != relative.as_posix():
            raise ValueError(f"E20c {name} input path differs")
        for path in (root / relative, evidence / "frozen-inputs" / relative):
            if sha256_file(path) != expected_sha:
                raise ValueError(f"E20c {name} input hash differs")


def validate_source_and_build(
    evidence: Path, contract: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime = contract["runtime"]
    source = load_object(evidence / "source.json")
    if source != {
        "commit": runtime["commit"],
        "tag": runtime["tag"],
        "patches_applied": [item["name"] for item in runtime["patches"]],
    }:
        raise ValueError("E20c source proof differs")
    if (
        sha256_file(evidence / "source-diff.patch")
        != runtime["source_diff_sha256"]
        or (evidence / "patched-files.txt").read_text().splitlines()
        != runtime["changed_files"]
    ):
        raise ValueError("E20c patched source differs")

    build_dir = evidence / "build"
    cache = set(
        (build_dir / "CMakeCache.txt").read_text(errors="replace").splitlines()
    )
    if not set(contract["build"]["required_cmake_cache_entries"]).issubset(cache):
        raise ValueError("E20c CMake cache differs")
    commands = (build_dir / "build-commands.txt").read_text(errors="replace")
    if not commands.strip() or "llama-server" not in commands or "llama-bench" not in commands:
        raise ValueError("E20c build command proof differs")
    server_version = (build_dir / "server-version.txt").read_text(errors="replace")
    if runtime["commit"][:9] not in server_version:
        raise ValueError("E20c server version differs")
    process = parse_time_output((build_dir / "build-time.log").read_text())
    process["elapsed_seconds"] = elapsed_seconds(process["elapsed"])
    if process["exit_status"] != 0 or process["elapsed_seconds"] <= 0:
        raise ValueError("E20c build process differs")
    symbols = set((build_dir / "environment-symbols.txt").read_text().splitlines())
    if symbols != {
        "GGML_CPU_NODE_TIMING",
        "GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION",
    }:
        raise ValueError("E20c runtime toggle symbols differ")
    closure = validate_runtime_closure(build_dir / "runtime-closure.json")
    return source, {
        "server_version": server_version.strip(),
        "build_process": process,
        "runtime_closure": closure,
    }


def expected_preflight_argv(
    observed: list[str], evidence: Path, contract: dict[str, Any]
) -> list[str]:
    if not observed or not observed[0].endswith("/bin/llama-bench"):
        raise ValueError("E20c preflight benchmark binary differs")
    model = (evidence / "model-sha256.txt").read_text().split()[1]
    replacements = {"BENCH_PATH": observed[0], "MODEL_PATH": model}
    return [
        replacements.get(value, value)
        for value in contract["mechanism_preflight"]["benchmark_argv"]
    ]


def validate_ffn_records(
    records: list[dict[str, Any]], profile: str, contract: dict[str, Any]
) -> dict[int, dict[str, dict[str, Any]]]:
    by_layer: dict[int, dict[str, dict[str, Any]]] = {}
    for record in records:
        match = FFN_NAME.fullmatch(record["name"])
        if match is None:
            continue
        role, layer_text = match.groups()
        layer = int(layer_text)
        if role in by_layer.setdefault(layer, {}):
            raise ValueError(f"E20c {profile} repeats FFN {role}-{layer}")
        if (
            record["op"] != "MUL_MAT"
            or record["src0"] != f"blk.{layer}.ffn_{role}.weight"
            or record["src1"] != f"ffn_norm-{layer}"
            or record["ne"][0] != 9216
            or record["ne"][2:] != [1, 1]
        ):
            raise ValueError(f"E20c {profile} FFN record differs")
        by_layer[layer][role] = record

    expected_layers = set(contract["mechanism_preflight"]["required_layers"])
    if set(by_layer) != expected_layers:
        raise ValueError(f"E20c {profile} layer coverage differs")
    if profile == "reuse_off":
        if any(
            set(items) != {"gate", "up"}
            or items["gate"]["fused_nodes"] != 0
            or items["up"]["fused_nodes"] != 0
            or items["gate"]["ne"] != items["up"]["ne"]
            for items in by_layer.values()
        ):
            raise ValueError("E20c control FFN mechanism differs")
    elif profile == "reuse_on":
        if any(
            set(items) != {"gate"} or items["gate"]["fused_nodes"] != 1
            for items in by_layer.values()
        ):
            raise ValueError("E20c candidate FFN mechanism differs")
    else:
        raise ValueError("unknown E20c preflight profile")
    return by_layer


def validate_preflight(
    evidence: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    validated: dict[str, Any] = {}
    record_maps: dict[str, dict[int, dict[str, dict[str, Any]]]] = {}
    for profile in ("reuse_off", "reuse_on"):
        directory = evidence / "preflight" / profile
        command = load_object(directory / "command.json")
        environment = {
            "GGML_CPU_NODE_TIMING": "1",
            "GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION": (
                "0" if profile == "reuse_off" else "1"
            ),
        }
        argv = command.get("argv")
        if (
            not isinstance(argv, list)
            or command
            != {"argv": expected_preflight_argv(argv, evidence, contract),
                "environment": environment,
                "profile": profile}
        ):
            raise ValueError(f"E20c {profile} preflight command differs")
        process = parse_time_output((directory / "process-time.log").read_text())
        if process["exit_status"] != 0:
            raise ValueError(f"E20c {profile} preflight process failed")
        lines = [
            line
            for line in (directory / "result.jsonl").read_text().splitlines()
            if line
        ]
        if len(lines) != 1:
            raise ValueError(f"E20c {profile} result count differs")
        result = json.loads(lines[0])
        if (
            result.get("n_prompt") != 512
            or result.get("n_gen") != 0
            or result.get("n_threads") != 4
            or result.get("n_batch") != 1024
            or result.get("n_ubatch") != 512
            or contract["runtime"]["commit"][:9]
            not in str(result.get("build_commit", ""))
        ):
            raise ValueError(f"E20c {profile} benchmark result differs")
        records = parse_node_timing(directory / "stderr.log")
        record_maps[profile] = validate_ffn_records(records, profile, contract)
        validated[profile] = {
            "process": process,
            "result_sha256": sha256_file(directory / "result.jsonl"),
            "stderr_sha256": sha256_file(directory / "stderr.log"),
            "timing_record_count": len(records),
            "ffn_record_count": sum(len(items) for items in record_maps[profile].values()),
            "fused_ffn_pair_count": sum(
                items["gate"]["fused_nodes"] for items in record_maps[profile].values()
            ),
        }

    for layer in contract["mechanism_preflight"]["required_layers"]:
        control = record_maps["reuse_off"][layer]
        candidate = record_maps["reuse_on"][layer]
        if control["gate"]["ne"] != candidate["gate"]["ne"]:
            raise ValueError(f"E20c layer {layer} preflight shapes differ")
    if (
        validated["reuse_off"]["ffn_record_count"]
        != contract["mechanism_preflight"]["control_expected_separate_ffn_nodes"]
        or validated["reuse_off"]["fused_ffn_pair_count"] != 0
        or validated["reuse_on"]["ffn_record_count"]
        != contract["mechanism_preflight"]["candidate_expected_fused_ffn_pairs"]
        or validated["reuse_on"]["fused_ffn_pair_count"]
        != contract["mechanism_preflight"]["candidate_expected_fused_ffn_pairs"]
    ):
        raise ValueError("E20c mechanism count proof differs")
    return validated


def validate_service_cell(
    directory: Path,
    profile: str,
    repetition: int,
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> dict[str, Any]:
    recipe = load_object(directory / "recipe.json")
    expected_environment = contract["build"]["profiles"][profile]["environment"]
    if recipe.get("environment") != expected_environment:
        raise ValueError(f"E20c {directory.name} recipe environment differs")
    result = validate_cell(
        directory, profile, repetition, contract, tasks, references
    )
    timed = (directory / "server-time.log").read_text(errors="replace")
    required = [
        f"GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION={expected_environment['GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION']}",
        "GGML_CPU_NODE_TIMING=0",
    ]
    if any(value not in timed for value in required):
        raise ValueError(f"E20c {directory.name} timed environment differs")
    if parse_node_timing(directory / "server.stderr.log"):
        raise ValueError(f"E20c {directory.name} enabled diagnostic timing")
    return result


def evaluate_hypothesis(
    performance: dict[str, Any], build: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    acceptance = contract["acceptance"]
    baseline = performance[contract["execution"]["baseline_profile"]]
    candidate = performance[contract["execution"]["candidate_profile"]]
    positive = (
        baseline["requests_per_second"]["median"],
        baseline["http_ms"]["median"],
        baseline["http_ms"]["p95"],
        baseline["server_cpu_seconds_per_request"]["median"],
        baseline["ready_ms"]["median"],
        baseline["maximum_rss_kib"]["max"],
        build["runtime_closure"]["total_size_bytes"],
    )
    if min(positive) <= 0:
        raise ValueError("E20c baseline contains a non-positive metric")
    ratios = {
        "throughput_ratio": candidate["requests_per_second"]["median"]
        / baseline["requests_per_second"]["median"],
        "median_http_latency_ratio": candidate["http_ms"]["median"]
        / baseline["http_ms"]["median"],
        "p95_http_latency_ratio": candidate["http_ms"]["p95"]
        / baseline["http_ms"]["p95"],
        "cpu_seconds_per_request_ratio": candidate[
            "server_cpu_seconds_per_request"
        ]["median"]
        / baseline["server_cpu_seconds_per_request"]["median"],
        "ready_time_ratio": candidate["ready_ms"]["median"]
        / baseline["ready_ms"]["median"],
        "candidate_rss_ratio": candidate["maximum_rss_kib"]["max"]
        / baseline["maximum_rss_kib"]["max"],
        "runtime_closure_ratio": 1.0,
        "candidate_throughput_cv": candidate["requests_per_second"][
            "coefficient_of_variation"
        ],
    }
    gates = {
        "quality_passed": candidate["quality"]["exact_selected_predictions"],
        "throughput_passed": ratios["throughput_ratio"]
        >= acceptance["minimum_throughput_ratio"],
        "median_latency_passed": ratios["median_http_latency_ratio"]
        <= acceptance["maximum_median_http_latency_ratio"],
        "p95_latency_passed": ratios["p95_http_latency_ratio"]
        <= acceptance["maximum_p95_http_latency_ratio"],
        "cpu_time_passed": ratios["cpu_seconds_per_request_ratio"]
        <= acceptance["maximum_cpu_seconds_per_request_ratio"],
        "readiness_passed": ratios["ready_time_ratio"]
        <= acceptance["maximum_ready_time_ratio"],
        "rss_passed": ratios["candidate_rss_ratio"]
        <= acceptance["maximum_candidate_rss_ratio"],
        "runtime_closure_passed": ratios["runtime_closure_ratio"]
        <= acceptance["maximum_runtime_closure_ratio"],
        "scheduler_dispersion_passed": ratios["candidate_throughput_cv"]
        <= acceptance["maximum_candidate_throughput_cv"],
    }
    passed = all(gates.values())
    return {
        "passed": passed,
        "selected_profile": (
            contract["execution"]["candidate_profile"]
            if passed
            else contract["execution"]["baseline_profile"]
        ),
        **gates,
        **ratios,
        "weighted_score_used": False,
    }


def validate_safety_preflight(
    evidence: Path,
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> dict[str, Any]:
    specification = contract["safety_preflight"]
    profile = specification["profile"]
    repetition = specification["repetition"]
    relative = Path(specification["directory"])
    if (
        profile != contract["execution"]["candidate_profile"]
        or repetition != 7
        or relative.is_absolute()
        or relative.parts != ("cells", "safety-reuse_on-r7")
        or specification.get("must_complete_before_measurement") is not True
        or specification.get("timings_are_diagnostic_not_performance_evidence")
        is not True
    ):
        raise ValueError("E20c safety-preflight contract differs")
    cell = validate_service_cell(
        evidence / relative,
        profile,
        repetition,
        contract,
        tasks,
        references,
    )
    probe = cell["probe"]
    if (
        probe["correct"] != specification["required_correct"]
        or probe["total"] != specification["required_total"]
        or probe["reference_prediction_mismatches"]
        != specification["required_reference_prediction_mismatches"]
        or probe["failures"] != specification["required_request_failures"]
    ):
        raise ValueError("E20c candidate failed the frozen safety preflight")
    return {
        **cell,
        "completed_before_measurement": True,
        "excluded_from_performance_summary": True,
        "timings_are_diagnostic_not_performance_evidence": True,
    }


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E20c":
        raise ValueError("invalid E20c contract")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E20c")
    validate_inputs(evidence, root, contract)
    source, build = validate_source_and_build(evidence, contract)
    preflight = validate_preflight(evidence, contract)

    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    selected_manifest = load_object(root / contract["inputs"]["manifest_path"])
    candidate = contract["selected"]["candidate"]
    references = reference_predictions(selected_manifest, candidate)
    correct = sum(references[item["id"]] == item["answer"] for item in tasks)
    if (
        len(tasks) != contract["selected"]["reference_total"]
        or correct != contract["selected"]["reference_correct"]
        or set(references) != {item["id"] for item in tasks}
    ):
        raise ValueError("E20c selected quality reference differs")
    safety_preflight = validate_safety_preflight(
        evidence, contract, tasks, references
    )

    execution = contract["execution"]
    baseline = execution["baseline_profile"]
    candidate_profile = execution["candidate_profile"]
    expected_pairs = {
        (profile, repetition)
        for profile in (baseline, candidate_profile)
        for repetition in range(1, execution["repetitions_per_profile"] + 1)
    }
    order = execution["order"]
    if (
        len(order) != len(expected_pairs)
        or {(item.get("profile"), item.get("repetition")) for item in order}
        != expected_pairs
    ):
        raise ValueError("E20c execution order differs")
    provenance = load_object(evidence / "provenance.json")
    if provenance.get("experiment_id") != "E20c" or (
        provenance.get("baseline_profile"), provenance.get("candidate_profile")
    ) != (baseline, candidate_profile):
        raise ValueError("E20c provenance differs")

    cells: list[dict[str, Any]] = []
    paths: dict[tuple[str, int], Path] = {}
    for index, item in enumerate(order, 1):
        profile = item["profile"]
        repetition = item["repetition"]
        directory = evidence / "cells" / f"{index:02d}-{profile}-r{repetition}"
        paths[(profile, repetition)] = directory
        cells.append(
            validate_service_cell(
                directory, profile, repetition, contract, tasks, references
            )
        )
    performance, maximum_prompt_tokens = summarize_service_performance(
        cells, paths, (baseline, candidate_profile), correct
    )
    if not performance[baseline]["quality"]["exact_selected_predictions"]:
        raise ValueError("E20c control failed selected quality")
    hypothesis = evaluate_hypothesis(performance, build, contract)
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E20c",
        "status": (
            "valid_guarded_repack_pair_reuse_win"
            if hypothesis["passed"]
            else "valid_guarded_repack_pair_reuse_no_win"
        ),
        "scope": (
            "Exact patched b10216 guarded repack-backend FFN gate/up "
            "activation reuse"
        ),
        "source": {
            "artifact_name": f"e20c-repack-pair-{run_id}-{provenance['github_run_attempt']}",
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "artifact_retention_days": 90,
            "runtime_proof": source,
        },
        "contract": contract,
        "provenance": provenance,
        "platform": {
            **parse_lscpu((evidence / "lscpu.txt").read_text()),
            "uname": (evidence / "uname.txt").read_text().strip(),
            "python": (evidence / "python-version.txt").read_text().strip(),
            "compiler": (evidence / "compiler.txt").read_text().strip(),
        },
        "selection": {
            "candidate": candidate,
            "correct": correct,
            "total": len(tasks),
            "accuracy": correct / len(tasks),
            "baseline_profile": baseline,
            "candidate_profile": candidate_profile,
            "selected_profile": hypothesis["selected_profile"],
        },
        "validation": {
            "all_input_hashes_match": True,
            "exact_model_verified": True,
            "exact_patch_series_verified": True,
            "single_binary_for_both_profiles": True,
            "control_separate_ffn_nodes_verified": True,
            "candidate_fused_ffn_pairs_verified": True,
            "candidate_full_service_safety_preflight_passed": True,
            "safety_preflight_excluded_from_performance_summary": True,
            "diagnostic_timer_disabled_during_service_measurement": True,
            "transitive_runtime_closure_hashed": True,
            "fresh_server_per_cell": True,
            "measured_window_process_cpu_validated": True,
            "quality_drift_treated_as_rejection": True,
            "optimization_claim_allowed": hypothesis["passed"],
            "automatic_product_promotion_allowed": False,
            "energy_claim_allowed": False,
            "claim_scope": contract["claim_boundary"],
        },
        "mechanism_preflight": preflight,
        "safety_preflight": safety_preflight,
        "maximum_observed_prompt_tokens": maximum_prompt_tokens,
        "build": build,
        "performance": performance,
        "hypothesis": hypothesis,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
