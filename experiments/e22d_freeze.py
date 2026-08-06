#!/usr/bin/env python3
"""Freeze an independent-host replication of the final Axion density result."""

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
    "experiments/e22b_cell.sh",
    "experiments/e22b_host_preflight.sh",
    "experiments/e22b_ingest.py",
    "experiments/e22b_probe.py",
    "experiments/e22c_campaign.sh",
    "experiments/e22c_contract.json",
    "experiments/e22d_campaign.sh",
    "experiments/e22d_freeze.py",
    "experiments/e22d_ingest.py",
    "experiments/e22d_prepare_host.sh",
    "results/manifests/e3f-30656151957.json",
    "results/manifests/e16c-30851609576.json",
    "results/manifests/e22c-axion-20260806.json",
    "pareto64/certificate.py",
    "pareto64/cli.py",
    "pareto64/deploy.py",
    "pareto64/gateway.py",
    "pareto64/repack.py",
    "pareto64/sidecar.py",
)


def build_contract(root: Path) -> dict[str, Any]:
    source_manifest_path = root / "results/manifests/e22c-axion-20260806.json"
    source = load_object(source_manifest_path)
    predecessor = load_object(root / "experiments/e22c_contract.json")
    if (
        source.get("status") != "valid_repeated_maximum_density_not_promoted"
        or source.get("decision") != "retain_and_narrow_native_axion_claim"
        or source.get("claim_decision", {}).get(
            "repeated_steady_state_fixed_memory_result_valid"
        )
        is not True
        or source.get("failed_advance_gates") != ["median_readiness_bounded"]
        or predecessor.get("experiment_id") != "E22c-clean-maximum-density"
        or predecessor.get("fixed_memory", {}).get("cap_bytes") != 16_723_460_096
    ):
        raise ValueError("E22d requires the retained E22c steady-state result")
    order = [dict(cell) for cell in predecessor["matrix"]["order"]]
    return {
        "schema_version": 1,
        "experiment_id": "E22d-independent-host-density-replication",
        "created_utc": "2026-08-06",
        "stage": "independent stable Arm host replication",
        "question": (
            "Does the exact normal-six/shared-eight fixed-memory result and "
            "normal-eight admission boundary reproduce on a second fresh Google "
            "Axion instance without treating readiness as a rerolled gate?"
        ),
        "source_result": {
            "manifest": "results/manifests/e22c-axion-20260806.json",
            "manifest_sha256": sha256_file(source_manifest_path),
            "instance_id": source["host"]["instance_id"],
            "median_aggregate_throughput_ratio": source["ratio_distributions"][
                "aggregate_throughput_ratio"
            ]["median"],
            "median_summed_pss_normal_kib": source["mode_distributions"]["normal"][
                "summed_pss_kib"
            ]["median"],
            "median_summed_pss_shared_kib": source["mode_distributions"]["shared"][
                "summed_pss_kib"
            ]["median"],
            "failed_gate": "median_readiness_bounded",
            "raw_archive_name": source["retention_validation"]["archive_name"],
            "raw_archive_sha256": source["retention_validation"]["archive_sha256"],
            "raw_archive_size_bytes": source["retention_validation"][
                "archive_size_bytes"
            ],
            "raw_archive_url": (
                "https://github.com/Arshgill01/Arm/releases/download/"
                "e22-axion-evidence-20260806/"
                + source["retention_validation"]["archive_name"]
            ),
        },
        "host_requirements": {
            "provider": "Google Cloud Compute Engine",
            "machine_type_basename": "c4a-highcpu-8",
            "cpu_model": "Neoverse-V2",
            "architecture": "aarch64",
            "logical_cpus": 8,
            "threads_per_core": 1,
            "mem_total_bytes": 16_723_460_096,
            "swap_total_bytes": 0,
            "provisioning_model": "STANDARD",
            "pmu_tracking_type": "standard",
            "perf_event_paranoid_maximum": 1,
            "different_instance_id_from_source": True,
            "automatic_delete_after_seconds_at_most": 14_400,
            "instance_termination_action": "DELETE",
        },
        "cost_control": {
            "user_authorized_ceiling_usd": 40.0,
            "experiment_maximum_usd": 3.0,
            "estimated_compute_rate_usd_per_hour": 0.30296,
            "instance_maximum_runtime_hours": 4.0,
            "estimated_maximum_compute_usd": 1.21184,
            "estimate_boundary": (
                "Published c4a-highcpu-8 estimate retained from E22c; excludes a "
                "small prorated boot disk charge and is not a billing claim."
            ),
            "instance_termination_action": "DELETE",
        },
        "fixed_memory": predecessor["fixed_memory"],
        "selected": predecessor["selected"],
        "source": predecessor["source"],
        "build": predecessor["build"],
        "service": predecessor["service"],
        "workload": predecessor["workload"],
        "pmu": predecessor["pmu"],
        "matrix": {
            "repetitions_per_mode": 4,
            "normal_workers": 6,
            "shared_workers": 8,
            "order": order,
            "order_rationale": predecessor["matrix"]["order_rationale"],
            "inter_cell_idle_seconds": 5,
            "warm_same_host_page_cache": True,
            "drop_caches": False,
            "normal_eight_boundary": {
                "position": 9,
                "mode": "normal",
                "workers": 8,
                "runs_after_repeated_cells": True,
                "requires_every_normal_six_cell_admitted": True,
            },
        },
        "advance": {
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "response_differences_between_all_cells_and_hosts": 0,
            "all_eight_repeated_cells_valid_and_admitted": True,
            "normal_eight_fails_as_a_measured_resource_boundary": True,
            "minimum_normal_eight_oom_kill_delta": 1,
            "minimum_median_aggregate_throughput_ratio": 1.25,
            "minimum_each_paired_aggregate_throughput_ratio": 1.20,
            "maximum_median_p95_latency_ratio": 1.15,
            "maximum_each_paired_p95_latency_ratio": 1.20,
            "minimum_median_per_worker_throughput_ratio": 0.80,
            "minimum_median_throughput_per_gib_pss_ratio": 2.50,
            "minimum_median_summed_pss_saved_fraction": 0.55,
            "maximum_mode_throughput_coefficient_of_variation": 0.10,
            "density_worker_gain": 2,
            "all_shared_workers_map_one_verified_inode_read_only": True,
            "all_pmu_events_counted": True,
            "readiness_is_disclosure_only_not_a_replication_gate": True,
            "post_result_gate_change_permitted": False,
        },
        "scientific_boundary": {
            "independent_instance_replication": True,
            "same_provider_machine_class": True,
            "same_exact_model_runtime_product_and_workload": True,
            "runtime_recovered_from_hash_bound_public_e22c_bundle": True,
            "warm_same_host_page_cache_only": True,
            "steady_state_density_claim_only": True,
            "readiness_reroll_permitted": False,
            "cold_cache_claim_permitted": False,
            "energy_claim_permitted": False,
            "billing_claim_permitted": False,
            "fleet_or_other_machine_class_claim_permitted": False,
            "broader_microarchitectural_causality_permitted": False,
            "perf_event_paranoid_adjustment_disclosed": True,
        },
        "successor_rule": (
            "Promote cross-instance replication only if every frozen validity and "
            "advance gate passes. Readiness is always reported but cannot change the "
            "E22c lifecycle decision. Stop after this one independent instance."
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
