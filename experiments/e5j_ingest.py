#!/usr/bin/env python3
"""Validate native E5j Arm serving thread-efficiency evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, summarize
    from experiments.e5b_ingest import (
        ARTIFACT_INPUTS,
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_cell,
        validate_recipe,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, summarize
    from e5b_ingest import (
        ARTIFACT_INPUTS,
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_cell,
        validate_recipe,
    )


def validate_thread_invocation(cell_dir: Path, config: dict[str, Any]) -> None:
    threads = config["threads"]
    time_log = (cell_dir / "server-time.log").read_text(
        encoding="utf-8", errors="replace"
    )
    commands = [
        line for line in time_log.splitlines() if "Command being timed:" in line
    ]
    if len(commands) != 1 or f" --threads {threads}" not in commands[0]:
        raise ValueError(f"{cell_dir.name} Pareto64 thread invocation differs")

    recipe = load_object(cell_dir / "recipe.json")
    runtime = recipe["runtime"]
    argv = runtime["argv"]
    for argument in ("--threads", "--threads-batch"):
        if (
            runtime.get("threads") != threads
            or argv.count(argument) != 1
            or argv.index(argument) == len(argv) - 1
            or argv[argv.index(argument) + 1] != str(threads)
        ):
            raise ValueError(f"{cell_dir.name} launch recipe thread binding differs")


def validate_process_cpu(
    probe: dict[str, Any],
    *,
    cell_dir: Path,
    measured_requests: int,
) -> dict[str, float | int]:
    parameters = probe.get("parameters", {})
    result = probe.get("result", {})
    cpu = result.get("server_process_cpu")
    if not isinstance(cpu, dict):
        raise ValueError(f"{cell_dir.name} lacks measured-window server CPU evidence")
    pid = int((cell_dir / "server-pid.txt").read_text(encoding="utf-8").strip())
    integer_fields = (
        "pid",
        "clock_ticks_per_second",
        "user_ticks",
        "system_ticks",
        "total_ticks",
    )
    if any(type(cpu.get(field)) is not int for field in integer_fields):
        raise ValueError(f"{cell_dir.name} server CPU counters are not integers")
    if parameters.get("server_pid") != pid or cpu["pid"] != pid:
        raise ValueError(f"{cell_dir.name} server CPU PID binding differs")
    if (
        cpu["clock_ticks_per_second"] <= 0
        or cpu["user_ticks"] < 0
        or cpu["system_ticks"] < 0
        or cpu["total_ticks"] <= 0
        or cpu["total_ticks"] != cpu["user_ticks"] + cpu["system_ticks"]
    ):
        raise ValueError(f"{cell_dir.name} server CPU counters are invalid")

    elapsed = result.get("elapsed_seconds")
    if (
        not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed <= 0
    ):
        raise ValueError(f"{cell_dir.name} server CPU interval elapsed time is invalid")
    total_seconds = cpu["total_ticks"] / cpu["clock_ticks_per_second"]
    expected = {
        "user_seconds": cpu["user_ticks"] / cpu["clock_ticks_per_second"],
        "system_seconds": cpu["system_ticks"] / cpu["clock_ticks_per_second"],
        "total_seconds": total_seconds,
        "seconds_per_request": total_seconds / measured_requests,
        "average_cores_used": total_seconds / elapsed,
    }
    for field, value in expected.items():
        observed = cpu.get(field)
        if (
            not isinstance(observed, (int, float))
            or not math.isfinite(observed)
            or observed < 0
            or not math.isclose(float(observed), value, rel_tol=1e-12, abs_tol=0.0)
        ):
            raise ValueError(f"{cell_dir.name} server CPU {field} differs")
    if expected["seconds_per_request"] <= 0 or expected["average_cores_used"] <= 0:
        raise ValueError(f"{cell_dir.name} server CPU interval is empty")
    return {
        **{field: cpu[field] for field in integer_fields},
        **expected,
    }


def evaluate_profiles(
    performance: dict[str, Any],
    *,
    acceptance: dict[str, Any],
    baseline_configuration: str,
) -> dict[str, Any]:
    baseline = performance[baseline_configuration]
    baseline_throughput = baseline["requests_per_second"]["median"]
    baseline_median_latency = baseline["http_ms"]["median"]
    baseline_p95_latency = baseline["http_ms"]["p95"]
    baseline_cpu = baseline["server_cpu_seconds_per_request"]["median"]
    if min(
        baseline_throughput,
        baseline_median_latency,
        baseline_p95_latency,
        baseline_cpu,
    ) <= 0:
        raise ValueError("baseline thread profile contains a non-positive value")

    gates: dict[str, dict[str, Any]] = {}
    eligible: list[str] = []
    for name, profile in performance.items():
        throughput_ratio = (
            profile["requests_per_second"]["median"] / baseline_throughput
        )
        median_latency_ratio = profile["http_ms"]["median"] / baseline_median_latency
        p95_latency_ratio = profile["http_ms"]["p95"] / baseline_p95_latency
        cpu_ratio = (
            profile["server_cpu_seconds_per_request"]["median"] / baseline_cpu
        )
        quality_passed = profile["quality"]["exact_selected_predictions"]
        throughput_passed = (
            throughput_ratio >= acceptance["minimum_throughput_retention_ratio"]
        )
        latency_passed = (
            median_latency_ratio
            <= acceptance["maximum_median_http_latency_ratio"]
            and p95_latency_ratio <= acceptance["maximum_p95_http_latency_ratio"]
        )
        cpu_passed = (
            cpu_ratio <= acceptance["maximum_cpu_seconds_per_request_ratio"]
        )
        profile_eligible = (
            name != baseline_configuration
            and quality_passed
            and throughput_passed
            and latency_passed
            and cpu_passed
        )
        gates[name] = {
            "eligible": profile_eligible,
            "quality_passed": quality_passed,
            "throughput_retention_passed": throughput_passed,
            "latency_retention_passed": latency_passed,
            "cpu_time_reduction_passed": cpu_passed,
            "throughput_retention_ratio": throughput_ratio,
            "median_http_latency_ratio": median_latency_ratio,
            "p95_http_latency_ratio": p95_latency_ratio,
            "cpu_seconds_per_request_ratio": cpu_ratio,
            "cpu_seconds_per_request_reduction_ratio": 1.0 - cpu_ratio,
        }
        if profile_eligible:
            eligible.append(name)

    selected = (
        min(
            eligible,
            key=lambda name: (
                performance[name]["server_cpu_seconds_per_request"]["median"],
                performance[name]["threads"],
                -performance[name]["requests_per_second"]["median"],
                name,
            ),
        )
        if eligible
        else baseline_configuration
    )
    return {
        "passed": bool(eligible),
        "baseline_configuration": baseline_configuration,
        "selected_configuration": selected,
        "eligible_configurations": sorted(eligible),
        "profile_gates": gates,
        "weighted_score_used": False,
        "metric_boundary": "server process CPU time; not energy or power",
    }


def build_manifest(
    evidence_dir: Path,
    contract_path: Path,
    manifest_path: Path,
    policy_path: Path,
    models_path: Path,
    runtime_contract_path: Path,
    tasks_path: Path,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E5j":
        raise ValueError("unsupported E5j contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E5j contract")

    source_paths = {
        "manifest": manifest_path,
        "policy": policy_path,
        "models": models_path,
        "runtime_contract": runtime_contract_path,
        "tasks": tasks_path,
    }
    for name, path in source_paths.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if sha256_file(path) != expected:
            raise ValueError(f"source {name} hash differs from the contract")
        if sha256_file(evidence_dir / ARTIFACT_INPUTS[name]) != expected:
            raise ValueError(f"artifact {name} hash differs from the contract")

    runtime_proof = (evidence_dir / "runtime-proof.stderr.log").read_text(
        encoding="utf-8", errors="replace"
    )
    required_patterns = contract["selected"]["required_runtime_buffer_patterns"]
    for pattern in required_patterns:
        if pattern not in runtime_proof:
            raise ValueError(f"unmeasured runtime proof lacks buffer: {pattern}")

    selected_manifest = load_object(manifest_path)
    tasks = load_tasks(load_object(tasks_path))
    candidate = contract["selected"]["candidate"]
    references = reference_predictions(selected_manifest, candidate)
    if set(references) != {task["id"] for task in tasks}:
        raise ValueError("selected predictions and task IDs differ")
    correct = sum(references[task["id"]] == task["answer"] for task in tasks)
    if (
        correct != contract["selected"]["reference_correct"]
        or len(tasks) != contract["selected"]["reference_total"]
    ):
        raise ValueError("contract selected quality differs from retained evidence")

    execution = contract["execution"]
    configurations = execution["configurations"]
    baseline_configuration = execution["baseline_configuration"]
    if configurations[baseline_configuration]["threads"] != 4 or {
        config["threads"] for config in configurations.values()
    } != {2, 3, 4}:
        raise ValueError("thread configurations differ from the frozen profile")
    order = execution["order"]
    expected_pairs = {
        (name, repetition)
        for name in configurations
        for repetition in range(1, execution["repetitions_per_configuration"] + 1)
    }
    observed_pairs = {
        (item.get("configuration"), item.get("repetition")) for item in order
    }
    if len(order) != len(expected_pairs) or observed_pairs != expected_pairs:
        raise ValueError("execution order does not cover every frozen cell once")

    provenance = load_object(evidence_dir / "provenance.json")
    if (
        provenance.get("experiment_id") != "E5j"
        or provenance.get("default_configuration") != baseline_configuration
    ):
        raise ValueError("provenance does not bind the E5j default")
    platform = parse_lscpu((evidence_dir / "lscpu.txt").read_text(encoding="utf-8"))
    topology = contract["prior_evidence"]["host_topology"]
    if any(platform.get(key) != value for key, value in topology.items()):
        raise ValueError("runner CPU topology differs from the frozen Arm host")

    cells = []
    cell_paths: dict[tuple[str, int], Path] = {}
    cpu_records: dict[tuple[str, int], dict[str, float | int]] = {}
    for index, item in enumerate(order, 1):
        configuration = item["configuration"]
        repetition = item["repetition"]
        cell_dir = evidence_dir / "cells" / f"{index:02d}-{configuration}-r{repetition}"
        cell_paths[(configuration, repetition)] = cell_dir
        config = configurations[configuration]
        validate_recipe(
            load_object(cell_dir / "recipe.json"), config=config, contract=contract
        )
        validate_thread_invocation(cell_dir, config)
        cells.append(
            validate_cell(
                cell_dir,
                configuration=configuration,
                repetition=repetition,
                config=config,
                contract=contract,
                tasks=tasks,
                references=references,
                require_selected_quality=False,
            )
        )
        probe = load_object(cell_dir / "probe.json")
        cpu_records[(configuration, repetition)] = validate_process_cpu(
            probe,
            cell_dir=cell_dir,
            measured_requests=contract["request"]["measured_tasks"],
        )

    performance: dict[str, Any] = {}
    maximum_prompt_tokens = 0
    for name, configuration in configurations.items():
        config_cells = [cell for cell in cells if cell["configuration"] == name]
        probes = [
            load_object(cell_paths[(name, cell["repetition"])] / "probe.json")
            for cell in config_cells
        ]
        raw_cases = [case for probe in probes for case in probe["cases"]]
        prompt_tokens = [
            int(case["cached_tokens"]) + int(case["evaluated_prompt_tokens"])
            for case in raw_cases
        ]
        maximum_prompt_tokens = max(maximum_prompt_tokens, max(prompt_tokens))
        prediction_maps = [
            {case["id"]: case["predicted"] for case in probe["cases"]}
            for probe in probes
        ]
        exact_predictions = all(
            cell["probe"]["correct"] == contract["selected"]["reference_correct"]
            and cell["probe"]["reference_prediction_mismatches"]
            == contract["acceptance"]["reference_prediction_mismatches"]
            for cell in config_cells
        )
        repetitions = [
            cpu_records[(name, cell["repetition"])] for cell in config_cells
        ]
        performance[name] = {
            "threads": configuration["threads"],
            "quality": {
                "correct_per_repetition": [
                    cell["probe"]["correct"] for cell in config_cells
                ],
                "reference_prediction_mismatches_per_repetition": [
                    cell["probe"]["reference_prediction_mismatches"]
                    for cell in config_cells
                ],
                "predictions_stable_between_repetitions": all(
                    item == prediction_maps[0] for item in prediction_maps[1:]
                ),
                "exact_selected_predictions": exact_predictions,
            },
            "repetitions": config_cells,
            "server_process_cpu_repetitions": repetitions,
            "server_cpu_seconds_per_request": summarize(
                [float(item["seconds_per_request"]) for item in repetitions]
            ),
            "average_server_cores_used": summarize(
                [float(item["average_cores_used"]) for item in repetitions]
            ),
            "requests_per_second": summarize(
                [cell["probe"]["requests_per_second"] for cell in config_cells]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in raw_cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in raw_cases]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in raw_cases]),
            "cached_tokens": summarize(
                [float(case["cached_tokens"]) for case in raw_cases]
            ),
            "prompt_tokens": summarize([float(value) for value in prompt_tokens]),
            "ready_ms": summarize([cell["ready_ms"] for cell in config_cells]),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in config_cells]
            ),
        }

    if (
        maximum_prompt_tokens
        != contract["prior_evidence"]["maximum_observed_prompt_tokens"]
    ):
        raise ValueError("observed prompt bound differs from prior evidence")
    profile_result = evaluate_profiles(
        performance,
        acceptance=contract["acceptance"],
        baseline_configuration=baseline_configuration,
    )
    selected_configuration = profile_result["selected_configuration"]
    run_id = str(provenance["github_run_id"])
    artifact_name = (
        f"{contract['artifact_name_prefix']}-{run_id}-"
        f"{provenance['github_run_attempt']}"
    )
    return {
        "schema_version": 1,
        "experiment_id": "E5j",
        "status": (
            "valid_selected_inference_thread_efficiency"
            if profile_result["passed"]
            else "valid_selected_inference_no_thread_efficiency_win"
        ),
        "scope": contract["scope"],
        "source": {
            "artifact_name": artifact_name,
            "github_run_url": (
                f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}"
            ),
            "artifact_retention_days": 90,
        },
        "contract": contract,
        "provenance": provenance,
        "platform": {
            **platform,
            "uname": (evidence_dir / "uname.txt").read_text().strip(),
            "python": (evidence_dir / "python-version.txt").read_text().strip(),
        },
        "selection": {
            "candidate": candidate,
            "correct": correct,
            "total": len(tasks),
            "accuracy": correct / len(tasks),
            "model_sha256": contract["selected"]["model_sha256"],
            "model_size_bytes": contract["selected"]["model_size_bytes"],
            "baseline_configuration": baseline_configuration,
            "selected_configuration": selected_configuration,
            "selected_threads": configurations[selected_configuration]["threads"],
        },
        "validation": {
            "all_input_hashes_match": True,
            "launch_recomputed_selected_plan": True,
            "exact_model_and_runtime_verified": True,
            "zero_request_failures": True,
            "fresh_server_per_cell": True,
            "runtime_buffer_proof_observed": True,
            "thread_arguments_bound_in_every_recipe": True,
            "server_pid_bound_in_every_probe": True,
            "measured_window_process_cpu_validated": True,
            "model_load_and_warmups_excluded_from_cpu_window": True,
            "cached_prefix_observed_in_every_measured_request": True,
            "quality_drift_treated_as_profile_ineligibility": True,
            "energy_claim_allowed": False,
            "thread_efficiency_claim_allowed": profile_result["passed"],
        },
        "measurement_boundary": contract["measurement_boundary"],
        "maximum_observed_prompt_tokens": maximum_prompt_tokens,
        "performance": performance,
        "runtime_buffer_patterns_observed": required_patterns,
        "hypothesis": profile_result,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--runtime-contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    manifest = build_manifest(
        arguments.evidence_dir,
        arguments.contract,
        arguments.manifest,
        arguments.policy,
        arguments.models,
        arguments.runtime_contract,
        arguments.tasks,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
