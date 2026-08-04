#!/usr/bin/env python3
"""Validate the matched native Arm stock-quant service frontier."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e2_ingest import elapsed_seconds
    from experiments.e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from experiments.e5j_ingest import validate_process_cpu
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e9a_ingest import expected_server_argv
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e2_ingest import elapsed_seconds
    from e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from e5j_ingest import validate_process_cpu
    from e7a_ingest import validate_runtime_closure
    from e9a_ingest import expected_server_argv


def validate_frozen_inputs(
    evidence: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E11b"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E11b contract differs")
    for key, value in contract["inputs"].items():
        if not key.endswith("_path"):
            continue
        name = key.removesuffix("_path")
        source = root / value
        retained = evidence / "frozen-inputs" / value
        expected = contract["inputs"][f"{name}_sha256"]
        if sha256_file(source) != expected or sha256_file(retained) != expected:
            raise ValueError(f"E11b input differs for {name}")
    return contract


def validate_build(evidence: Path, contract: dict[str, Any]) -> dict[str, Any]:
    runtime = contract["runtime"]
    source = load_object(evidence / "source.json")
    if source != runtime["source"]:
        raise ValueError("E11b source identity differs")
    for patch in runtime["source"]["patches"]:
        if sha256_file(evidence / "patches" / Path(patch["path"]).name) != patch[
            "sha256"
        ]:
            raise ValueError(f"E11b retained patch differs: {patch['path']}")
    if (
        sha256_file(evidence / "source-diff.patch")
        != runtime["source"]["source_diff_sha256"]
        or (evidence / "patched-files.txt").read_text().splitlines()
        != runtime["source"]["changed_files"]
    ):
        raise ValueError("E11b source diff differs")
    build = evidence / "build"
    configure = load_object(build / "configure-command.json")
    if configure.get("cmake_arguments") != runtime["build"]["cmake_arguments"]:
        raise ValueError("E11b configure command differs")
    cache_lines = (build / "CMakeCache.txt").read_text(errors="replace").splitlines()
    for argument in runtime["build"]["cmake_arguments"]:
        if not argument.startswith("-D") or "=" not in argument:
            continue
        name, value = argument[2:].split("=", 1)
        if value in {"ON", "OFF"} and not any(
            line.startswith(f"{name}:") and line.endswith(f"={value}")
            for line in cache_lines
        ):
            raise ValueError(f"E11b CMake cache differs for {name}")
    version = (build / "server-version.txt").read_text(errors="replace").strip()
    if runtime["source"]["commit"][:9] not in version:
        raise ValueError("E11b server version differs")
    process = parse_time_output((build / "build-time.log").read_text())
    process["elapsed_seconds"] = elapsed_seconds(process["elapsed"])
    if process["elapsed_seconds"] <= 0:
        raise ValueError("E11b build duration differs")
    closure = validate_runtime_closure(build / "runtime-closure.json")
    dependencies = sorted(
        {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
    )
    if set(contract["acceptance"]["forbidden_dynamic_dependency_basenames"]) & set(
        dependencies
    ):
        raise ValueError("E11b build retains a forbidden dependency")
    return {
        "configure_command": configure,
        "cmake_cache_sha256": sha256_file(build / "CMakeCache.txt"),
        "server_version": version,
        "build_process": process,
        "runtime_closure": closure,
        "dynamic_dependency_basenames": dependencies,
    }


def probe_contract(contract: dict[str, Any], candidate: str) -> dict[str, Any]:
    return {
        **contract,
        "selected": {
            "candidate": candidate,
            "reference_correct": 0,
            "reference_total": contract["request"]["measured_tasks"],
            "reference_accuracy": 0.0,
        },
    }


def validate_recipe(
    recipe: dict[str, Any], contract: dict[str, Any], candidate: str, role: str
) -> None:
    runtime = contract["runtime"]
    model = contract["models"][candidate]
    server = recipe.get("server_path")
    model_path = recipe.get("model", {}).get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E11b"
        or recipe.get("candidate") != candidate
        or recipe.get("role") != role
        or recipe.get("source") != runtime["source"]
        or recipe.get("build") != runtime["build"]
        or recipe.get("service") != runtime["service"]
        or recipe.get("model", {}).get("sha256") != model["sha256"]
        or recipe.get("model", {}).get("size_bytes") != model["size_bytes"]
        or not isinstance(server, str)
        or not server.endswith("/bin/llama-server")
        or not isinstance(model_path, str)
        or not model_path.endswith(".gguf")
        or runtime["source"]["commit"][:9] not in recipe.get("server_version", "")
    ):
        raise ValueError(f"E11b recipe differs for {candidate} {role}")
    if recipe.get("argv") != expected_server_argv(
        server,
        model_path,
        candidate=candidate,
        profile_name=runtime["profile_name"],
    ):
        raise ValueError(f"E11b argv differs for {candidate} {role}")


def validate_cell(
    path: Path,
    *,
    contract: dict[str, Any],
    candidate: str,
    role: str,
    repetition: int,
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    recipe = load_object(path / "recipe.json")
    validate_recipe(recipe, contract, candidate, role)
    timed = (path / "server-time.log").read_text(errors="replace")
    commands = [line for line in timed.splitlines() if "Command being timed:" in line]
    if len(commands) != 1 or not all(arg in commands[0] for arg in recipe["argv"]):
        raise ValueError(f"E11b timed command differs for {path.name}")
    readiness = load_object(path / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not math.isfinite(ready_ms)
        or ready_ms < 0
    ):
        raise ValueError(f"E11b readiness differs for {path.name}")
    config = {
        "client_concurrency": contract["request"]["client_concurrency"],
        "prompt_cache": True,
        "warmup_slot_ids": contract["runtime"]["service"]["warmup_slot_ids"],
    }
    raw_probe = load_object(path / "probe.json")
    probe = validate_probe(
        raw_probe,
        configuration=role,
        repetition=repetition,
        config=config,
        contract=probe_contract(contract, candidate),
        tasks=tasks,
        references=references,
        require_selected_quality=False,
    )
    cached = [case.get("cached_tokens") for case in raw_probe["cases"]]
    if any(
        type(value) is not int
        or value < contract["acceptance"]["minimum_cached_tokens_per_request"]
        for value in cached
    ):
        raise ValueError(f"E11b cache mechanism differs for {path.name}")
    process_cpu = validate_process_cpu(
        raw_probe,
        cell_dir=path,
        measured_requests=contract["request"]["measured_tasks"],
    )
    process = parse_time_output(timed)
    shell_exit = int((path / "server-shell-exit.txt").read_text())
    slots = load_object(path / "slots.json")
    if (
        shell_exit not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process.get("maximum_rss_kib") is None
        or not isinstance(slots, list)
        or len(slots) != contract["runtime"]["service"]["server_parallel_slots"]
        or "llamacpp:" not in (path / "metrics.txt").read_text()
    ):
        raise ValueError(f"E11b process evidence differs for {path.name}")
    return (
        {
            "candidate": candidate,
            "role": role,
            "repetition": repetition,
            "ready_ms": float(ready_ms),
            "probe": probe,
            "server_process_cpu": process_cpu,
            "process": process,
            "server_shell_exit_status": shell_exit,
            "slots_observed": len(slots),
        },
        raw_probe["cases"],
    )


def summarize_model(
    cells: list[dict[str, Any]], samples: list[dict[str, Any]]
) -> dict[str, Any]:
    repetitions = sorted(cell["repetition"] for cell in cells)
    prediction_maps = [
        {
            case["id"]: case["predicted"]
            for case in samples
            if case["repetition"] == repetition
        }
        for repetition in repetitions
    ]
    return {
        "quality": {
            "correct_per_repetition": [cell["probe"]["correct"] for cell in cells],
            "accuracy_per_repetition": [
                cell["probe"]["accuracy"] for cell in cells
            ],
            "reference_prediction_mismatches_per_repetition": [
                cell["probe"]["reference_prediction_mismatches"] for cell in cells
            ],
            "predictions_stable_between_repetitions": all(
                item == prediction_maps[0] for item in prediction_maps[1:]
            ),
            "predictions": prediction_maps[0],
        },
        "repetitions": cells,
        "samples": samples,
        "requests_per_second": summarize(
            [cell["probe"]["requests_per_second"] for cell in cells]
        ),
        "http_ms": summarize([float(case["http_ms"]) for case in samples]),
        "encode_ms": summarize([float(case["encode_ms"]) for case in samples]),
        "decode_ms": summarize([float(case["decode_ms"]) for case in samples]),
        "cached_tokens": summarize(
            [float(case["cached_tokens"]) for case in samples]
        ),
        "server_cpu_seconds_per_request": summarize(
            [
                float(cell["server_process_cpu"]["seconds_per_request"])
                for cell in cells
            ]
        ),
        "average_server_cores_used": summarize(
            [
                float(cell["server_process_cpu"]["average_cores_used"])
                for cell in cells
            ]
        ),
        "ready_ms": summarize([cell["ready_ms"] for cell in cells]),
        "maximum_rss_kib": summarize(
            [float(cell["process"]["maximum_rss_kib"]) for cell in cells]
        ),
    }


def ratios(candidate: dict[str, Any], anchor: dict[str, Any]) -> dict[str, float]:
    return {
        "throughput": candidate["requests_per_second"]["median"]
        / anchor["requests_per_second"]["median"],
        "median_http_latency": candidate["http_ms"]["median"]
        / anchor["http_ms"]["median"],
        "p95_http_latency": candidate["http_ms"]["p95"]
        / anchor["http_ms"]["p95"],
        "cpu_seconds_per_request": candidate["server_cpu_seconds_per_request"][
            "median"
        ]
        / anchor["server_cpu_seconds_per_request"]["median"],
        "maximum_rss": candidate["maximum_rss_kib"]["max"]
        / anchor["maximum_rss_kib"]["max"],
        "readiness": candidate["ready_ms"]["median"]
        / anchor["ready_ms"]["median"],
    }


def point_valid(performance: dict[str, Any], contract: dict[str, Any]) -> bool:
    return bool(
        performance["quality"]["predictions_stable_between_repetitions"]
        and performance["requests_per_second"]["coefficient_of_variation"]
        <= contract["acceptance"]["maximum_throughput_coefficient_of_variation"]
        and performance["ready_ms"]["max"]
        <= contract["acceptance"]["maximum_ready_ms"]
        and performance["maximum_rss_kib"]["max"]
        <= contract["acceptance"]["maximum_process_rss_kib"]
    )


def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    maximize = [
        *left["quality_coordinates"].keys(),
        "throughput",
    ]
    left_max = {**left["quality_coordinates"], "throughput": left["throughput"]}
    right_max = {
        **right["quality_coordinates"],
        "throughput": right["throughput"],
    }
    minimize = (
        "model_size_bytes",
        "median_http_ms",
        "p95_http_ms",
        "cpu_seconds_per_request",
        "maximum_rss_kib",
        "readiness_ms",
    )
    no_worse = all(left_max[name] >= right_max[name] for name in maximize) and all(
        left[name] <= right[name] for name in minimize
    )
    strict = any(left_max[name] > right_max[name] for name in maximize) or any(
        left[name] < right[name] for name in minimize
    )
    return no_worse and strict


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_frozen_inputs(evidence, contract_path, root)
    build = validate_build(evidence, contract)
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["reference_manifest_path"]),
        contract["anchor"],
    )
    platform = {
        **parse_lscpu((evidence / "lscpu.txt").read_text()),
        "uname": (evidence / "uname.txt").read_text().strip(),
        "compiler": (evidence / "compiler.txt").read_text().strip(),
        "environment": load_object(evidence / "environment.json"),
    }
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E11b platform differs")

    pairs = []
    all_anchor_cells: list[dict[str, Any]] = []
    all_anchor_samples: list[dict[str, Any]] = []
    points: list[dict[str, Any]] = []
    for candidate in contract["candidate_order"]:
        cells_by_role: dict[str, list[dict[str, Any]]] = {
            "anchor": [],
            "candidate": [],
        }
        samples_by_role: dict[str, list[dict[str, Any]]] = {
            "anchor": [],
            "candidate": [],
        }
        pair_root = evidence / "pairs" / candidate
        for index, item in enumerate(contract["execution"]["pair_order"], start=1):
            role = item["role"]
            repetition = item["repetition"]
            model = contract["anchor"] if role == "anchor" else candidate
            cell, cases = validate_cell(
                pair_root / f"{index:02d}-{role}-r{repetition}",
                contract=contract,
                candidate=model,
                role=role,
                repetition=repetition,
                tasks=tasks,
                references=references,
            )
            cells_by_role[role].append(cell)
            samples_by_role[role].extend(
                {"repetition": repetition, **case} for case in cases
            )
        anchor = summarize_model(cells_by_role["anchor"], samples_by_role["anchor"])
        measured = summarize_model(
            cells_by_role["candidate"], samples_by_role["candidate"]
        )
        all_anchor_cells.extend(cells_by_role["anchor"])
        all_anchor_samples.extend(samples_by_role["anchor"])
        valid = point_valid(measured, contract) and point_valid(anchor, contract)
        pair = {
            "candidate": candidate,
            "anchor": anchor,
            "candidate_performance": measured,
            "ratios": ratios(measured, anchor),
            "validity_passed": valid,
        }
        pairs.append(pair)
        model = contract["models"][candidate]
        points.append(
            {
                "candidate": candidate,
                "validity_passed": valid,
                "quality_coordinates": model["quality_coordinates"],
                "model_size_bytes": model["size_bytes"],
                "throughput": measured["requests_per_second"]["median"],
                "median_http_ms": measured["http_ms"]["median"],
                "p95_http_ms": measured["http_ms"]["p95"],
                "cpu_seconds_per_request": measured[
                    "server_cpu_seconds_per_request"
                ]["median"],
                "maximum_rss_kib": measured["maximum_rss_kib"]["max"],
                "readiness_ms": measured["ready_ms"]["median"],
                "service": measured,
            }
        )

    anchor_performance = summarize_model(all_anchor_cells, all_anchor_samples)
    anchor_model = contract["models"][contract["anchor"]]
    anchor_point = {
        "candidate": contract["anchor"],
        "validity_passed": point_valid(anchor_performance, contract),
        "quality_coordinates": anchor_model["quality_coordinates"],
        "model_size_bytes": anchor_model["size_bytes"],
        "throughput": anchor_performance["requests_per_second"]["median"],
        "median_http_ms": anchor_performance["http_ms"]["median"],
        "p95_http_ms": anchor_performance["http_ms"]["p95"],
        "cpu_seconds_per_request": anchor_performance[
            "server_cpu_seconds_per_request"
        ]["median"],
        "maximum_rss_kib": anchor_performance["maximum_rss_kib"]["max"],
        "readiness_ms": anchor_performance["ready_ms"]["median"],
        "service": anchor_performance,
    }
    points.insert(0, anchor_point)
    valid_points = [point for point in points if point["validity_passed"]]
    frontier = [
        point["candidate"]
        for point in valid_points
        if not any(
            dominates(other, point)
            for other in valid_points
            if other["candidate"] != point["candidate"]
        )
    ]
    confirmation = [name for name in frontier if name != contract["anchor"]]
    provenance = load_object(evidence / "provenance.json")
    if provenance.get("experiment_id") != "E11b":
        raise ValueError("E11b provenance differs")
    return {
        "schema_version": 1,
        "experiment_id": "E11b",
        "status": "valid_stock_quant_service_frontier",
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "build": build,
        "prerequisite": contract["prerequisite"],
        "pairs": pairs,
        "points": points,
        "service_frontier": frontier,
        "sealed_confirmation_candidates": confirmation,
        "validation": {
            "native_arm64": True,
            "all_pairs_same_job": True,
            "exact_e7c_source_build_service": True,
            "fresh_process_per_cell": True,
            "reverse_balanced_four_repetitions_per_model": True,
            "all_raw_answers_retained": True,
            "measured_window_process_cpu_validated": True,
            "binary_and_dependency_closure_hashed": True,
            "weighted_score_used": False,
            "original_30_task_admission_contract_rewritten": False,
        },
        "decision": {
            "product_promotion_made": False,
            "sealed_e11c_confirmation_required": True,
            "sealed_confirmation_candidates": confirmation,
        },
        "provenance": provenance,
        "claim_boundary": contract["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_summary(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": summary["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
