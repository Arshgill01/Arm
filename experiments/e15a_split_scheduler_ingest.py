#!/usr/bin/env python3
"""Validate the bounded E15a asymmetric scheduler experiment."""

from __future__ import annotations

import argparse
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
        validate_probe,
    )
    from experiments.e5j_ingest import validate_process_cpu
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e15a_split_scheduler_freeze import INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from e5j_ingest import validate_process_cpu
    from e7a_ingest import validate_runtime_closure
    from e15a_split_scheduler_freeze import INPUT_PATHS


ARTIFACT_INPUTS = {
    "manifest": "selected-manifest.json",
    "models": "models-manifest.json",
    "tasks": "tasks-manifest.json",
    "e9a_contract": "e9a-contract.json",
    "e9a_manifest": "e9a-manifest.json",
    "e9a_report": "e9a-report.md",
    "e5j_manifest": "e5j-manifest.json",
    "e5j_report": "e5j-report.md",
    "probe": "probe.py",
    "cell_runner": "cell-runner.sh",
    "freeze": "freeze.py",
    "ingest": "ingest.py",
    "test": "test.py",
}


def expected_server_argv(
    server: str, model: str, contract: dict[str, Any], configuration: str
) -> list[str]:
    config = contract["execution"]["configurations"][configuration]
    return [
        server,
        "--model",
        model,
        "--alias",
        contract["selected"]["candidate"],
        "--threads",
        str(config["threads_decode"]),
        "--threads-batch",
        str(config["threads_batch"]),
        "--ctx-size",
        str(config["context_per_slot"]),
        "--cache-type-k",
        config["kv_cache_type_k"],
        "--cache-type-v",
        config["kv_cache_type_v"],
        "--flash-attn",
        config["flash_attention"],
        "--parallel",
        str(config["server_parallel_slots"]),
        "--cont-batching",
        "--cache-prompt",
        "--host",
        "127.0.0.1",
        "--port",
        "18081",
        "--no-webui",
        "--metrics",
        "--slots",
        "--jinja",
        "--temp",
        "0.0",
        "--seed",
        "424242",
        "--log-colors",
        "off",
        "--batch-size",
        str(config["batch_size"]),
        "--ubatch-size",
        str(config["micro_batch_size"]),
    ]


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E15a"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("contract does not identify E15a")
    for name, relative in INPUT_PATHS.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if (
            sha256_file(root / relative) != expected
            or sha256_file(evidence / ARTIFACT_INPUTS[name]) != expected
        ):
            raise ValueError(f"E15a input differs for {name}")
    prerequisite = contract["prerequisites"]["e9a"]
    if (
        sha256_file(evidence / "e9a-workflow-summary.json")
        != prerequisite["workflow_summary_sha256"]
        or load_object(evidence / "e9a-workflow-summary.json").get("status")
        != prerequisite["required_status"]
    ):
        raise ValueError("E15a E9a workflow prerequisite differs")
    return contract


def validate_runtime(evidence: Path, contract: dict[str, Any]) -> dict[str, Any]:
    runtime_dir = evidence / "runtime"
    closure_path = runtime_dir / "runtime-closure.json"
    closure = validate_runtime_closure(closure_path)
    server = runtime_dir / "runtime-files/bin/llama-server"
    if (
        sha256_file(closure_path) != contract["runtime"]["runtime_closure_sha256"]
        or closure["file_count"] != contract["runtime"]["runtime_closure_file_count"]
        or closure["total_size_bytes"]
        != contract["runtime"]["runtime_closure_total_size_bytes"]
        or server.stat().st_size != contract["runtime"]["server_size_bytes"]
        or sha256_file(server) != contract["runtime"]["server_sha256"]
    ):
        raise ValueError("E15a reused runtime closure differs")
    ldd = (evidence / "runtime-ldd.txt").read_text(errors="replace")
    if "not found" in ldd or "libcrypto.so.3" in ldd or "libssl.so.3" in ldd:
        raise ValueError("E15a reused runtime dependency proof differs")
    version = (evidence / "server-version.txt").read_text(errors="replace").strip()
    if contract["runtime"]["source"]["commit"][:9] not in version:
        raise ValueError("E15a reused runtime version differs")
    return {
        "server_sha256": sha256_file(server),
        "server_size_bytes": server.stat().st_size,
        "server_version": version,
        "runtime_closure": closure,
        "runtime_closure_sha256": sha256_file(closure_path),
        "ldd_sha256": sha256_file(evidence / "runtime-ldd.txt"),
    }


