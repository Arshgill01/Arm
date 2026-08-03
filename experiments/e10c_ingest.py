#!/usr/bin/env python3
"""Validate E10c native Arm fixed-candidate scoring evidence."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e9a_ingest import expected_server_argv
    from experiments.e9c_ingest import validate_process_cpu
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure
    from e9a_ingest import expected_server_argv
    from e9c_ingest import validate_process_cpu


ARTIFACT_INPUTS = {
    "e9a_contract": "e9a-contract.json",
    "e10b_contract": "e10b-contract.json",
    "e10b_manifest": "e10b-manifest.json",
    "models": "models-manifest.json",
    "tasks": "tasks-manifest.json",
    "scorer_patch": "patches/0005-server-score-fixed-candidates.patch",
}
CHANGED_FILES = [
    "common/reasoning-budget.cpp",
    "ggml/src/ggml-cpu/CMakeLists.txt",
    "ggml/src/ggml-cpu/arch/arm/quants.c",
    "tests/test-reasoning-budget.cpp",
    "tools/server/README.md",
    "tools/server/server-context.cpp",
    "tools/server/server-context.h",
    "tools/server/server-schema.cpp",
    "tools/server/server-task.cpp",
    "tools/server/server-task.h",
    "tools/server/server.cpp",
    "tools/server/tests/unit/test_completion.py",
]


def scorer_server_argv(server: str, model: str, candidate: str) -> list[str]:
    argv = expected_server_argv(
        server,
        model,
        candidate=candidate,
        profile_name="e7c_final",
    )
    argv[argv.index("--ctx-size") + 1] = "1024"
    argv[argv.index("--parallel") + 1] = "4"
    return argv


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E10c":
        raise ValueError("contract does not identify E10c")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E10c contract")
    inputs = contract["inputs"]
    for key, artifact_path in ARTIFACT_INPUTS.items():
        source = root / inputs[f"{key}_path"]
        expected = inputs[f"{key}_sha256"]
        if (
            sha256_file(source) != expected
            or sha256_file(evidence / artifact_path) != expected
        ):
            raise ValueError(f"E10c input hash differs for {key}")
    for key in ("probe", "ingest"):
        if sha256_file(root / inputs[f"{key}_path"]) != inputs[f"{key}_sha256"]:
            raise ValueError(f"E10c implementation hash differs for {key}")
    return contract


def validate_source_and_build(
    evidence: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    service = contract["service"]
    source = load_object(evidence / "source.json")
    patches = sorted(path.name for path in (evidence / "patches").iterdir())
    if (
        source.get("commit") != service["source_commit"]
        or source.get("tag") != service["source_tag"]
        or source.get("patches_applied") != patches
        or len(patches) != 5
        or sha256_file(evidence / "source-diff.patch") != service["source_diff_sha256"]
        or (evidence / "patched-files.txt").read_text().splitlines() != CHANGED_FILES
    ):
        raise ValueError("E10c source proof differs from the frozen patch set")

    build_dir = evidence / "build"
    e9a = load_object(evidence / "e9a-contract.json")
    cmake_arguments = e9a["profiles"]["e7c_final"]["build"]["cmake_arguments"]
    command = load_object(build_dir / "configure-command.json")
    if command.get("cmake_arguments") != cmake_arguments:
        raise ValueError("E10c CMake arguments differ from E7c")
    cache = (build_dir / "CMakeCache.txt").read_text(errors="replace")
    for argument in cmake_arguments:
        if argument.startswith("-D") and "=" in argument:
            name, value = argument[2:].split("=", 1)
            if value in {"ON", "OFF"} and not any(
                line.startswith(f"{name}:") and line.endswith(f"={value}")
                for line in cache.splitlines()
            ):
                raise ValueError(f"E10c CMake cache differs for {name}")
    version = (build_dir / "server-version.txt").read_text(errors="replace").strip()
    if service["source_commit"][:9] not in version:
        raise ValueError("E10c server version differs from b10216")
    closure = validate_runtime_closure(build_dir / "runtime-closure.json")
    dependencies = sorted(
        {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
    )
    if {"libcrypto.so.3", "libssl.so.3"}.intersection(dependencies):
        raise ValueError("E10c runtime closure unexpectedly contains OpenSSL")
    build_process = parse_time_output((build_dir / "build-time.log").read_text())
    if build_process["maximum_rss_kib"] is None:
        raise ValueError("E10c build process evidence is incomplete")
    return {
        "configure_command": command,
        "cmake_cache_sha256": sha256_file(build_dir / "CMakeCache.txt"),
        "server_version": version,
        "build_process": build_process,
        "runtime_closure": closure,
        "dynamic_dependency_basenames": dependencies,
    }


def validate_recipe(recipe: dict[str, Any], contract: dict[str, Any]) -> None:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E10c"
        or recipe.get("profile_name") != contract["service"]["profile"]
        or recipe.get("service") != contract["service"]
        or model.get("sha256") != contract["selected"]["model_sha256"]
        or model.get("size_bytes") != contract["selected"]["model_size_bytes"]
        or not isinstance(server, str)
        or not isinstance(model_path, str)
    ):
        raise ValueError("E10c recipe differs from the frozen service")
    if recipe.get("argv") != scorer_server_argv(
        server, model_path, contract["selected"]["candidate"]
    ):
        raise ValueError("E10c server argv differs from the frozen scorer service")


def validate_raw(cell_dir: Path, record: dict[str, Any]) -> None:
    path = cell_dir / "raw" / record["path"]
    compressed = path.read_bytes()
    raw = gzip.decompress(compressed)
    if (
        len(raw) != record.get("bytes")
        or hashlib.sha256(raw).hexdigest() != record.get("sha256")
        or len(compressed) != record.get("gzip_bytes")
        or hashlib.sha256(compressed).hexdigest() != record.get("gzip_sha256")
    ):
        raise ValueError(f"{path} raw response integrity differs")


def validate_calibration(
    cell_dir: Path, calibration: dict[str, Any], contract: dict[str, Any]
) -> None:
    expected = contract["workload"]["multi_token_calibration_candidates"]
    if (
        calibration.get("error") is not None
        or calibration.get("candidate_tokens") != expected
        or len(calibration.get("serial_sum_logprobs", [])) != len(expected)
        or len(calibration.get("forked_sum_logprobs", [])) != len(expected)
        or calibration.get("maximum_absolute_sum_logprob_delta", math.inf)
        > contract["acceptance"]["maximum_multi_token_sum_logprob_delta"]
        or calibration.get("maximum_absolute_token_logprob_delta", math.inf)
        > contract["acceptance"]["maximum_token_logprob_delta"]
    ):
        raise ValueError(f"{cell_dir.name} multi-token calibration failed")
    serial_raw = calibration.get("serial_raw_responses")
    forked_raw = calibration.get("forked_raw_responses")
    if (
        not isinstance(serial_raw, list)
        or len(serial_raw) != sum(len(candidate) for candidate in expected)
        or not isinstance(forked_raw, list)
        or len(forked_raw) != 1
    ):
        raise ValueError("calibration raw response count differs")
    for record in serial_raw + forked_raw:
        validate_raw(cell_dir, record)


def validate_case(
    cell_dir: Path,
    case: dict[str, Any],
    *,
    task: dict[str, Any],
    index: int,
    mode: str,
    contract: dict[str, Any],
) -> None:
    labels = contract["workload"]["candidate_labels"]
    expected_requests = len(labels) if mode == "serial" else 1
    scores = case.get("candidate_sum_logprobs")
    token_scores = case.get("candidate_token_logprobs")
    raw = case.get("raw_responses")
    if (
        case.get("index") != index
        or case.get("task_id") != task["id"]
        or case.get("category") != task["category"]
        or case.get("expected") != task["answer"]
        or case.get("error") is not None
        or case.get("prediction") not in labels
        or case.get("selected_index") != labels.index(case["prediction"])
        or case.get("correct") != (case["prediction"] == task["answer"])
        or not isinstance(case.get("prompt_tokens"), int)
        or not 0
        < case["prompt_tokens"]
        <= contract["workload"]["maximum_prompt_tokens"]
        or not isinstance(case.get("prompt_sha256"), str)
        or len(case["prompt_sha256"]) != 64
        or not isinstance(scores, list)
        or len(scores) != len(labels)
        or not isinstance(token_scores, list)
        or len(token_scores) != len(labels)
        or any(
            not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in scores
        )
        or any(
            not isinstance(values, list)
            or len(values) != 1
            or not isinstance(values[0], (int, float))
            or not math.isfinite(values[0])
            for values in token_scores
        )
        or case.get("inference_requests") != expected_requests
        or case.get("prompt_evaluations") != expected_requests
        or not isinstance(raw, list)
        or len(raw) != expected_requests
    ):
        raise ValueError(f"{cell_dir.name} case {task['id']} differs")
    expected_index = max(range(len(scores)), key=lambda item: (scores[item], -item))
    if case["selected_index"] != expected_index:
        raise ValueError("candidate selection differs from summed log probabilities")
    for name in ("http_ms", "prompt_ms", "predicted_ms", "response_bytes"):
        value = case.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{cell_dir.name} has invalid {name}")
    cached = case.get("cached_tokens")
    if (
        not isinstance(cached, list)
        or len(cached) != expected_requests
        or any(value != 0 for value in cached)
    ):
        raise ValueError("measured request unexpectedly reused the prompt cache")
    if mode == "forked":
        if (
            case.get("candidate_contents") != labels
            or case.get("candidate_cached_tokens") != [0] * len(labels)
            or not isinstance(case.get("request_ms"), (int, float))
        ):
            raise ValueError("forked response content differs from exact candidates")
    for record in raw:
        validate_raw(cell_dir, record)


def validate_cell(
    cell_dir: Path,
    *,
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    mode: str,
    repetition: int,
) -> dict[str, Any]:
    recipe = load_object(cell_dir / "recipe.json")
    validate_recipe(recipe, contract)
    timed = (cell_dir / "server-time.log").read_text(errors="replace")
    command_lines = [
        line for line in timed.splitlines() if "Command being timed:" in line
    ]
    if len(command_lines) != 1 or not all(
        argument in command_lines[0] for argument in recipe["argv"]
    ):
        raise ValueError(f"{cell_dir.name} timed command differs")
    readiness = load_object(cell_dir / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not 0 <= ready_ms <= contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError(f"{cell_dir.name} readiness is invalid")
    process = parse_time_output(timed)
    if (
        process["exit_status"]
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
    ):
        raise ValueError(f"{cell_dir.name} process evidence is invalid")

    probe = load_object(cell_dir / "probe.json")
    parameters = probe.get("parameters", {})
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E10c"
        or parameters.get("mode") != mode
        or parameters.get("repetition") != repetition
        or parameters.get("task_count") != len(tasks)
        or parameters.get("candidate_labels")
        != contract["workload"]["candidate_labels"]
        or parameters.get("candidate_token_ids")
        != contract["workload"]["candidate_token_ids"]
        or parameters.get("cache_prompt") is not False
        or parameters.get("seed") != contract["workload"]["seed"]
    ):
        raise ValueError(f"{cell_dir.name} probe parameters differ")
    pid = int((cell_dir / "server-pid.txt").read_text().strip())
    if parameters.get("server_pid") != pid:
        raise ValueError(f"{cell_dir.name} PID binding differs")

    prompt_records = probe.get("prompt_records")
    cases = probe.get("cases")
    if not isinstance(prompt_records, list) or len(prompt_records) != len(tasks):
        raise ValueError("prompt records differ from the frozen task count")
    if not isinstance(cases, list) or len(cases) != len(tasks):
        raise ValueError("cases differ from the frozen task count")
    for index, (task, prompt, case) in enumerate(
        zip(tasks, prompt_records, cases), start=1
    ):
        if (
            prompt.get("task_id") != task["id"]
            or prompt.get("tokens") != case.get("prompt_tokens")
            or prompt.get("sha256") != case.get("prompt_sha256")
        ):
            raise ValueError("prompt record and case identity differ")
        validate_case(
            cell_dir,
            case,
            task=task,
            index=index,
            mode=mode,
            contract=contract,
        )
    validate_calibration(cell_dir, probe.get("multi_token_calibration", {}), contract)

    result = probe.get("result", {})
    failures = sum(case.get("error") is not None for case in cases)
    correct = sum(case.get("correct") is True for case in cases)
    expected_requests = len(tasks) * (4 if mode == "serial" else 1)
    elapsed = result.get("elapsed_seconds")
    if (
        result.get("failures") != failures
        or failures != 0
        or result.get("correct") != correct
        or result.get("total") != len(tasks)
        or not math.isclose(
            result.get("accuracy", -1), correct / len(tasks), rel_tol=1e-12
        )
        or not isinstance(elapsed, (int, float))
        or elapsed <= 0
        or not math.isclose(
            result.get("tasks_per_second", -1), len(tasks) / elapsed, rel_tol=1e-12
        )
        or result.get("inference_requests") != expected_requests
        or result.get("prompt_evaluations") != expected_requests
    ):
        raise ValueError(f"{cell_dir.name} result summary differs")
    process_cpu = validate_process_cpu(
        probe.get("process_cpu"),
        server_pid=pid,
        requests=len(tasks),
        elapsed_seconds=float(elapsed),
    )
    return {
        "mode": mode,
        "repetition": repetition,
        "ready_ms": float(ready_ms),
        "process": process,
        "process_cpu": process_cpu,
        "result": result,
        "prompt_records": prompt_records,
        "cases": cases,
        "multi_token_calibration": probe["multi_token_calibration"],
    }


def compare_cells(
    cells: list[dict[str, Any]], contract: dict[str, Any]
) -> dict[str, Any]:
    by_key = {(cell["mode"], cell["repetition"]): cell for cell in cells}
    maximum_delta = 0.0
    all_predictions_equal = True
    all_prompt_hashes_equal = True
    for repetition in (1, 2):
        serial = by_key[("serial", repetition)]
        forked = by_key[("forked", repetition)]
        all_prompt_hashes_equal &= serial["prompt_records"] == forked["prompt_records"]
        for serial_case, forked_case in zip(serial["cases"], forked["cases"]):
            all_predictions_equal &= (
                serial_case["prediction"] == forked_case["prediction"]
            )
            for serial_score, forked_score in zip(
                serial_case["candidate_sum_logprobs"],
                forked_case["candidate_sum_logprobs"],
            ):
                maximum_delta = max(maximum_delta, abs(serial_score - forked_score))
    serial_predictions = [
        [case["prediction"] for case in by_key[("serial", repetition)]["cases"]]
        for repetition in (1, 2)
    ]
    forked_predictions = [
        [case["prediction"] for case in by_key[("forked", repetition)]["cases"]]
        for repetition in (1, 2)
    ]
    all_predictions_equal &= serial_predictions[0] == serial_predictions[1]
    all_predictions_equal &= forked_predictions[0] == forked_predictions[1]
    if maximum_delta > contract["acceptance"]["maximum_single_token_logprob_delta"]:
        all_predictions_equal = False
    return {
        "maximum_absolute_single_token_logprob_delta": maximum_delta,
        "all_predictions_equal": all_predictions_equal,
        "all_prompt_hashes_equal": all_prompt_hashes_equal,
    }


def aggregate(cells: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, Any]:
    modes: dict[str, dict[str, Any]] = {}
    for mode in ("serial", "forked"):
        selected = [cell for cell in cells if cell["mode"] == mode]
        cases = [case for cell in selected for case in cell["cases"]]
        modes[mode] = {
            "accuracy": summarize(
                [float(cell["result"]["accuracy"]) for cell in selected]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in cases]),
            "response_bytes": summarize(
                [float(case["response_bytes"]) for case in cases]
            ),
            "tasks_per_second": summarize(
                [float(cell["result"]["tasks_per_second"]) for cell in selected]
            ),
            "cpu_seconds_per_task": summarize(
                [float(cell["process_cpu"]["seconds_per_request"]) for cell in selected]
            ),
            "ready_ms": summarize([cell["ready_ms"] for cell in selected]),
            "maximum_rss_kib": max(
                int(cell["process"]["maximum_rss_kib"]) for cell in selected
            ),
            "prompt_evaluations": sum(
                int(cell["result"]["prompt_evaluations"]) for cell in selected
            ),
            "inference_requests": sum(
                int(cell["result"]["inference_requests"]) for cell in selected
            ),
        }
    parity = compare_cells(cells, contract)
    ratios = {
        "median_http_latency": modes["forked"]["http_ms"]["median"]
        / modes["serial"]["http_ms"]["median"],
        "median_cpu_seconds_per_task": modes["forked"]["cpu_seconds_per_task"]["median"]
        / modes["serial"]["cpu_seconds_per_task"]["median"],
        "median_tasks_per_second": modes["forked"]["tasks_per_second"]["median"]
        / modes["serial"]["tasks_per_second"]["median"],
        "maximum_rss": modes["forked"]["maximum_rss_kib"]
        / modes["serial"]["maximum_rss_kib"],
        "prompt_evaluations": modes["forked"]["prompt_evaluations"]
        / modes["serial"]["prompt_evaluations"],
    }
    maximum_multi_sum_delta = max(
        float(cell["multi_token_calibration"]["maximum_absolute_sum_logprob_delta"])
        for cell in cells
    )
    maximum_token_delta = max(
        float(cell["multi_token_calibration"]["maximum_absolute_token_logprob_delta"])
        for cell in cells
    )
    return {
        "modes": modes,
        "ratios": ratios,
        "parity": parity,
        "maximum_multi_token_sum_logprob_delta": maximum_multi_sum_delta,
        "maximum_token_logprob_delta": maximum_token_delta,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = validate_inputs(args.evidence_dir, args.contract, args.root)
    build = validate_source_and_build(args.evidence_dir, contract)
    tasks_manifest = load_object(args.evidence_dir / "tasks-manifest.json")
    tasks = tasks_manifest.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != contract["workload"]["task_count"]:
        raise ValueError("E10c task manifest differs")

    cells: list[dict[str, Any]] = []
    for index, point in enumerate(contract["execution"]["cell_order"], start=1):
        cell_dir = (
            args.evidence_dir
            / "cells"
            / f"{index:02d}-{point['mode']}-r{point['repetition']}"
        )
        cells.append(
            validate_cell(
                cell_dir,
                contract=contract,
                tasks=tasks,
                mode=point["mode"],
                repetition=point["repetition"],
            )
        )
    combined = aggregate(cells, contract)
    acceptance = contract["acceptance"]
    gates = {
        "request_failures": all(cell["result"]["failures"] == 0 for cell in cells),
        "single_token_parity": combined["parity"][
            "maximum_absolute_single_token_logprob_delta"
        ]
        <= acceptance["maximum_single_token_logprob_delta"],
        "multi_token_sum_parity": combined["maximum_multi_token_sum_logprob_delta"]
        <= acceptance["maximum_multi_token_sum_logprob_delta"],
        "multi_token_token_parity": combined["maximum_token_logprob_delta"]
        <= acceptance["maximum_token_logprob_delta"],
        "prediction_parity": combined["parity"]["all_predictions_equal"],
        "prompt_identity": combined["parity"]["all_prompt_hashes_equal"],
        "latency": combined["ratios"]["median_http_latency"]
        <= acceptance["maximum_forked_to_serial_median_http_latency_ratio"],
        "cpu": combined["ratios"]["median_cpu_seconds_per_task"]
        <= acceptance["maximum_forked_to_serial_median_cpu_ratio"],
        "prompt_evaluations": combined["ratios"]["prompt_evaluations"]
        == acceptance["expected_forked_to_serial_prompt_evaluations_ratio"],
        "rss": combined["ratios"]["maximum_rss"]
        <= acceptance["maximum_forked_to_serial_rss_ratio"],
    }
    lscpu = parse_lscpu((args.evidence_dir / "lscpu.txt").read_text())
    provenance = load_object(args.evidence_dir / "provenance.json")
    if (
        lscpu.get("architecture") != "aarch64"
        or provenance.get("experiment_id") != "E10c"
    ):
        raise ValueError("E10c platform or provenance differs")
    summary = {
        "schema_version": 1,
        "experiment_id": "E10c",
        "status": "pass" if all(gates.values()) else "fail",
        "promote_candidate_scorer": all(gates.values()),
        "validation": gates,
        "platform": {
            "lscpu": lscpu,
            "environment": load_object(args.evidence_dir / "environment.json"),
        },
        "source_and_build": build,
        "aggregate": combined,
        "cells": cells,
        "provenance": provenance,
        "claim_boundary": contract["claim_boundary"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {"status": summary["status"], "validation": gates, "aggregate": combined},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
