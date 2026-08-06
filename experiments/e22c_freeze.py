#!/usr/bin/env python3
"""Freeze the clean repeated Axion maximum-density comparison."""

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
    "experiments/e3_tasks.json",
    "experiments/e22b_contract.json",
    "experiments/e22b_cell.sh",
    "experiments/e22b_ingest.py",
    "experiments/e22b_probe.py",
    "experiments/e22c_freeze.py",
    "experiments/e22c_campaign.sh",
    "experiments/e22c_ingest.py",
    "results/manifests/e3f-30656151957.json",
    "results/manifests/e16c-30851609576.json",
    "results/manifests/e22b-axion-20260806.json",
    "pareto64/certificate.py",
    "pareto64/cli.py",
    "pareto64/deploy.py",
    "pareto64/gateway.py",
    "pareto64/repack.py",
    "pareto64/sidecar.py",
)


def build_contract(root: Path) -> dict[str, Any]:
    curve = load_object(root / "results/manifests/e22b-axion-20260806.json")
    predecessor = load_object(root / "experiments/e22b_contract.json")
    normal = curve.get("maximum_admitted", {}).get("normal", {})
    shared = curve.get("maximum_admitted", {}).get("shared", {})
    if (
        curve.get("status") != "valid_fixed_memory_curve_promoted"
        or curve.get("decision")
        != "freeze_clean_repeated_maximum_density_comparison"
        or curve.get("failed_advance_gates") != []
        or normal.get("worker_count") != 6
        or shared.get("worker_count") != 8
        or curve.get("normal_eight_resource_boundary", {}).get("oom_kill_delta") != 1
        or predecessor.get("experiment_id") != "E22b-fixed-memory-curve"
        or predecessor.get("fixed_memory", {}).get("cap_bytes") != 16_723_460_096
    ):
        raise ValueError("E22c requires the promoted retained E22b boundary")
    order = [
        {"position": 1, "repetition": 1, "mode": "normal", "workers": 6},
        {"position": 2, "repetition": 1, "mode": "shared", "workers": 8},
        {"position": 3, "repetition": 2, "mode": "shared", "workers": 8},
        {"position": 4, "repetition": 2, "mode": "normal", "workers": 6},
        {"position": 5, "repetition": 3, "mode": "shared", "workers": 8},
        {"position": 6, "repetition": 3, "mode": "normal", "workers": 6},
        {"position": 7, "repetition": 4, "mode": "normal", "workers": 6},
        {"position": 8, "repetition": 4, "mode": "shared", "workers": 8},
    ]
    return {
        "schema_version": 1,
        "experiment_id": "E22c-clean-maximum-density",
        "created_utc": "2026-08-06",
        "stage": "final stable Arm fixed-memory comparison",
        "question": (
            "Does the E22b maximum-density result repeat cleanly when normal-six "
            "and shared-eight are measured four times in an order-balanced sequence?"
        ),
        "scientific_boundary": {
            **predecessor["scientific_boundary"],
            "final_repeated_comparison": True,
            "order_balanced": True,
            "e22b_cell_schema_reused_without_behavior_change": True,
        },
        "host": predecessor["host"],
        "cost_control": predecessor["cost_control"],
        "fixed_memory": predecessor["fixed_memory"],
        "source_curve": {
            "manifest": "results/manifests/e22b-axion-20260806.json",
            "manifest_sha256": sha256_file(
                root / "results/manifests/e22b-axion-20260806.json"
            ),
            "raw_archive_name": curve["retention_validation"]["archive_name"],
            "raw_archive_sha256": curve["retention_validation"]["archive_sha256"],
            "normal_maximum_workers": normal["worker_count"],
            "shared_maximum_workers": shared["worker_count"],
            "single_curve_throughput_ratio": curve[
                "fixed_memory_aggregate_throughput_ratio"
            ],
        },
        "selected": predecessor["selected"],
        "source": predecessor["source"],
        "build": predecessor["build"],
        "service": predecessor["service"],
        "matrix": {
            "repetitions_per_mode": 4,
            "normal_workers": 6,
            "shared_workers": 8,
            "order": order,
            "order_rationale": (
                "NSSNSNNS places each mode twice in the first and second half, "
                "pairs each repetition once, and gives each mode two first-in-pair runs."
            ),
            "inter_cell_idle_seconds": 5,
            "warm_same_host_page_cache": True,
            "drop_caches": False,
        },
        "workload": predecessor["workload"],
        "pmu": predecessor["pmu"],
        "advance": {
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "response_differences_between_all_cells": 0,
            "all_eight_cells_valid_and_admitted": True,
            "minimum_median_aggregate_throughput_ratio": 1.25,
            "minimum_each_paired_aggregate_throughput_ratio": 1.20,
            "maximum_median_p95_latency_ratio": 1.15,
            "maximum_each_paired_p95_latency_ratio": 1.20,
            "minimum_median_per_worker_throughput_ratio": 0.80,
            "minimum_median_throughput_per_gib_pss_ratio": 2.50,
            "maximum_median_all_worker_readiness_ratio": 2.00,
            "maximum_mode_throughput_coefficient_of_variation": 0.10,
            "density_worker_gain": 2,
            "all_shared_workers_map_one_verified_inode_read_only": True,
            "all_pmu_events_counted": True,
            "post_result_gate_change_permitted": False,
        },
        "successor_rule": (
            "If every gate passes, promote the native Axion fixed-memory result as "
            "the primary Arm-specific submission claim. Otherwise retain E22c and "
            "narrow the claim to the strongest repeated boundary that was predeclared."
        ),
        "inputs": {path: {"sha256": sha256_file(root / path)} for path in INPUT_PATHS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    contract = build_contract(arguments.root.resolve())
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