def validate_cell(
    cell_dir: Path,
    *,
    configuration: str,
    repetition: int,
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = contract["execution"]["configurations"][configuration]
    recipe = load_object(cell_dir / "recipe.json")
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("experiment_id") != "E15a"
        or recipe.get("configuration") != configuration
        or recipe.get("repetition") != repetition
        or recipe.get("service") != config
        or model.get("candidate") != contract["selected"]["candidate"]
        or model.get("sha256") != contract["selected"]["model_sha256"]
        or model.get("size_bytes") != contract["selected"]["model_size_bytes"]
        or not isinstance(server, str)
        or not server.endswith("/runtime-files/bin/llama-server")
        or not isinstance(model_path, str)
        or not model_path.endswith(contract["selected"]["path"])
        or contract["runtime"]["source"]["commit"][:9]
        not in recipe.get("server_version", "")
        or recipe.get("argv")
        != expected_server_argv(server, model_path, contract, configuration)
    ):
        raise ValueError(f"{cell_dir.name} E15a recipe differs")
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
        or not math.isfinite(ready_ms)
        or not 0 <= ready_ms <= contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError(f"{cell_dir.name} readiness differs")
    raw_probe = load_object(cell_dir / "probe.json")
    probe = validate_probe(
        raw_probe,
        configuration=configuration,
        repetition=repetition,
        config={
            "client_concurrency": config["client_concurrency"],
            "prompt_cache": config["request_cache_prompt"],
            "warmup_slot_ids": config["warmup_slot_ids"],
        },
        contract=contract,
        tasks=tasks,
        references=references,
    )
    cases = raw_probe["cases"]
    cached = [case.get("cached_tokens") for case in cases]
    if any(
        type(value) is not int
        or value < contract["acceptance"]["minimum_cached_tokens_per_request"]
        for value in cached
    ):
        raise ValueError(f"{cell_dir.name} cache mechanism differs")
    process_cpu = validate_process_cpu(
        raw_probe,
        cell_dir=cell_dir,
        measured_requests=contract["request"]["measured_tasks"],
    )
    process = parse_time_output(timed)
    shell_exit = int((cell_dir / "server-shell-exit.txt").read_text().strip())
    slots = json.loads((cell_dir / "slots.json").read_text())
    if (
        shell_exit not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process.get("maximum_rss_kib") is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
        or not isinstance(slots, list)
        or len(slots) != config["server_parallel_slots"]
        or "llamacpp:" not in (cell_dir / "metrics.txt").read_text()
    ):
        raise ValueError(f"{cell_dir.name} process evidence differs")
    return (
        {
            "configuration": configuration,
            "repetition": repetition,
            "ready_ms": float(ready_ms),
            "probe": probe,
            "server_process_cpu": process_cpu,
            "process": process,
            "server_shell_exit_status": shell_exit,
            "slots_observed": len(slots),
        },
        cases,
    )


def summarize_performance(
    cells: list[dict[str, Any]],
    samples: dict[str, list[dict[str, Any]]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    performance: dict[str, Any] = {}
    for name, config in contract["execution"]["configurations"].items():
        selected = [cell for cell in cells if cell["configuration"] == name]
        raw = samples[name]
        maps = [
            {case["id"]: case["predicted"] for case in raw if case["repetition"] == rep}
            for rep in range(
                1, contract["execution"]["repetitions_per_configuration"] + 1
            )
        ]
        performance[name] = {
            "threads_decode": config["threads_decode"],
            "threads_batch": config["threads_batch"],
            "quality": {
                "correct_per_repetition": [
                    cell["probe"]["correct"] for cell in selected
                ],
                "reference_prediction_mismatches_per_repetition": [
                    cell["probe"]["reference_prediction_mismatches"]
                    for cell in selected
                ],
                "predictions_stable_between_repetitions": all(
                    item == maps[0] for item in maps[1:]
                ),
                "exact_selected_predictions": all(
                    cell["probe"]["correct"]
                    == contract["selected"]["reference_correct"]
                    and cell["probe"]["reference_prediction_mismatches"] == 0
                    for cell in selected
                ),
            },
            "repetitions": selected,
            "samples": raw,
            "requests_per_second": summarize(
                [cell["probe"]["requests_per_second"] for cell in selected]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in raw]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in raw]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in raw]),
            "cached_tokens": summarize([float(case["cached_tokens"]) for case in raw]),
            "server_cpu_seconds_per_request": summarize(
                [
                    float(cell["server_process_cpu"]["seconds_per_request"])
                    for cell in selected
                ]
            ),
            "average_server_cores_used": summarize(
                [
                    float(cell["server_process_cpu"]["average_cores_used"])
                    for cell in selected
                ]
            ),
            "ready_ms": summarize([cell["ready_ms"] for cell in selected]),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in selected]
            ),
        }
    return performance


