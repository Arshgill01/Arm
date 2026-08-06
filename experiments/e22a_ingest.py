#!/usr/bin/env python3
"""Independently validate and summarize the E22a scaling preflight."""

from __future__ import annotations

import argparse
import json
import math
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
        or contract.get("experiment_id") != "E22a-preflight"
        or contract.get("scientific_boundary", {}).get("preflight_only") is not True
        or contract.get("scientific_boundary", {}).get(
            "final_performance_claim_permitted"
        )
        is not False
    ):
        raise ValueError("E22a contract boundary differs")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("retained E22a contract differs")
    for relative, record in contract["inputs"].items():
        if sha256_file(root / relative) != record["sha256"]:
            raise ValueError(f"E22a input differs: {relative}")
    if "aarch64" not in (evidence_dir / "uname.txt").read_text():
        raise ValueError("E22a did not run on native aarch64")
    return contract


def validate_cell(
    cell_dir: Path,
    *,
    contract: dict[str, Any],
    cell: dict[str, Any],
    task_ids: list[str],
) -> dict[str, Any]:
    mode = cell["mode"]
    worker_count = cell["workers"]
    plan = load_object(cell_dir / "deployment-plan.json")
    ready = load_object(cell_dir / "ready.json")
    receipt = load_object(cell_dir / "deployment-receipt.json")
    probe = load_object(cell_dir / "probe.json")
    expected_mode = "normal_repack" if mode == "normal" else "shared_sidecar"
    if (
        plan.get("status") != "ready_to_deploy_pareto64"
        or plan.get("deployment_mode") != expected_mode
        or plan.get("worker_count") != worker_count
        or any(
            worker.get("worker") != index + 1
            for index, worker in enumerate(plan["workers"])
        )
        or any(
            worker.get("argv", [None])[0] != plan["workers"][0]["argv"][0]
            for worker in plan["workers"]
        )
        or any(
            worker["argv"][worker["argv"].index("--threads") + 1] != "1"
            or worker["argv"][worker["argv"].index("--threads-batch") + 1] != "1"
            for worker in plan["workers"]
        )
    ):
        raise ValueError(f"{cell_dir.name} deployment plan differs")
    if (
        ready.get("status") != "pareto64_deployment_ready"
        or ready.get("deployment_sha256") != plan.get("deployment_sha256")
        or len(ready.get("workers", [])) != worker_count
        or receipt.get("status") != "valid_pareto64_deployment_lifecycle"
        or receipt.get("deployment_sha256") != plan.get("deployment_sha256")
        or receipt.get("deployment_mode") != expected_mode
        or len(receipt.get("workers", [])) != worker_count
        or receipt.get("failure") is not None
        or len(receipt.get("worker_returncodes", [])) != worker_count
        or any(value not in (0, -2, 130) for value in receipt["worker_returncodes"])
    ):
        raise ValueError(f"{cell_dir.name} deployment lifecycle differs")
    mappings = receipt.get("shared_mappings")
    if not isinstance(mappings, list) or (
        mode == "shared"
        and (
            len(mappings) != worker_count
            or any(
                mapping.get("read_only") is not True
                or mapping.get("shared") is not True
                or mapping.get("inode") != plan["sidecar"]["inode"]
                for mapping in mappings
            )
        )
    ):
        raise ValueError(f"{cell_dir.name} shared mapping evidence differs")
    if mode == "normal" and (mappings or plan.get("sidecar") is not None):
        raise ValueError(f"{cell_dir.name} normal control unexpectedly uses a sidecar")
    raw_workers = probe.get("workers")
    group = probe.get("group")
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E22a-preflight"
        or probe.get("mode") != mode
        or probe.get("worker_count") != worker_count
        or probe.get("deployment_sha256") != plan.get("deployment_sha256")
        or not isinstance(raw_workers, list)
        or len(raw_workers) != worker_count
        or not isinstance(group, dict)
        or group.get("measured_requests")
        != contract["workload"]["requests_per_worker"] * worker_count
        or not finite_positive(group.get("elapsed_seconds"))
        or not finite_positive(group.get("requests_per_second"))
        or not finite_positive(group.get("summed_pss_kib"))
        or not finite_positive(group.get("summed_rss_kib"))
        or not finite_positive(group.get("throughput_per_gib_pss"))
    ):
        raise ValueError(f"{cell_dir.name} probe shape differs")
    response_maps = []
    for worker_index, worker in enumerate(raw_workers, 1):
        cases = worker.get("cases")
        result = worker.get("result")
        if (
            worker.get("worker") != worker_index
            or not isinstance(cases, list)
            or [case.get("id") for case in cases] != task_ids
            or not isinstance(result, dict)
            or result.get("total") != len(task_ids)
            or not finite_positive(result.get("elapsed_seconds"))
            or not finite_positive(result.get("requests_per_second"))
            or any(case.get("status") != 200 for case in cases)
        ):
            raise ValueError(f"{cell_dir.name} worker {worker_index} probe differs")
        response_maps.append({case["id"]: case.get("response") for case in cases})
    gateway = probe.get("gateway_smoke")
    headers = gateway.get("headers") if isinstance(gateway, dict) else None
    metrics = gateway.get("metrics") if isinstance(gateway, dict) else None
    if (
        not isinstance(headers, dict)
        or headers.get("X-Pareto64-Route") != "unknown_shadow_then_oracle"
        or headers.get("X-Pareto64-Served-Source") != "uncached_oracle"
        or not isinstance(metrics, dict)
        or metrics.get("runtime", {}).get("requests") != 1
        or metrics.get("runtime", {}).get("oracle_calls") != 1
    ):
        raise ValueError(f"{cell_dir.name} certificate gateway smoke differs")
    return {
        "position": cell["position"],
        "mode": mode,
        "worker_count": worker_count,
        "deployment_sha256": plan["deployment_sha256"],
        "request_failures": group["request_failures"],
        "reference_prediction_mismatches": group["reference_prediction_mismatches"],
        "responses_stable_across_workers": all(
            response_map == response_maps[0] for response_map in response_maps[1:]
        ),
        "response_map": response_maps[0],
        "correct": group["correct"],
        "measured_requests": group["measured_requests"],
        "requests_per_second": group["requests_per_second"],
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
        "shared_mapping_count": len(mappings),
        "gateway_route": headers["X-Pareto64-Route"],
        "gateway_served_source": headers["X-Pareto64-Served-Source"],
    }


