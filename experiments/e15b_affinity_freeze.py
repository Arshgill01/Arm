#!/usr/bin/env python3
"""Freeze the confirmatory two-CPU-affinity split-scheduler experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


INPUT_PATHS = {
    "manifest": Path("results/manifests/e3f-30656151957.json"),
    "models": Path("experiments/e3f_models.json"),
    "tasks": Path("experiments/e3_tasks.json"),
    "e9a_contract": Path("experiments/e9a_contract.json"),
    "e9a_manifest": Path("results/manifests/e9a-30764802071.json"),
    "e15a_contract": Path("experiments/e15a_contract.json"),
    "e15a_failure": Path("results/manifests/e15a-30849270574.json"),
    "e15a_failure_report": Path(
        "results/reports/e15a-split-scheduler-topology-failure.md"
    ),
    "probe": Path("experiments/e5b_inference_probe.py"),
    "cell_runner": Path("experiments/e15b_affinity_cell.sh"),
    "freeze": Path("experiments/e15b_affinity_freeze.py"),
    "ingest": Path("experiments/e15b_affinity_ingest.py"),
    "test": Path("tests/test_e15b.py"),
}


def require_true(value: dict[str, Any], names: tuple[str, ...], label: str) -> None:
    validation = value.get("validation")
    if not isinstance(validation, dict) or not all(
        validation.get(name) is True for name in names
    ):
        raise ValueError(f"{label} required validation differs")


def build_contract(root: Path) -> dict[str, Any]:
    e9a_contract = load_object(root / INPUT_PATHS["e9a_contract"])
    e9a = load_object(root / INPUT_PATHS["e9a_manifest"])
    failure = load_object(root / INPUT_PATHS["e15a_failure"])
    if (
        e9a.get("status") != "valid_final_service_win"
        or e9a.get("selection", {}).get("candidate") != "ministral3_3b_q4_k_m"
        or e9a.get("platform", {}).get("architecture") != "aarch64"
        or e9a.get("platform", {}).get("logical_cpus") != 2
        or e9a.get("platform", {}).get("model_name") != "Neoverse-N2"
    ):
        raise ValueError("E15b exact E9a prerequisite differs")
    require_true(
        e9a,
        (
            "binary_and_dependency_closures_hashed",
            "fresh_server_per_cell",
            "measured_window_process_cpu_validated",
            "native_arm64_same_job",
            "raw_answers_retained_in_manifest",
            "reverse_balanced_four_repetitions",
        ),
        "E9a",
    )
    if (
        failure.get("status") != "invalid_native_runner_topology_mismatch"
        or failure.get("promotion_decision_permitted") is not False
        or failure.get("raw_cells_validated") != 16
        or failure.get("raw_measured_requests_validated") != 480
        or failure.get("failure", {}).get("expected_platform", {}).get(
            "logical_cpus"
        )
        != 2
        or failure.get("failure", {}).get("observed_platform", {}).get(
            "logical_cpus"
        )
        != 4
        or failure.get("decision", {}).get(
            "change_frozen_required_logical_cpus_after_observation"
        )
        is not False
        or failure.get("decision", {}).get(
            "separately_frozen_affinity_control_successor_allowed"
        )
        is not True
    ):
        raise ValueError("E15b retained E15a failure prerequisite differs")
    service = e9a_contract["profiles"]["e7c_final"]
    base = {
        **service["service"],
        "client_concurrency": 1,
        "threads_decode": 4,
        "threads_batch": 4,
    }
    base.pop("threads")
    configurations = {
        "tied4_4": {**base},
        "split2_4": {**base, "threads_decode": 2},
    }
    order_names = (
        ("tied4_4", "split2_4"),
        ("split2_4", "tied4_4"),
        ("split2_4", "tied4_4"),
        ("tied4_4", "split2_4"),
        ("tied4_4", "split2_4"),
        ("split2_4", "tied4_4"),
    )
    order = [
        {"configuration": name, "repetition": repetition}
        for repetition, names in enumerate(order_names, start=1)
        for name in names
    ]
    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    return {
        "schema_version": 1,
        "experiment_id": "E15b",
        "title": "Confirmatory two-CPU-affinity split-scheduler boundary",
        "state": (
            "frozen after E15a completed on an invalid four-CPU topology and exposed "
            "a descriptive no-win; E15b preserves the exact original service gates, "
            "enforces the unresolved two-CPU boundary, and is confirmatory rather than "
            "blind discovery"
        ),
        "hypothesis": (
            "On an exact two-CPU server-and-client affinity boundary matching E9a's "
            "logical CPU count, decode 2 / batch 4 can reduce server CPU seconds per "
            "request by at least two percent while retaining at least 98 percent of "
            "throughput and no more than two percent median or tail regression."
        ),
        "scope": (
            "Only tied 4/4 and the mechanism-selected decode 2 / batch 4 candidate are "
            "rerun. Both the server and request client are pinned to the same lowest "
            "two CPUs from the job affinity mask. Model, runtime, workload, cache, "
            "batch, context, request, and original E15a performance gates are unchanged."
        ),
        "inputs": inputs,
        "prerequisites": {
            "e9a": {
                "run_id": "30764802071",
                "run_attempt": 1,
                "artifact_name": "e9a-final-service-30764802071-1",
                "artifact_id": 8838874234,
                "artifact_digest": "sha256:3d360aed5fd02abf5421c3a23309f1abda56bf5f96c0e406a5c13897c15aae70",
                "workflow_summary_sha256": "39424e7f3a43a3a05b4139609224584945c8da7c1de66a9f224e8c7184de012d",
                "required_status": e9a["status"],
            },
            "e15a_failure": {
                "run_id": failure["github"]["run_id"],
                "artifact_id": failure["github"]["artifact_id"],
                "artifact_digest": failure["github"]["artifact_digest"],
                "manifest_sha256": sha256_file(root / INPUT_PATHS["e15a_failure"]),
                "required_status": failure["status"],
                "four_cpu_outcome_seen_before_freeze": True,
                "four_cpu_outcome_eligible_for_promotion": False,
            },
        },
        "selected": {
            "candidate": e9a["selection"]["candidate"],
            "reference_correct": e9a["selection"]["correct"],
            "reference_total": e9a["selection"]["total"],
            "reference_accuracy": e9a["selection"]["accuracy"],
            "model_sha256": e9a["selection"]["model_sha256"],
            "model_size_bytes": e9a["selection"]["model_size_bytes"],
            "repository": "unsloth/Ministral-3-3B-Instruct-2512-GGUF",
            "revision": "7564922f37fa5bbb62b87f09a55c12f1f91d7a6a",
            "path": "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
        },
        "runtime": {
            "source": service["source"],
            "build": service["build"],
            "server_sha256": "e15e14bd5d4f86e09a79603862f52db841de758ecc21b2c476a2ba92cc8ee40e",
            "server_size_bytes": 72488,
            "runtime_closure_sha256": "a441ab5943b5dea87ae713afff6573c62a874cf919fa1b0fa8908073ecabdf8b",
            "runtime_closure_file_count": 8,
            "runtime_closure_total_size_bytes": 19857448,
            "binary_reuse": "Reuse the exact retained E9a E7c artifact closure.",
        },
        "request": {
            "instruction_role": "system",
            "chat_template_mode": "model_jinja_system_instruction",
            "temperature": 0.0,
            "seed": 424242,
            "max_output_tokens": 8,
            "timeout_seconds": 30.0,
            "warmup_task_ids": ["arithmetic-02", "logic-01"],
            "measured_tasks": 30,
            "client_concurrency": 1,
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "minimum_host_logical_cpus": 2,
            "affinity_selection": "lowest two IDs in os.sched_getaffinity(0)",
            "server_affinity_cpu_count": 2,
            "client_affinity_cpu_count": 2,
            "same_server_client_affinity_required": True,
            "configurations": configurations,
            "baseline_configuration": "tied4_4",
            "candidate_configurations": ["split2_4"],
            "repetitions_per_configuration": 6,
            "fresh_server_per_cell": True,
            "same_job": True,
            "order_design": "six reverse-balanced pairs",
            "order": order,
            "total_fresh_processes": 12,
            "total_measured_requests": 360,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "required_model_name": "Neoverse-N2",
            "minimum_host_logical_cpus": 2,
            "required_affinity_cpu_count": 2,
            "http_status": 200,
            "termination_reason": "stop",
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "minimum_cached_tokens_per_request": 1,
            "minimum_candidate_throughput_ratio": 0.98,
            "maximum_candidate_median_http_latency_ratio": 1.02,
            "maximum_candidate_p95_http_latency_ratio": 1.02,
            "maximum_candidate_cpu_seconds_per_request_ratio": 0.98,
            "maximum_candidate_encode_latency_ratio": 1.02,
            "maximum_throughput_coefficient_of_variation": 0.05,
            "maximum_ready_ms": 15000.0,
            "maximum_process_rss_kib": 8388608,
            "accepted_server_shell_exit_statuses": [0, 130],
            "weighted_score_used": False,
            "post_result_gate_change_permitted": False,
        },
        "selection": {
            "eligible": (
                "Only split2_4 may promote, and only after every exact quality, "
                "cache, affinity, throughput, median, p95, encode, CPU, dispersion, "
                "readiness, RSS, and runtime gate passes."
            ),
            "no_win_rule": "Retain tied4_4 when split2_4 fails any gate.",
        },
        "measurement_boundary": (
            "The server and measured request client are restricted to the same exact "
            "two-CPU affinity set. Server CPU counters cover only the 30 measured "
            "requests after two warmups. Downloads, readiness, warmups, client CPU, "
            "metrics, and shutdown are excluded. CPU time is not energy or power."
        ),
        "negative_result_rule": (
            "Retain affinity failure, quality drift, scheduler noise, latency or "
            "throughput regression, CPU non-improvement, and no-win outcomes without "
            "changing the affinity policy, repetitions, workload, or original gates."
        ),
        "claim_boundary": (
            "E15b can establish only a confirmatory exact end-product split-thread "
            "result inside one two-CPU affinity boundary on native GitHub Arm64. It "
            "does not establish blind discovery, unpinned host behavior, long-context, "
            "long-generation, energy, PMU, local-device, fleet, or cost behavior."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