def evaluate(performance: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    baseline_name = contract["execution"]["baseline_configuration"]
    baseline = performance[baseline_name]
    acceptance = contract["acceptance"]
    gates: dict[str, dict[str, Any]] = {}
    eligible: list[str] = []
    for name, profile in performance.items():
        ratios = {
            "throughput": profile["requests_per_second"]["median"]
            / baseline["requests_per_second"]["median"],
            "median_http_latency": profile["http_ms"]["median"]
            / baseline["http_ms"]["median"],
            "p95_http_latency": profile["http_ms"]["p95"] / baseline["http_ms"]["p95"],
            "encode_latency": profile["encode_ms"]["median"]
            / baseline["encode_ms"]["median"],
            "cpu_seconds_per_request": profile["server_cpu_seconds_per_request"][
                "median"
            ]
            / baseline["server_cpu_seconds_per_request"]["median"],
        }
        checks = {
            "quality_passed": profile["quality"]["exact_selected_predictions"]
            and profile["quality"]["predictions_stable_between_repetitions"],
            "cache_passed": profile["cached_tokens"]["min"]
            >= acceptance["minimum_cached_tokens_per_request"],
            "throughput_passed": ratios["throughput"]
            >= acceptance["minimum_candidate_throughput_ratio"],
            "median_latency_passed": ratios["median_http_latency"]
            <= acceptance["maximum_candidate_median_http_latency_ratio"],
            "p95_latency_passed": ratios["p95_http_latency"]
            <= acceptance["maximum_candidate_p95_http_latency_ratio"],
            "encode_latency_passed": ratios["encode_latency"]
            <= acceptance["maximum_candidate_encode_latency_ratio"],
            "cpu_time_passed": ratios["cpu_seconds_per_request"]
            <= acceptance["maximum_candidate_cpu_seconds_per_request_ratio"],
            "dispersion_passed": profile["requests_per_second"][
                "coefficient_of_variation"
            ]
            <= acceptance["maximum_throughput_coefficient_of_variation"],
        }
        promotable = name in contract["execution"]["candidate_configurations"]
        passed = promotable and all(checks.values())
        gates[name] = {
            **checks,
            "promotable": promotable,
            "eligible": passed,
            "ratios": ratios,
        }
        if passed:
            eligible.append(name)
    selected = (
        min(
            eligible,
            key=lambda name: (
                performance[name]["server_cpu_seconds_per_request"]["median"],
                -performance[name]["requests_per_second"]["median"],
                -performance[name]["threads_decode"],
                name,
            ),
        )
        if eligible
        else baseline_name
    )
    return {
        "passed": bool(eligible),
        "baseline_configuration": baseline_name,
        "selected_configuration": selected,
        "eligible_configurations": sorted(eligible),
        "profile_gates": gates,
        "weighted_score_used": False,
    }


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    runtime = validate_runtime(evidence, contract)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if (
        platform["architecture"] != contract["acceptance"]["required_architecture"]
        or platform["model_name"] != contract["acceptance"]["required_model_name"]
        or platform["logical_cpus"] != contract["acceptance"]["required_logical_cpus"]
    ):
        raise ValueError("E15a native runner topology differs")
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if (
        len(model_line) != 2
        or model_line[0] != contract["selected"]["model_sha256"]
        or int((evidence / "model-size.txt").read_text())
        != contract["selected"]["model_size_bytes"]
    ):
        raise ValueError("E15a model identity differs")
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["manifest_path"]),
        contract["selected"]["candidate"],
    )
    order = contract["execution"]["order"]
    expected = {
        (name, repetition)
        for name in contract["execution"]["configurations"]
        for repetition in range(
            1, contract["execution"]["repetitions_per_configuration"] + 1
        )
    }
    if (
        len(order) != len(expected)
        or {(item["configuration"], item["repetition"]) for item in order} != expected
    ):
        raise ValueError("E15a balanced execution order differs")
    cells = []
    samples = {name: [] for name in contract["execution"]["configurations"]}
    for index, item in enumerate(order, 1):
        name = item["configuration"]
        repetition = item["repetition"]
        cell_dir = evidence / "cells" / f"{index:02d}-{name}-r{repetition}"
        cell, raw = validate_cell(
            cell_dir,
            configuration=name,
            repetition=repetition,
            contract=contract,
            tasks=tasks,
            references=references,
        )
        cells.append(cell)
        samples[name].extend({**case, "repetition": repetition} for case in raw)
    performance = summarize_performance(cells, samples, contract)
    decision = evaluate(performance, contract)
    return {
        "schema_version": 1,
        "experiment_id": "E15a",
        "status": (
            "valid_split_scheduler_promoted"
            if decision["passed"]
            else "valid_split_scheduler_no_promotion"
        ),
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "runtime": runtime,
        "model": contract["selected"],
        "performance": performance,
        "decision": decision,
        "validation": {
            "native_arm64_same_job": True,
            "exact_e9a_runtime_reused": True,
            "exact_model_and_workload": True,
            "fresh_server_per_cell": True,
            "balanced_four_repetitions": True,
            "independent_prefill_decode_controls": True,
            "exact_quality": all(
                profile["quality"]["exact_selected_predictions"]
                for profile in performance.values()
            ),
            "zero_request_failures": True,
            "weighted_score_used": False,
            "energy_claim_allowed": False,
        },
        "measurement_boundary": contract["measurement_boundary"],
        "claim_boundary": contract["claim_boundary"],
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
