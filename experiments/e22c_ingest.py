#!/usr/bin/env python3
"""Independently validate the repeated Axion maximum-density comparison."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

try:
    from experiments.e22a_freeze import load_object, sha256_file
    from experiments.e22b_ingest import validate_valid_cell
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e22a_freeze import load_object, sha256_file
    from e22b_ingest import validate_valid_cell


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


def validate_contract(
    evidence_dir: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E22c-clean-maximum-density"
        or contract.get("scientific_boundary", {}).get("final_repeated_comparison")
        is not True
        or contract.get("matrix", {}).get("repetitions_per_mode") != 4
        or contract.get("advance", {}).get("post_result_gate_change_permitted")
        is not False
        or contract.get("fixed_memory", {}).get("cap_bytes") != 16_723_460_096
        or load_object(evidence_dir / "contract.json") != contract
    ):
        raise ValueError("E22c contract boundary differs")
    for relative, record in contract["inputs"].items():
        if sha256_file(root / relative) != record["sha256"]:
            raise ValueError(f"E22c input differs: {relative}")
    curve_path = root / contract["source_curve"]["manifest"]
    if sha256_file(curve_path) != contract["source_curve"]["manifest_sha256"]:
        raise ValueError("E22c source curve differs")
    return contract


def ingest(evidence_dir: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_contract(evidence_dir, contract_path, root)
    task_ids = [
        task["id"] for task in load_object(root / "experiments/e3_tasks.json")["tasks"]
    ]
    cells = []
    for cell_spec in contract["matrix"]["order"]:
        cell_dir = evidence_dir / "cells" / (
            f"{cell_spec['position']:02d}-{cell_spec['mode']}-w{cell_spec['workers']}"
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
            cell["mode"]: cell
            for cell in cells
            if cell["repetition"] == repetition
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
                "per_worker_throughput_ratio": shared[
                    "requests_per_second_per_worker"
                ]
                / normal["requests_per_second_per_worker"],
                "p95_latency_ratio": shared["p95_http_ms"]
                / normal["p95_http_ms"],
                "all_worker_readiness_ratio": shared["all_workers_ready_seconds"]
                / normal["all_workers_ready_seconds"],
                "throughput_per_gib_pss_ratio": shared["throughput_per_gib_pss"]
                / normal["throughput_per_gib_pss"],
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
        )
    }
    campaign = load_object(evidence_dir / "campaign-status.json")
    response_maps = [cell["response_map"] for cell in cells]
    expected_events = set(contract["pmu"]["events"])
    validity = {
        "campaign_completed_without_failed_cells": (
            campaign.get("status") == "completed_clean_maximum_density_campaign"
            and campaign.get("failed_cells") == 0
        ),
        "all_eight_cells_valid": len(cells) == 8 and all(cell["valid"] for cell in cells),
        "all_eight_cells_admitted": all(cell["admitted"] for cell in cells),
        "all_requests_succeeded": all(cell["request_failures"] == 0 for cell in cells),
        "all_reference_responses_exact": all(
            cell["reference_prediction_mismatches"] == 0 for cell in cells
        ),
        "all_response_maps_identical": all(
            response_map == response_maps[0] for response_map in response_maps[1:]
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
    }
    advance = contract["advance"]
    gates = {
        "valid_repeated_comparison": all(validity.values()),
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
        "each_paired_p95_bounded": ratio_distributions["p95_latency_ratio"][
            "maximum"
        ]
        <= advance["maximum_each_paired_p95_latency_ratio"],
        "median_per_worker_throughput": ratio_distributions[
            "per_worker_throughput_ratio"
        ]["median"]
        >= advance["minimum_median_per_worker_throughput_ratio"],
        "median_throughput_per_gib_pss": ratio_distributions[
            "throughput_per_gib_pss_ratio"
        ]["median"]
        >= advance["minimum_median_throughput_per_gib_pss_ratio"],
        "median_readiness_bounded": ratio_distributions[
            "all_worker_readiness_ratio"
        ]["median"]
        <= advance["maximum_median_all_worker_readiness_ratio"],
        "throughput_dispersion_bounded": all(
            mode_distributions[mode]["requests_per_second"][
                "coefficient_of_variation"
            ]
            <= advance["maximum_mode_throughput_coefficient_of_variation"]
            for mode in ("normal", "shared")
        ),
        "density_gain": (
            contract["matrix"]["shared_workers"]
            - contract["matrix"]["normal_workers"]
            >= advance["density_worker_gain"]
        ),
    }
    failed = sorted(name for name, passed in gates.items() if not passed)
    promoted = not failed
    receipt = load_object(evidence_dir / "product/sidecar-receipt.json")
    return {
        "schema_version": 1,
        "experiment_id": contract["experiment_id"],
        "status": (
            "valid_repeated_maximum_density_promoted"
            if promoted
            else "valid_repeated_maximum_density_not_promoted"
        ),
        "decision": (
            "promote_native_axion_fixed_memory_result"
            if promoted
            else "retain_and_narrow_native_axion_claim"
        ),
        "contract_sha256": sha256_file(contract_path),
        "repository_commit": (evidence_dir / "repository-commit.txt")
        .read_text(encoding="utf-8")
        .strip(),
        "source_curve": contract["source_curve"],
        "host": contract["host"],
        "cost_control": contract["cost_control"],
        "fixed_memory": contract["fixed_memory"],
        "claim_boundary": contract["scientific_boundary"],
        "construction": receipt["construction"],
        "storage": receipt["storage"],
        "cells": cells,
        "pairs": pairs,
        "mode_distributions": mode_distributions,
        "ratio_distributions": ratio_distributions,
        "validity_gates": validity,
        "advance_gates": gates,
        "failed_advance_gates": failed,
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
