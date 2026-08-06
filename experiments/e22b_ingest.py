#!/usr/bin/env python3
"""Independently validate the stable Axion fixed-memory density curve."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e22a_freeze import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e22a_freeze import load_object, sha256_file


def finite_positive(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def validate_contract(
    evidence_dir: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E22b-fixed-memory-curve"
        or contract.get("scientific_boundary", {}).get(
            "fixed_memory_cap_frozen_before_measurement"
        )
        is not True
        or contract.get("scientific_boundary", {}).get(
            "host_is_stable_performance_authority"
        )
        is not True
        or contract.get("advance", {}).get("post_result_gate_change_permitted")
        is not False
        or contract.get("fixed_memory", {}).get("cap_bytes") != 16_723_460_096
    ):
        raise ValueError("E22b contract boundary differs")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("retained E22b contract differs")
    for relative, record in contract["inputs"].items():
        if sha256_file(root / relative) != record["sha256"]:
            raise ValueError(f"E22b input differs: {relative}")
    host = load_object(evidence_dir / "host-preflight/host-preflight.json")
    if (
        host.get("instance_id") != contract["host"]["instance_id"]
        or sha256_file(evidence_dir / "host-preflight/host-preflight.json")
        != contract["host"]["host_preflight_sha256"]
        or sha256_file(evidence_dir / "host-preflight/file-inventory-sha256.txt")
        != contract["host"]["host_inventory_sha256"]
    ):
        raise ValueError("E22b retained host differs")
    return contract


def response_maps(probe: dict[str, Any], task_ids: list[str]) -> list[dict[str, str]]:
    maps = []
    for worker_index, worker in enumerate(probe.get("workers", []), 1):
        cases = worker.get("cases")
        result = worker.get("result")
        if (
            worker.get("worker") != worker_index
            or not isinstance(cases, list)
            or [case.get("id") for case in cases] != task_ids
            or not isinstance(result, dict)
            or result.get("total") != len(task_ids)
            or any(case.get("status") != 200 for case in cases)
        ):
            raise ValueError(f"E22b worker {worker_index} probe differs")
        maps.append({case["id"]: case.get("response") for case in cases})
    return maps


def validate_valid_cell(
    cell_dir: Path,
    *,
    contract: dict[str, Any],
    cell: dict[str, Any],
    task_ids: list[str],
) -> dict[str, Any]:
    mode = cell["mode"]
    workers = cell["workers"]
    plan = load_object(cell_dir / "deployment-plan.json")
    ready = load_object(cell_dir / "ready.json")
    receipt = load_object(cell_dir / "deployment-receipt.json")
    probe = load_object(cell_dir / "probe.json")
    expected_mode = "normal_repack" if mode == "normal" else "shared_sidecar"
    if (
        plan.get("status") != "ready_to_deploy_pareto64"
        or plan.get("deployment_mode") != expected_mode
        or plan.get("worker_count") != workers
        or len(plan.get("workers", [])) != workers
        or any(
            item["argv"][item["argv"].index("--threads") + 1] != "1"
            or item["argv"][item["argv"].index("--threads-batch") + 1] != "1"
            for item in plan["workers"]
        )
        or ready.get("status") != "pareto64_deployment_ready"
        or ready.get("deployment_sha256") != plan.get("deployment_sha256")
        or len(ready.get("workers", [])) != workers
        or receipt.get("status") != "valid_pareto64_deployment_lifecycle"
        or receipt.get("failure") is not None
        or receipt.get("deployment_sha256") != plan.get("deployment_sha256")
        or len(receipt.get("workers", [])) != workers
    ):
        raise ValueError(f"{cell_dir.name} deployment lifecycle differs")
    mappings = receipt.get("shared_mappings")
    if not isinstance(mappings, list) or (
        mode == "shared"
        and (
            len(mappings) != workers
            or any(
                mapping.get("read_only") is not True
                or mapping.get("shared") is not True
                or mapping.get("inode") != plan["sidecar"]["inode"]
                for mapping in mappings
            )
        )
    ):
        raise ValueError(f"{cell_dir.name} shared mappings differ")
    if mode == "normal" and (mappings or plan.get("sidecar") is not None):
        raise ValueError(f"{cell_dir.name} normal control uses a sidecar")

    group = probe.get("group")
    memory = probe.get("memory_after_measurement")
    pmu = probe.get("pmu")
    maps = response_maps(probe, task_ids)
    expected_events = set(contract["pmu"]["events"])
    gateway = probe.get("gateway_smoke", {})
    headers = gateway.get("headers", {})
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E22b-fixed-memory-curve"
        or probe.get("mode") != mode
        or probe.get("worker_count") != workers
        or len(maps) != workers
        or not isinstance(group, dict)
        or group.get("measured_requests")
        != contract["workload"]["requests_per_worker"] * workers
        or not finite_positive(group.get("requests_per_second"))
        or not finite_positive(group.get("summed_pss_kib"))
        or not finite_positive(group.get("summed_rss_kib"))
        or not isinstance(memory, dict)
        or memory.get("memtotal_bytes") != contract["fixed_memory"]["cap_bytes"]
        or memory.get("swaptotal_bytes") != 0
        or memory.get("swapfree_bytes") != 0
        or probe.get("vmstat_delta", {}).get("oom_kill") != 0
        or not isinstance(pmu, dict)
        or set(pmu.get("events", {})) != expected_events
        or any(not finite_positive(value) for value in pmu["events"].values())
        or pmu.get("raw_sha256") != sha256_file(cell_dir / "perf-stat.csv")
        or headers.get("X-Pareto64-Route") != "unknown_shadow_then_oracle"
        or headers.get("X-Pareto64-Served-Source") != "uncached_oracle"
    ):
        raise ValueError(f"{cell_dir.name} probe shape differs")
    return {
        "position": cell["position"],
        "mode": mode,
        "worker_count": workers,
        "started": True,
        "valid": True,
        "admitted": (
            memory["memavailable_bytes"]
            >= contract["fixed_memory"]["minimum_mem_available_bytes"]
        ),
        "deployment_sha256": plan["deployment_sha256"],
        "request_failures": group["request_failures"],
        "reference_prediction_mismatches": group["reference_prediction_mismatches"],
        "responses_stable_across_workers": all(item == maps[0] for item in maps[1:]),
        "response_map": maps[0],
        "correct": group["correct"],
        "measured_requests": group["measured_requests"],
        "requests_per_second": group["requests_per_second"],
        "requests_per_second_per_worker": group["requests_per_second_per_worker"],
        "p50_http_ms": group["http_ms"]["median"],
        "p95_http_ms": group["http_ms"]["p95"],
        "maximum_http_ms": group["http_ms"]["max"],
        "summed_pss_kib": group["summed_pss_kib"],
        "summed_rss_kib": group["summed_rss_kib"],
        "throughput_per_gib_pss": group["throughput_per_gib_pss"],
        "one_worker_ready_seconds": group["one_worker_ready_seconds"],
        "all_workers_ready_seconds": group["all_workers_ready_seconds"],
        "server_cpu_seconds_per_request": group["server_cpu_seconds_per_request"],
        "minor_page_faults": group["minor_page_faults"],
        "major_page_faults": group["major_page_faults"],
        "mem_available_bytes": memory["memavailable_bytes"],
        "shared_mapping_count": len(mappings),
        "pmu_events": pmu["events"],
    }


def validate_nonvalid_cell(cell_dir: Path, cell: dict[str, Any]) -> dict[str, Any]:
    status = load_object(cell_dir / "cell-status.json")
    mode = cell["mode"]
    workers = cell["workers"]
    if (
        status.get("mode") != mode
        or status.get("workers") != workers
        or status.get("position") != cell["position"]
    ):
        raise ValueError(f"{cell_dir.name} nonvalid status differs")
    if status.get("status") == "skipped_by_frozen_normal_six_stop_rule":
        return {
            "position": cell["position"],
            "mode": mode,
            "worker_count": workers,
            "started": False,
            "valid": False,
            "admitted": False,
            "failure_class": "frozen_conditional_skip",
            "resource_boundary_evidence": True,
        }
    if status.get("status") != "failed_fixed_memory_admission_cell":
        raise ValueError(f"{cell_dir.name} failure status differs")
    text = "\n".join(
        item.read_text(errors="replace")
        for item in (
            cell_dir / "deploy.stderr.log",
            cell_dir / "kernel-since-start.txt",
            cell_dir / "deployment-receipt.json",
        )
        if item.is_file()
    )
    resource = bool(
        re.search(
            r"out of memory|oom-kill|killed process|exited before readiness",
            text,
            flags=re.IGNORECASE,
        )
    )
    return {
        "position": cell["position"],
        "mode": mode,
        "worker_count": workers,
        "started": True,
        "valid": False,
        "admitted": False,
        "failure_class": "fixed_memory_admission_failure",
        "exit_status": status.get("exit_status"),
        "deployment_status": status.get("deployment_status"),
        "resource_boundary_evidence": resource,
    }


def compare_pairs(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {(cell["mode"], cell["worker_count"]): cell for cell in cells}
    pairs = []
    for workers in (1, 2, 4, 5, 6):
        normal = indexed[("normal", workers)]
        shared = indexed[("shared", workers)]
        if not normal["valid"] or not shared["valid"]:
            continue
        pairs.append(
            {
                "worker_count": workers,
                "response_differences": sum(
                    normal["response_map"].get(task_id)
                    != shared["response_map"].get(task_id)
                    for task_id in set(normal["response_map"])
                    | set(shared["response_map"])
                ),
                "throughput_ratio": shared["requests_per_second"]
                / normal["requests_per_second"],
                "p95_latency_ratio": shared["p95_http_ms"] / normal["p95_http_ms"],
                "summed_pss_saved_kib": normal["summed_pss_kib"]
                - shared["summed_pss_kib"],
                "summed_pss_ratio": shared["summed_pss_kib"] / normal["summed_pss_kib"],
                "readiness_ratio": shared["all_workers_ready_seconds"]
                / normal["all_workers_ready_seconds"],
            }
        )
    return pairs


def ingest(evidence_dir: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_contract(evidence_dir, contract_path, root)
    task_ids = [
        task["id"] for task in load_object(root / "experiments/e3_tasks.json")["tasks"]
    ]
    cells = []
    for cell in contract["matrix"]["order"]:
        cell_dir = (
            evidence_dir
            / "cells"
            / (f"{cell['position']:02d}-{cell['mode']}-w{cell['workers']}")
        )
        status = load_object(cell_dir / "cell-status.json")
        if status.get("status") == "valid_fixed_memory_curve_cell":
            cells.append(
                validate_valid_cell(
                    cell_dir, contract=contract, cell=cell, task_ids=task_ids
                )
            )
        else:
            cells.append(validate_nonvalid_cell(cell_dir, cell))
    indexed = {(cell["mode"], cell["worker_count"]): cell for cell in cells}
    pairs = compare_pairs(cells)
    pair_index = {pair["worker_count"]: pair for pair in pairs}
    admitted = {
        mode: [
            cell
            for cell in cells
            if cell["mode"] == mode and cell["valid"] and cell["admitted"]
        ]
        for mode in ("normal", "shared")
    }
    maxima = {
        mode: max(items, key=lambda item: item["worker_count"]) if items else None
        for mode, items in admitted.items()
    }
    normal_max = maxima["normal"]
    shared_max = maxima["shared"]
    normal_one = indexed[("normal", 1)]
    validity = {
        "campaign_completed": load_object(evidence_dir / "campaign-status.json").get(
            "status"
        )
        == "completed_fixed_memory_curve_campaign",
        "required_normal_cells_valid": all(
            indexed[("normal", count)]["valid"] for count in (1, 2, 4, 5)
        ),
        "required_shared_cells_valid": all(
            indexed[("shared", count)]["valid"] for count in (1, 2, 4, 5, 6, 8)
        ),
        "normal_boundary_is_valid_or_resource_limited": all(
            indexed[("normal", count)]["valid"]
            or indexed[("normal", count)].get("resource_boundary_evidence") is True
            for count in (6, 8)
        ),
        "normal_eight_condition_respected": not (
            indexed[("normal", 6)]["valid"]
            and indexed[("normal", 6)]["admitted"]
            and not indexed[("normal", 8)]["started"]
        ),
        "all_valid_cells_exact": all(
            cell.get("request_failures") == 0
            and cell.get("reference_prediction_mismatches") == 0
            and cell.get("responses_stable_across_workers") is True
            for cell in cells
            if cell["valid"]
        ),
        "all_valid_cells_have_pmu": all(
            set(cell.get("pmu_events", {})) == set(contract["pmu"]["events"])
            for cell in cells
            if cell["valid"]
        ),
    }
    advance = contract["advance"]
    gates = {
        "valid_curve": all(validity.values()),
        "exact_responses_between_modes": all(
            pair["response_differences"]
            == advance["response_differences_between_modes"]
            for pair in pairs
        ),
        "throughput_retained_at_common_counts": all(
            pair["throughput_ratio"]
            >= advance["minimum_shared_throughput_ratio_at_common_count"]
            for pair in pairs
        ),
        "p95_bounded_at_common_counts": all(
            pair["p95_latency_ratio"]
            <= advance["maximum_shared_p95_ratio_at_common_count"]
            for pair in pairs
        ),
        "four_worker_pss_saving": pair_index.get(4, {}).get("summed_pss_saved_kib", -1)
        >= advance["minimum_pss_saved_kib_at_four_workers"],
        "four_worker_readiness_bounded": pair_index.get(4, {}).get(
            "readiness_ratio", math.inf
        )
        <= advance["maximum_shared_four_readiness_ratio"],
        "shared_eight_admitted": indexed[("shared", 8)]["admitted"] is True,
        "density_gain": (
            normal_max is not None
            and shared_max is not None
            and shared_max["worker_count"] - normal_max["worker_count"]
            >= advance["minimum_density_worker_gain"]
        ),
        "fixed_memory_aggregate_throughput": (
            normal_max is not None
            and shared_max is not None
            and shared_max["requests_per_second"] / normal_max["requests_per_second"]
            >= advance["minimum_fixed_memory_aggregate_throughput_ratio"]
        ),
        "shared_max_per_worker_throughput": (
            shared_max is not None
            and normal_one["valid"]
            and shared_max["requests_per_second_per_worker"]
            / normal_one["requests_per_second_per_worker"]
            >= advance["minimum_shared_max_per_worker_throughput_ratio_to_normal_one"]
        ),
        "shared_mapping_identity": all(
            cell["shared_mapping_count"] == cell["worker_count"]
            for cell in cells
            if cell["valid"] and cell["mode"] == "shared"
        ),
        "all_pmu_events_counted": validity["all_valid_cells_have_pmu"],
    }
    construction_receipt = load_object(evidence_dir / "product/sidecar-receipt.json")
    return {
        "schema_version": 1,
        "experiment_id": "E22b-fixed-memory-curve",
        "status": (
            "valid_fixed_memory_curve_promoted"
            if all(gates.values())
            else "valid_fixed_memory_curve_not_promoted"
            if all(validity.values())
            else "invalid_fixed_memory_curve"
        ),
        "contract_sha256": sha256_file(contract_path),
        "repository_commit": (evidence_dir / "repository-commit.txt")
        .read_text()
        .strip(),
        "host": contract["host"],
        "fixed_memory": contract["fixed_memory"],
        "construction": construction_receipt.get("construction"),
        "storage": construction_receipt.get("storage"),
        "cells": cells,
        "pairs": pairs,
        "validity_gates": validity,
        "advance_gates": gates,
        "failed_advance_gates": [name for name, passed in gates.items() if not passed],
        "maximum_admitted": {
            mode: (
                {
                    "worker_count": item["worker_count"],
                    "requests_per_second": item["requests_per_second"],
                    "p95_http_ms": item["p95_http_ms"],
                    "summed_pss_kib": item["summed_pss_kib"],
                    "mem_available_bytes": item["mem_available_bytes"],
                }
                if item is not None
                else None
            )
            for mode, item in maxima.items()
        },
        "fixed_memory_aggregate_throughput_ratio": (
            shared_max["requests_per_second"] / normal_max["requests_per_second"]
            if normal_max is not None and shared_max is not None
            else None
        ),
        "decision": (
            "freeze_clean_repeated_maximum_density_comparison"
            if all(gates.values())
            else "retain_curve_and_demote_or_narrow_fixed_memory_claim"
        ),
        "claim_boundary": contract["scientific_boundary"],
        "cost_control": contract["cost_control"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    summary = ingest(
        arguments.evidence_dir.resolve(),
        arguments.contract.resolve(),
        arguments.root.resolve(),
    )
    arguments.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "decision": summary["decision"],
                "failed_advance_gates": summary["failed_advance_gates"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
