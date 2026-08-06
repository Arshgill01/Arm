#!/usr/bin/env python3
"""Freeze the stable Axion fixed-memory sidecar scaling curve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e22a_freeze import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e22a_freeze import load_object, sha256_file


INPUT_PATHS = (
    "experiments/e16c_contract.json",
    "results/manifests/e16c-30851609576.json",
    "experiments/e3_tasks.json",
    "results/manifests/e3f-30656151957.json",
    "experiments/e3f_models.json",
    "experiments/e22a_probe.py",
    "experiments/e22b_host_preflight.sh",
    "experiments/e22b_freeze.py",
    "experiments/e22b_campaign.sh",
    "experiments/e22b_cell.sh",
    "experiments/e22b_ingest.py",
    "experiments/e22b_probe.py",
    "pareto64/certificate.py",
    "pareto64/cli.py",
    "pareto64/deploy.py",
    "pareto64/gateway.py",
    "pareto64/repack.py",
    "pareto64/sidecar.py",
)


def validate_host(
    host_dir: Path, cloud_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    host = load_object(host_dir / "host-preflight.json")
    cloud = load_object(cloud_path)
    scheduling = cloud.get("scheduling", {})
    if (
        host.get("status") != "valid_stable_axion_host_preflight"
        or host.get("architecture") != "aarch64"
        or host.get("cpu_model") != "Neoverse-V2"
        or host.get("logical_cpus") != 8
        or host.get("threads_per_core") != 1
        or host.get("mem_total_bytes") != 16_723_460_096
        or host.get("swap_total_bytes") != 0
        or host.get("pmu", {}).get("requested_tracking_type") != "standard"
        or host.get("pmu", {}).get("perf_stat_available") is not True
        or cloud.get("id") != host.get("instance_id")
        or cloud.get("cpuPlatform") != "Google Axion"
        or not str(cloud.get("machineType", "")).endswith("/c4a-highcpu-8")
        or cloud.get("status") != "RUNNING"
        or scheduling.get("provisioningModel") != "STANDARD"
        or scheduling.get("preemptible") is not False
        or scheduling.get("instanceTerminationAction") != "DELETE"
        or scheduling.get("maxRunDuration", {}).get("seconds") != "21600"
    ):
        raise ValueError("E22b stable host preflight differs")
    return host, cloud


def build_contract(
    root: Path, host_dir: Path, cloud_instance_path: Path
) -> dict[str, Any]:
    predecessor = load_object(root / "experiments/e16c_contract.json")
    evidence = load_object(root / "results/manifests/e16c-30851609576.json")
    if (
        predecessor.get("experiment_id") != "E16c"
        or evidence.get("status") != "valid_shared_sidecar_workers_promoted"
        or evidence.get("promoted") is not True
    ):
        raise ValueError("E22b requires the promoted E16c mechanism boundary")
    host, cloud = validate_host(host_dir, cloud_instance_path)
    order = [
        {"position": 1, "mode": "normal", "workers": 1},
        {"position": 2, "mode": "shared", "workers": 1},
        {"position": 3, "mode": "shared", "workers": 2},
        {"position": 4, "mode": "normal", "workers": 2},
        {"position": 5, "mode": "normal", "workers": 4},
        {"position": 6, "mode": "shared", "workers": 4},
        {"position": 7, "mode": "shared", "workers": 5},
        {"position": 8, "mode": "normal", "workers": 5},
        {"position": 9, "mode": "normal", "workers": 6},
        {"position": 10, "mode": "shared", "workers": 6},
        {"position": 11, "mode": "shared", "workers": 8},
        {"position": 12, "mode": "normal", "workers": 8},
    ]
    return {
        "schema_version": 1,
        "experiment_id": "E22b-fixed-memory-curve",
        "created_utc": "2026-08-06",
        "stage": "stable Arm fixed-physical-memory density curve",
        "question": (
            "How many exact one-thread workers and how much aggregate throughput "
            "does one verified shared Arm packed-weight image admit on the same "
            "16,723,460,096-byte Axion node as ordinary private repacking?"
        ),
        "scientific_boundary": {
            "preflight_only": False,
            "final_performance_claim_permitted_if_all_gates_pass": True,
            "fixed_memory_cap_frozen_before_measurement": True,
            "host_is_stable_performance_authority": True,
            "host_class": "Google Axion c4a-highcpu-8, Neoverse V2",
            "warm_same_host_page_cache_only": True,
            "cold_page_cache_claim_permitted": False,
            "energy_claim_permitted": False,
            "billing_cost_claim_permitted": False,
            "pmu_mechanism_claim_limited_to_counted_events": True,
        },
        "host": {
            **host,
            "host_preflight_sha256": sha256_file(host_dir / "host-preflight.json"),
            "host_inventory_sha256": sha256_file(
                host_dir / "file-inventory-sha256.txt"
            ),
            "cloud_instance_sha256": sha256_file(cloud_instance_path),
            "cloud_creation_timestamp": cloud["creationTimestamp"],
            "automatic_delete_after_seconds": 21_600,
            "on_host_maintenance": cloud["scheduling"]["onHostMaintenance"],
        },
        "cost_control": {
            "authorized_maximum_usd": 10.0,
            "instance_maximum_runtime_hours": 6.0,
            "instance_termination_action": "DELETE",
            "estimated_compute_rate_usd_per_hour": 0.30296,
            "estimated_maximum_compute_usd": 1.81776,
            "estimate_source": "https://cloud.google.com/products/axion",
            "estimate_boundary": (
                "Eight times the published starting c4a-highcpu hourly rate; "
                "not a bill, cost claim, or commitment price."
            ),
        },
        "fixed_memory": {
            "cap_source": "physical /proc/meminfo MemTotal on the frozen host",
            "cap_bytes": host["mem_total_bytes"],
            "minimum_mem_available_bytes": 536_870_912,
            "swap_total_bytes": 0,
            "admitted_cell_requires": [
                "valid deployment lifecycle and every worker ready",
                "all exact requests succeed with the reference response map",
                "zero OOM kills and zero swap",
                "MemAvailable remains at least 536,870,912 bytes after workload",
            ],
        },
        "source_artifact": {
            "repository": "Arshgill01/Arm",
            "run_id": "30851609576",
            "name": "e16c-shared-repack-arena-30851609576-1",
        },
        "selected": predecessor["selected"],
        "source": predecessor["source"],
        "build": predecessor["build"],
        "service": {
            **predecessor["service"],
            "threads": 1,
            "threads_batch": 1,
            "reason_for_thread_count": (
                "One matched worker thread per physical V2 core exposes the "
                "maximum eight-worker density without oversubscribing inference."
            ),
        },
        "matrix": {
            "modes": ["normal", "shared"],
            "worker_counts": [1, 2, 4, 5, 6, 8],
            "repetitions": 1,
            "order": order,
            "normal_eight_condition": (
                "Run only if normal six is valid, has zero OOM kills, and retains "
                "the frozen minimum MemAvailable; otherwise retain a skipped cell."
            ),
            "shared_eight_required": True,
            "full_quality_trace_per_started_worker": True,
            "gateway_smoke_after_direct_measurement": True,
            "clean_final_rerun_required_if_promoted": True,
        },
        "workload": {
            "tasks": 30,
            "warmup_task_ids": ["arithmetic-02", "logic-01"],
            "maximum_output_tokens": 8,
            "seed": 424242,
            "timeout_seconds": 90,
            "prompt_cache": True,
            "requests_per_worker": 30,
            "client_concurrency_per_worker": 1,
        },
        "pmu": {
            "tracking_type": "standard",
            "events": [
                "cpu_cycles",
                "inst_retired",
                "l1d_cache",
                "l1d_cache_refill",
                "l2d_cache",
            ],
            "scope": "worker processes during only the exact measured trace",
            "density_result_blocked_if_missing": True,
            "broader_microarchitectural_causality_permitted": False,
        },
        "advance": {
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "response_differences_between_modes": 0,
            "minimum_shared_throughput_ratio_at_common_count": 0.90,
            "maximum_shared_p95_ratio_at_common_count": 1.15,
            "minimum_pss_saved_kib_at_four_workers": 5_242_880,
            "maximum_shared_four_readiness_ratio": 1.50,
            "minimum_density_worker_gain": 2,
            "minimum_fixed_memory_aggregate_throughput_ratio": 1.25,
            "minimum_shared_max_per_worker_throughput_ratio_to_normal_one": 0.80,
            "shared_eight_workers_admitted": True,
            "all_shared_workers_map_one_verified_inode_read_only": True,
            "all_pmu_events_counted": True,
            "post_result_gate_change_permitted": False,
        },
        "successor_rule": (
            "If every gate passes, freeze and run a clean repeated comparison of "
            "the highest admitted normal and shared counts. Otherwise retain the "
            "curve and demote or narrow the fixed-memory claim."
        ),
        "inputs": {path: {"sha256": sha256_file(root / path)} for path in INPUT_PATHS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--host-preflight", type=Path, required=True)
    parser.add_argument("--cloud-instance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    contract = build_contract(
        arguments.root.resolve(),
        arguments.host_preflight.resolve(),
        arguments.cloud_instance.resolve(),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