def evaluate_pairs(
    cells: list[dict[str, Any]], advance: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, bool]]:
    by_key = {(cell["mode"], cell["worker_count"]): cell for cell in cells}
    pairs = []
    for worker_count in (1, 2, 4):
        normal = by_key[("normal", worker_count)]
        shared = by_key[("shared", worker_count)]
        pairs.append(
            {
                "worker_count": worker_count,
                "response_differences": sum(
                    normal["response_map"].get(task_id)
                    != shared["response_map"].get(task_id)
                    for task_id in set(normal["response_map"])
                    | set(shared["response_map"])
                ),
                "throughput_ratio": shared["requests_per_second"]
                / normal["requests_per_second"],
                "p95_latency_ratio": shared["p95_http_ms"] / normal["p95_http_ms"],
                "summed_pss_ratio": shared["summed_pss_kib"] / normal["summed_pss_kib"],
                "summed_pss_saved_kib": normal["summed_pss_kib"]
                - shared["summed_pss_kib"],
                "throughput_per_gib_ratio": shared["throughput_per_gib_pss"]
                / normal["throughput_per_gib_pss"],
                "all_workers_readiness_ratio": shared["all_workers_ready_seconds"]
                / normal["all_workers_ready_seconds"],
            }
        )
    pair_by_count = {pair["worker_count"]: pair for pair in pairs}
    saving_two = pair_by_count[2]["summed_pss_saved_kib"]
    saving_four = pair_by_count[4]["summed_pss_saved_kib"]
    gates = {
        "no_request_failures": all(cell["request_failures"] == 0 for cell in cells),
        "exact_reference_predictions": all(
            cell["reference_prediction_mismatches"] == 0 for cell in cells
        ),
        "stable_responses_across_workers": all(
            cell["responses_stable_across_workers"] for cell in cells
        ),
        "exact_responses_between_modes": all(
            pair["response_differences"]
            == advance["response_differences_between_modes"]
            for pair in pairs
        ),
        "throughput_retained": all(
            pair["throughput_ratio"]
            >= advance["minimum_shared_throughput_ratio_per_count"]
            for pair in pairs
        ),
        "p95_bounded": all(
            pair["p95_latency_ratio"]
            <= advance["maximum_shared_p95_latency_ratio_per_count"]
            for pair in pairs
        ),
        "two_worker_pss_saving": saving_two
        >= advance["minimum_pss_saved_kib_at_two_workers"],
        "four_worker_pss_saving": saving_four
        >= advance["minimum_pss_saved_kib_at_four_workers"],
        "pss_saving_does_not_collapse": saving_four
        >= saving_two * advance["maximum_four_to_two_pss_savings_collapse_ratio"],
        "shared_mapping_identity": all(
            cell["mode"] != "shared"
            or cell["shared_mapping_count"] == cell["worker_count"]
            for cell in cells
        ),
        "gateway_unknown_never_served": all(
            cell["gateway_route"] == "unknown_shadow_then_oracle"
            and cell["gateway_served_source"] == "uncached_oracle"
            for cell in cells
        ),
    }
    return pairs, gates


