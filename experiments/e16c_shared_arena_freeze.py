#!/usr/bin/env python3
"""Freeze the two-worker shared repack-sidecar PSS experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


INPUT_PATHS = {
    "manifest": Path("results/manifests/e3f-30656151957.json"),
    "policy": Path("configs/cloud-quality.json"),
    "models": Path("experiments/e3f_models.json"),
    "runtime_contract": Path("experiments/e3f_contract.json"),
    "tasks": Path("experiments/e3_tasks.json"),
    "e9a_contract": Path("experiments/e9a_contract.json"),
    "e16a_result": Path("results/manifests/e16a-30837796757.json"),
    "e16b_contract": Path("experiments/e16b_contract.json"),
    "e16b_result": Path("results/manifests/e16b-30842925537.json"),
    "e16b_report": Path("results/reports/e16b-repack-sidecar-loader.md"),
    "patch_1": Path(
        "patches/llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch"
    ),
    "patch_2": Path("patches/llama.cpp/0002-arm-q8-vector-narrowing-stores.patch"),
    "patch_3": Path(
        "patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch"
    ),
    "dump_patch": Path(
        "patches/llama.cpp/b10216/0006-repack-sidecar-feasibility-dump.patch"
    ),
    "loader_patch": Path(
        "patches/llama.cpp/b10216/0007-repack-sidecar-readonly-loader.patch"
    ),
    "sidecar_builder": Path("experiments/e16a_sidecar.py"),
    "constructor": Path("experiments/e16b_construct.sh"),
    "dual_probe": Path("experiments/e16c_dual_probe.py"),
    "group_runner": Path("experiments/e16c_shared_arena_group.sh"),
    "freeze": Path("experiments/e16c_shared_arena_freeze.py"),
    "ingest": Path("experiments/e16c_shared_arena_ingest.py"),
    "test": Path("tests/test_e16c.py"),
}


def build_contract(root: Path) -> dict:
    predecessor_contract = load_object(root / INPUT_PATHS["e16b_contract"])
    predecessor = load_object(root / INPUT_PATHS["e16b_result"])
    if (
        predecessor_contract.get("experiment_id") != "E16b"
        or predecessor.get("status") != "valid_sidecar_loader_promoted"
        or predecessor.get("promoted") is not True
        or predecessor.get("decision", {}).get("loader_promoted") is not True
        or predecessor.get("decision", {}).get(
            "multi_process_sharing_claim_permitted"
        )
        is not False
        or predecessor.get("artifact_validation", {}).get(
            "independent_summary_byte_identical"
        )
        is not True
    ):
        raise ValueError("E16c exact E16b prerequisite differs")
    order = [
        {"configuration": "normal_repack_workers", "repetition": 1},
        {"configuration": "shared_sidecar_workers", "repetition": 1},
        {"configuration": "shared_sidecar_workers", "repetition": 2},
        {"configuration": "normal_repack_workers", "repetition": 2},
        {"configuration": "shared_sidecar_workers", "repetition": 3},
        {"configuration": "normal_repack_workers", "repetition": 3},
        {"configuration": "normal_repack_workers", "repetition": 4},
        {"configuration": "shared_sidecar_workers", "repetition": 4},
    ]
    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    return {
        "schema_version": 1,
        "experiment_id": "E16c",
        "title": "Two-worker shared Arm repack-sidecar physical-memory boundary",
        "state": (
            "frozen after E16b admitted only the single-process loader and before "
            "observing any simultaneous-worker PSS, throughput, or quality result"
        ),
        "hypothesis": (
            "Mapping one verified packed arena MAP_SHARED into two simultaneous E7c "
            "workers can reduce their summed post-workload PSS by at least 25 percent "
            "versus two normal-repack workers while retaining at least 95 percent of "
            "aggregate throughput and exact output."
        ),
        "scope": (
            "Construct one provenance-bound sidecar, then compare two simultaneous "
            "normal-repack workers against two simultaneous read-only loader workers "
            "in eight reverse-balanced fresh two-process groups. Both workers receive "
            "the exact 30-task workload concurrently on separate loopback ports."
        ),
        "inputs": inputs,
        "prerequisite": {
            "experiment_id": "E16b",
            "run_id": predecessor["github"]["run_id"],
            "run_attempt": predecessor["github"]["run_attempt"],
            "artifact_name": predecessor["github"]["artifact_name"],
            "artifact_id": predecessor["github"]["artifact_id"],
            "manifest_sha256": sha256_file(root / INPUT_PATHS["e16b_result"]),
            "contract_sha256": sha256_file(root / INPUT_PATHS["e16b_contract"]),
            "workflow_summary_sha256": predecessor["artifact_validation"][
                "workflow_summary_sha256"
            ],
            "required_status": predecessor["status"],
            "single_process_loader_promoted": True,
            "multi_process_sharing_previously_unmeasured": True,
        },
        "selected": predecessor_contract["selected"],
        "source": predecessor_contract["source"],
        "build": predecessor_contract["build"],
        "service": predecessor_contract["service"],
        "mechanism": {
            **predecessor_contract["mechanism"],
            "worker_count": 2,
            "worker_ports": [18081, 18082],
            "same_sidecar_inode_required": True,
            "summed_pss_is_primary_memory_metric": True,
            "per_process_rss_memory_claim_allowed": False,
            "simultaneous_measurement_barrier_required": True,
        },
        "request": predecessor_contract["request"],
        "execution": {
            "configurations": [
                "normal_repack_workers",
                "shared_sidecar_workers",
            ],
            "baseline_configuration": "normal_repack_workers",
            "candidate_configuration": "shared_sidecar_workers",
            "workers_per_group": 2,
            "repetitions_per_configuration": 4,
            "order": order,
            "order_design": "ABBA followed by BAAB",
            "fresh_worker_group_per_cell": True,
            "measured_worker_processes": 16,
            "measured_requests_per_group": 60,
            "total_measured_requests": 480,
            "one_time_sidecar_construction_process": 1,
            "delete_generated_raw_tensors_after_sidecar_verification": True,
            "delete_sidecar_after_all_groups_and_final_verification": True,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "required_logical_cpus": 4,
            "required_model_name": "Neoverse-N2",
            "required_common_cpu_features": ["asimd", "asimddp"],
            "minimum_tensor_count": 100,
            "minimum_packed_buffer_coverage_fraction": 0.99,
            "maximum_ready_ms_per_worker": 120000,
            "maximum_process_rss_kib": 7340032,
            "accepted_server_shell_exit_statuses": [0, 130],
            "http_status": 200,
            "termination_reason": "stop",
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "correct_per_worker": 23,
            "stable_predictions_across_all_workers": True,
            "loader_mapping_permissions": "r--s",
            "loader_mapping_offset_hex": "00100000",
            "maximum_measurement_start_skew_ms": 10.0,
            "maximum_throughput_coefficient_of_variation": 0.10,
            "minimum_aggregate_throughput_retention_ratio": 0.95,
            "maximum_median_http_latency_ratio": 1.05,
            "maximum_p95_http_latency_ratio": 1.05,
            "maximum_server_cpu_seconds_per_request_ratio": 1.03,
            "maximum_summed_post_workload_pss_ratio": 0.75,
            "minimum_summed_post_workload_pss_saved_kib": 1048576,
            "maximum_group_readiness_ratio": 0.80,
            "generated_binary_cleanup_required": True,
            "post_result_gate_change_permitted": False,
        },
        "promotion_rule": (
            "Admit multi-process physical sharing only if every worker has exact stable "
            "output, both loader mappings are read-only shared views of the same sidecar "
            "inode and offset, the barrier is synchronized, throughput/latency/CPU are "
            "retained, and summed PSS clears both the ratio and absolute saving gates."
        ),
        "negative_result_rule": (
            "Retain worker startup failure, memory pressure, mapping mismatch, quality "
            "drift, synchronization failure, performance regression, or insufficient "
            "summed-PSS saving without changing worker count, order, workload, or gates."
        ),
        "measurement_boundary": (
            "Each cell launches two fresh workers simultaneously on one four-core native "
            "GitHub Arm64 job. CPU counters and request time cover only the synchronized "
            "dual 30-task measured windows. Summed PSS is captured from both live PIDs "
            "after both workloads. Linux page cache is not flushed. Construction and "
            "verification are measured separately and excluded from steady state."
        ),
        "claim_boundary": (
            "E16c can establish only observed two-process physical sharing for one exact "
            "model, source diff, CPU identity, sidecar, and four-core native runner. It "
            "cannot claim per-process RSS reduction, cold-storage startup, more than two "
            "workers, other CPUs/models, energy, PMU, local-device, fleet, or cost."
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
