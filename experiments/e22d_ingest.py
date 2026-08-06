#!/usr/bin/env python3
"""Independently validate the second-host Axion density replication."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

try:
    from experiments.e22a_freeze import load_object, sha256_file
    from experiments.e22b_ingest import validate_nonvalid_cell, validate_valid_cell
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e22a_freeze import load_object, sha256_file
    from e22b_ingest import validate_nonvalid_cell, validate_valid_cell


def distribution(values: list[float]) -> dict[str, float]:
    mean = statistics.fmean(values)
    standard_deviation = statistics.pstdev(values)
    return {
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
        "mean": mean,
        "population_standard_deviation": standard_deviation,
        "coefficient_of_variation": standard_deviation / mean,
    }


def vmstat(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] in {"oom_kill", "pswpin", "pswpout"}:
            values[fields[0]] = int(fields[1])
    return values


def validate_contract(
    evidence_dir: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E22d-independent-host-density-replication"
        or contract.get("advance", {}).get(
            "readiness_is_disclosure_only_not_a_replication_gate"
        )
        is not True
        or contract.get("advance", {}).get("post_result_gate_change_permitted")
        is not False
        or contract.get("fixed_memory", {}).get("cap_bytes") != 16_723_460_096
        or load_object(evidence_dir / "contract.json") != contract
    ):
        raise ValueError("E22d contract boundary differs")
    for relative, record in contract["inputs"].items():
        if sha256_file(root / relative) != record["sha256"]:
            raise ValueError(f"E22d input differs: {relative}")
    source_path = root / contract["source_result"]["manifest"]
    if sha256_file(source_path) != contract["source_result"]["manifest_sha256"]:
        raise ValueError("E22d source result differs")
    return contract


def validate_host(evidence_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    host_dir = evidence_dir / "host-preflight"
    host = load_object(host_dir / "host-preflight.json")
    cloud = load_object(host_dir / "cloud-instance.json")
    required = contract["host_requirements"]
    machine_type = str(host.get("machine_type", "")).split("/")[-1]
    cloud_machine_type = str(cloud.get("machineType", "")).split("/")[-1]
    duration_seconds = int(
        cloud.get("scheduling", {}).get("maxRunDuration", {}).get("seconds", 0)
    )
    checks = {
        "different_instance": host.get("instance_id")
        != contract["source_result"]["instance_id"],
        "cloud_identity_matches": str(cloud.get("id")) == host.get("instance_id"),
        "machine_type_matches": machine_type
        == required["machine_type_basename"]
        == cloud_machine_type,
        "architecture_matches": host.get("architecture") == required["architecture"],
        "cpu_model_matches": host.get("cpu_model") == required["cpu_model"],
        "topology_matches": host.get("logical_cpus") == required["logical_cpus"]
        and host.get("threads_per_core") == required["threads_per_core"],
        "fixed_memory_matches": host.get("mem_total_bytes")
        == required["mem_total_bytes"]
        and host.get("swap_total_bytes") == required["swap_total_bytes"],
        "standard_pmu_available": host.get("pmu", {}).get("perf_stat_available")
        is True,
        "automatic_delete_bounded": 0
        < duration_seconds
        <= required["automatic_delete_after_seconds_at_most"]
        and cloud.get("scheduling", {}).get("instanceTerminationAction")
        == required["instance_termination_action"],
        "boot_disks_auto_delete": bool(cloud.get("disks"))
        and all(disk.get("autoDelete") is True for disk in cloud["disks"]),
    }
    if not all(checks.values()):
        raise ValueError(f"E22d host differs: {checks}")
    return {
        **host,
        "cloud_creation_timestamp": cloud.get("creationTimestamp"),
        "cloud_instance_sha256": sha256_file(host_dir / "cloud-instance.json"),
        "host_preflight_sha256": sha256_file(host_dir / "host-preflight.json"),
        "host_inventory_sha256": sha256_file(host_dir / "file-inventory-sha256.txt"),
        "automatic_delete_after_seconds": duration_seconds,
        "on_host_maintenance": cloud.get("scheduling", {}).get("onHostMaintenance"),
        "host_validity_gates": checks,
    }


def ingest(evidence_dir: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_contract(evidence_dir, contract_path, root)
    host = validate_host(evidence_dir, contract)
    task_ids = [
        task["id"] for task in load_object(root / "experiments/e3_tasks.json")["tasks"]
    ]
    cells = []
    for cell_spec in contract["matrix"]["order"]:
        cell_dir = (
            evidence_dir
            / "cells"
            / (
                f"{cell_spec['position']:02d}-{cell_spec['mode']}-w{cell_spec['workers']}"
            )
        )
        status = load_object(cell_dir / "cell-status.json")
        if status.get("status") != "valid_fixed_memory_curve_cell":
            raise ValueError(f"{cell_dir.name} is not a valid repeated cell")
        cell = validate_valid_cell(
            cell_dir, contract=contract, cell=cell_spec, task_ids=task_ids
        )
        cell["repetition"] = cell_spec["repetition"]
        cells.append(cell)

    grouped = {
        mode: [cell for cell in cells if cell["mode"] == mode]
        for mode in ("normal", "shared")
    }
    pairs = []
    for repetition in range(1, 5):
        indexed = {
            cell["mode"]: cell for cell in cells if cell["repetition"] == repetition
        }
        normal = indexed["normal"]
        shared = indexed["shared"]
        pairs.append(
            {
                "repetition": repetition,
                "normal_position": normal["position"],
                "shared_position": shared["position"],
                "aggregate_throughput_ratio": shared["requests_per_second"]
                / normal["requests_per_second"],
                "per_worker_throughput_ratio": shared["requests_per_second_per_worker"]
                / normal["requests_per_second_per_worker"],
                "p95_latency_ratio": shared["p95_http_ms"] / normal["p95_http_ms"],
                "all_worker_readiness_ratio": shared["all_workers_ready_seconds"]
                / normal["all_workers_ready_seconds"],
                "throughput_per_gib_pss_ratio": shared["throughput_per_gib_pss"]
                / normal["throughput_per_gib_pss"],
                "summed_pss_saved_fraction": 1.0
                - shared["summed_pss_kib"] / normal["summed_pss_kib"],
            }
        )

    mode_distributions = {
        mode: {
            metric: distribution([float(cell[metric]) for cell in mode_cells])
            for metric in (
                "requests_per_second",
                "requests_per_second_per_worker",
                "p95_http_ms",
                "summed_pss_kib",
                "throughput_per_gib_pss",
                "all_workers_ready_seconds",
                "mem_available_bytes",
            )
        }
        for mode, mode_cells in grouped.items()
    }
    ratio_distributions = {
        metric: distribution([float(pair[metric]) for pair in pairs])
        for metric in (
            "aggregate_throughput_ratio",
            "per_worker_throughput_ratio",
            "p95_latency_ratio",
            "all_worker_readiness_ratio",
            "throughput_per_gib_pss_ratio",
            "summed_pss_saved_fraction",
        )
    }

    boundary_spec = contract["matrix"]["normal_eight_boundary"]
    boundary_dir = evidence_dir / "cells/09-normal-w8"
    boundary = validate_nonvalid_cell(boundary_dir, boundary_spec)
    before = vmstat(boundary_dir / "host-state-before.txt")
    after = vmstat(boundary_dir / "host-state-after.txt")
    boundary["oom_kill_delta"] = after.get("oom_kill", 0) - before.get("oom_kill", 0)
    boundary["pswpin_delta"] = after.get("pswpin", 0) - before.get("pswpin", 0)
    boundary["pswpout_delta"] = after.get("pswpout", 0) - before.get("pswpout", 0)

    source = load_object(root / contract["source_result"]["manifest"])
    source_maps = [cell["response_map"] for cell in source["cells"]]
    response_maps = [cell["response_map"] for cell in cells]
    campaign = load_object(evidence_dir / "campaign-status.json")
    repeated_campaign = load_object(evidence_dir / "repeated-campaign-status.json")
    expected_events = set(contract["pmu"]["events"])
    validity = {
        "campaign_completed": campaign.get("status")
        == "completed_independent_host_density_replication"
        and campaign.get("repeated_campaign_exit_status") == 0,
        "repeated_campaign_completed": repeated_campaign.get("status")
        == "completed_clean_maximum_density_campaign"
        and repeated_campaign.get("failed_cells") == 0,
        "all_eight_cells_valid_and_admitted": len(cells) == 8
        and all(cell["valid"] and cell["admitted"] for cell in cells),
        "all_requests_succeeded": all(cell["request_failures"] == 0 for cell in cells),
        "all_reference_responses_exact": all(
            cell["reference_prediction_mismatches"] == 0 for cell in cells
        ),
        "all_response_maps_identical_across_cells_and_hosts": all(
            item == response_maps[0] for item in response_maps[1:] + source_maps
        ),
        "all_shared_mappings_verified": all(
            cell["shared_mapping_count"] == 8 for cell in grouped["shared"]
        ),
        "all_pmu_events_counted": all(
            set(cell["pmu_events"]) == expected_events
            and all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value > 0
                for value in cell["pmu_events"].values()
            )
            for cell in cells
        ),
        "normal_eight_is_resource_boundary": boundary["started"]
        and not boundary["valid"]
        and boundary["resource_boundary_evidence"]
        and boundary["oom_kill_delta"]
        >= contract["advance"]["minimum_normal_eight_oom_kill_delta"]
        and boundary["pswpin_delta"] == 0
        and boundary["pswpout_delta"] == 0,
    }
    advance = contract["advance"]
    gates = {
        "valid_independent_host_replication": all(validity.values()),
        "median_aggregate_throughput": ratio_distributions[
            "aggregate_throughput_ratio"
        ]["median"]
        >= advance["minimum_median_aggregate_throughput_ratio"],
        "each_paired_aggregate_throughput": ratio_distributions[
            "aggregate_throughput_ratio"
        ]["minimum"]
        >= advance["minimum_each_paired_aggregate_throughput_ratio"],
        "median_p95_bounded": ratio_distributions["p95_latency_ratio"]["median"]
        <= advance["maximum_median_p95_latency_ratio"],
        "each_paired_p95_bounded": ratio_distributions["p95_latency_ratio"]["maximum"]
        <= advance["maximum_each_paired_p95_latency_ratio"],
        "median_per_worker_throughput": ratio_distributions[
            "per_worker_throughput_ratio"
        ]["median"]
        >= advance["minimum_median_per_worker_throughput_ratio"],
        "median_throughput_per_gib_pss": ratio_distributions[
            "throughput_per_gib_pss_ratio"
        ]["median"]
        >= advance["minimum_median_throughput_per_gib_pss_ratio"],
        "median_summed_pss_saved": ratio_distributions["summed_pss_saved_fraction"][
            "median"
        ]
        >= advance["minimum_median_summed_pss_saved_fraction"],
        "throughput_dispersion_bounded": all(
            mode_distributions[mode]["requests_per_second"]["coefficient_of_variation"]
            <= advance["maximum_mode_throughput_coefficient_of_variation"]
            for mode in ("normal", "shared")
        ),
        "density_gain": contract["matrix"]["shared_workers"]
        - contract["matrix"]["normal_workers"]
        >= advance["density_worker_gain"],
    }
    failed = sorted(name for name, passed in gates.items() if not passed)
    receipt = load_object(evidence_dir / "product/sidecar-receipt.json")
    return {
        "schema_version": 1,
        "experiment_id": contract["experiment_id"],
        "status": (
            "valid_independent_host_replication_promoted"
            if not failed
            else "valid_independent_host_replication_not_promoted"
            if all(validity.values())
            else "invalid_independent_host_replication"
        ),
        "decision": (
            "promote_two_independent_axion_instance_density_result"
            if not failed
            else "retain_e22c_single_instance_result"
        ),
        "contract_sha256": sha256_file(contract_path),
        "repository_commit": (evidence_dir / "repository-commit.txt")
        .read_text(encoding="utf-8")
        .strip(),
        "source_result": contract["source_result"],
        "host": host,
        "cost_control": contract["cost_control"],
        "fixed_memory": contract["fixed_memory"],
        "claim_boundary": contract["scientific_boundary"],
        "construction": receipt["construction"],
        "storage": receipt["storage"],
        "cells": cells,
        "normal_eight_resource_boundary": boundary,
        "pairs": pairs,
        "mode_distributions": mode_distributions,
        "ratio_distributions": ratio_distributions,
        "validity_gates": validity,
        "advance_gates": gates,
        "failed_advance_gates": failed,
        "readiness_decision": "disclosed_only_not_rerolled",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = ingest(
        arguments.evidence_dir.resolve(),
        arguments.contract.resolve(),
        arguments.root.resolve(),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "failed_advance_gates": result["failed_advance_gates"],
                "status": result["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