def ingest(evidence_dir: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_contract(evidence_dir, contract_path, root)
    sidecar_receipt = load_object(evidence_dir / "product/sidecar-receipt.json")
    construction = sidecar_receipt.get("construction")
    storage = sidecar_receipt.get("storage")
    if (
        sidecar_receipt.get("status") != "valid_persistent_arm_sidecar"
        or not isinstance(construction, dict)
        or not finite_positive(construction.get("total_prepack_seconds"))
        or not finite_positive(construction.get("full_verification_seconds"))
        or not isinstance(storage, dict)
        or not finite_positive(storage.get("sidecar_bytes"))
        or not finite_positive(storage.get("raw_repack_bytes"))
    ):
        raise ValueError("E22a sidecar construction evidence differs")
    tasks = load_object(root / "experiments/e3_tasks.json")["tasks"]
    task_ids = [task["id"] for task in tasks]
    cells = []
    for cell in contract["matrix"]["order"]:
        cell_dir = (
            evidence_dir
            / "cells"
            / (f"{cell['position']:02d}-{cell['mode']}-w{cell['workers']}")
        )
        cells.append(
            validate_cell(cell_dir, contract=contract, cell=cell, task_ids=task_ids)
        )
    pairs, gates = evaluate_pairs(cells, contract["advance"])
    return {
        "schema_version": 1,
        "experiment_id": "E22a-preflight",
        "status": "valid_sidecar_scaling_preflight",
        "contract_sha256": sha256_file(contract_path),
        "repository_commit": (evidence_dir / "repository-commit.txt")
        .read_text()
        .strip(),
        "host": {
            "uname": (evidence_dir / "uname.txt").read_text().strip(),
            "perf": load_object(evidence_dir / "perf-probe.json"),
            "stable_performance_authority": False,
        },
        "construction": construction,
        "storage": storage,
        "cells": cells,
        "pairs": pairs,
        "advance_gates": gates,
        "failed_advance_gates": [name for name, passed in gates.items() if not passed],
        "decision": (
            "proceed_to_stable_host_fixed_memory_contract"
            if all(gates.values())
            else "park_or_narrow_sidecar_scaling_hypothesis"
        ),
        "claim_boundary": contract["scientific_boundary"],
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
