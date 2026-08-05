#!/usr/bin/env python3
"""Validate and summarize the frozen full E21a native service matrix."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e9a_ingest import expected_server_argv
    from experiments.e13b_ingest import validate_process_cpu, validate_runtime
    from experiments.e21a_online_policy import identity_sha256, sha256_value, valid_call
    from experiments.e21a_preflight_probe import valid_nonnegative_numbers
    from experiments.evidence_readiness import load_slots_array
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import load_object, sha256_file
    from e9a_ingest import expected_server_argv
    from e13b_ingest import validate_process_cpu, validate_runtime
    from e21a_online_policy import identity_sha256, sha256_value, valid_call
    from e21a_preflight_probe import valid_nonnegative_numbers
    from evidence_readiness import load_slots_array


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E21a"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E21a contract differs")
    for name, item in contract["inputs"].items():
        if sha256_file(root / item["path"]) != item["sha256"]:
            raise ValueError(f"E21a input differs for {name}")
    return contract


def validate_recipe(
    recipe: dict[str, Any], contract: dict[str, Any], policy: str, repetition: int
) -> dict[str, Any]:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("experiment_id") != "E21a"
        or recipe.get("policy") != policy
        or recipe.get("repetition") != repetition
        or recipe.get("profile_name") != "e7c_final"
        or recipe.get("service") != contract["service"]
        or model.get("candidate") != contract["selected"]["candidate"]
        or model.get("sha256") != contract["selected"]["model_sha256"]
        or model.get("size_bytes") != contract["selected"]["model_size_bytes"]
        or not isinstance(server, str)
        or not server.endswith("/bin/llama-server")
        or not isinstance(model_path, str)
        or not model_path.endswith(".gguf")
        or contract["service"]["source_commit"][:9]
        not in recipe.get("server_version", "")
        or recipe.get("argv")
        != expected_server_argv(
            server,
            model_path,
            candidate=contract["selected"]["candidate"],
            profile_name="e7c_final",
        )
    ):
        raise ValueError("E21a recipe differs from exact E7c service")
    return recipe


def expected_cell_path(cell: dict[str, Any]) -> str:
    return f"{cell['index']:02d}-{cell['policy']}-r{cell['repetition']}"


def validate_cell(
    cell_dir: Path,
    contract: dict[str, Any],
    policy: str,
    repetition: int,
) -> dict[str, Any]:
    recipe = validate_recipe(
        load_object(cell_dir / "recipe.json"), contract, policy, repetition
    )
    probe = load_object(cell_dir / "probe.json")
    readiness = load_object(cell_dir / "readiness.json")
    slots = load_slots_array(cell_dir / "slots.json")
    process = parse_time_output((cell_dir / "server-time.log").read_text())
    pid = int((cell_dir / "server-pid.txt").read_text().strip())
    workload = contract["workload"]
    expected = contract["acceptance"]
    served = probe.get("served_records", [])
    raw = probe.get("raw_calls", [])
    fingerprints = probe.get("unseen_prompt_fingerprints", {})
    if (
        probe.get("experiment_id") != "E21a"
        or probe.get("policy") != policy
        or probe.get("repetition") != repetition
        or probe.get("identity_sha256") != contract["identity_sha256"]
        or probe.get("result", {}).get("served_requests")
        != workload["served_requests_per_cell"]
        or len(served) != workload["served_requests_per_cell"]
        or [record.get("task_id") for record in served] != workload["task_sequence"]
        or len(fingerprints) != workload["unique_prompts"]
        or len(set(fingerprints.values())) != workload["unique_prompts"]
        or set(fingerprints.values())
        & set(contract["prior_certificate"]["prompt_fingerprints"])
        or readiness.get("status") != "ok"
        or not isinstance(readiness.get("ready_ms"), (int, float))
        or not math.isfinite(float(readiness["ready_ms"]))
        or len(slots) != 1
        or process["maximum_rss_kib"] is None
        or (cell_dir / "server-shell-exit.txt").read_text().strip()
        not in {str(value) for value in expected["server_exit_statuses"]}
        or any(not valid_call(record.get("served_call", {})) for record in served)
    ):
        raise ValueError(f"E21a {policy} r{repetition} cell differs")
    valid_nonnegative_numbers(
        raw, ("http_ms", "encode_ms", "decode_ms", "cached_tokens")
    )
    process_cpu = validate_process_cpu(
        probe.get("process_cpu"),
        pid=pid,
        requests=len(served),
        elapsed=float(probe["result"]["elapsed_seconds"]),
    )
    route_counts = probe["result"].get("route_counts")
    admission_counts = probe["result"].get("admission_counts")
    expected_routes = expected[f"{policy}_route_counts"]
    expected_admissions = expected[f"{policy}_admission_counts"]
    expected_calls = expected[f"{policy}_http_calls"]
    if (
        route_counts != expected_routes
        or admission_counts != expected_admissions
        or len(raw) != expected_calls
        or probe["result"].get("actual_http_calls") != expected_calls
        or probe["result"].get("request_failures") != 0
        or probe["result"].get("correct") != workload["correct_per_cell"]
        or probe["result"].get("reference_prediction_mismatches") != 0
    ):
        raise ValueError(f"E21a {policy} r{repetition} frozen counts differ")
    registry = probe.get("registry")
    if policy == "all_uncached":
        if registry is not None or any(call["cached_tokens"] != 0 for call in raw):
            raise ValueError("E21a baseline is not fully uncached")
    else:
        payload = registry.get("payload", {}) if isinstance(registry, dict) else {}
        if (
            registry.get("payload_sha256") != sha256_value(payload)
            or payload.get("identity_sha256") != identity_sha256(contract["identity"])
            or len(payload.get("certified", {})) != expected["certified_transitions"]
            or len(payload.get("denied", {})) != expected["denied_transitions"]
            or set(payload.get("certified", {})) & set(payload.get("denied", {}))
        ):
            raise ValueError("E21a online registry differs")
    return {
        "policy": policy,
        "repetition": repetition,
        "recipe": recipe,
        "probe": probe,
        "served_records": served,
        "raw_calls": raw,
        "process_cpu": process_cpu,
        "maximum_rss_kib": process["maximum_rss_kib"],
        "readiness_ms": float(readiness["ready_ms"]),
        "server_pid": pid,
    }


def aggregate_policy(cells: list[dict[str, Any]]) -> dict[str, Any]:
    records = [record for cell in cells for record in cell["served_records"]]
    elapsed = sum(float(cell["probe"]["result"]["elapsed_seconds"]) for cell in cells)
    cpu = sum(float(cell["process_cpu"]["total_seconds"]) for cell in cells)
    return {
        "repetitions": len(cells),
        "served_requests": len(records),
        "actual_http_calls": sum(len(cell["raw_calls"]) for cell in cells),
        "elapsed_seconds": elapsed,
        "served_requests_per_second": len(records) / elapsed,
        "per_cell_served_requests_per_second": summarize(
            [
                float(cell["probe"]["result"]["served_requests_per_second"])
                for cell in cells
            ]
        ),
        "user_http_ms": summarize(
            [float(record["user_http_ms"]) for record in records]
        ),
        "cpu_seconds_per_served_request": cpu / len(records),
        "maximum_rss_kib": summarize(
            [float(cell["maximum_rss_kib"]) for cell in cells]
        ),
        "readiness_ms": summarize([cell["readiness_ms"] for cell in cells]),
        "request_failures": sum(
            cell["probe"]["result"]["request_failures"] for cell in cells
        ),
        "correct": sum(cell["probe"]["result"]["correct"] for cell in cells),
        "reference_prediction_mismatches": sum(
            cell["probe"]["result"]["reference_prediction_mismatches"] for cell in cells
        ),
        "cell_metrics": [
            {
                "repetition": cell["repetition"],
                "served_requests_per_second": cell["probe"]["result"][
                    "served_requests_per_second"
                ],
                "median_user_http_ms": cell["probe"]["result"]["user_http_ms"][
                    "median"
                ],
                "p95_user_http_ms": cell["probe"]["result"]["user_http_ms"]["p95"],
                "cpu_seconds_per_served_request": cell["process_cpu"][
                    "seconds_per_request"
                ],
                "maximum_rss_kib": cell["maximum_rss_kib"],
                "readiness_ms": cell["readiness_ms"],
            }
            for cell in sorted(cells, key=lambda item: item["repetition"])
        ],
    }


def ratio(candidate: float, baseline: float) -> float:
    if baseline <= 0:
        raise ValueError("E21a ratio baseline is not positive")
    return candidate / baseline


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E21a full matrix is not native Arm64")
    runtime = validate_runtime(evidence, contract)
    ordered_cells = []
    for spec in contract["execution"]["cell_order"]:
        ordered_cells.append(
            validate_cell(
                evidence / "cells" / expected_cell_path(spec),
                contract,
                spec["policy"],
                spec["repetition"],
            )
        )
    by_policy = {
        policy: [cell for cell in ordered_cells if cell["policy"] == policy]
        for policy in ("all_uncached", "online")
    }
    baseline = aggregate_policy(by_policy["all_uncached"])
    online = aggregate_policy(by_policy["online"])
    workload = contract["workload"]
    canonical = by_policy["all_uncached"][0]["served_records"]
    canonical_by_task = {
        record["task_id"]: record for record in canonical[: workload["unique_prompts"]]
    }
    exact_mismatches = 0
    for cell in ordered_cells:
        for record in cell["served_records"]:
            exact_mismatches += (
                record["served_response"]
                != canonical_by_task[record["task_id"]]["served_response"]
            )

    baseline_by_rep = {cell["repetition"]: cell for cell in by_policy["all_uncached"]}
    online_by_rep = {cell["repetition"]: cell for cell in by_policy["online"]}
    certified_online_ms: list[float] = []
    certified_baseline_ms: list[float] = []
    first_use_online_ms: list[float] = []
    first_use_baseline_ms: list[float] = []
    break_even = []
    tasks_per_cycle = workload["unique_prompts"]
    for repetition in range(1, contract["execution"]["repetitions_per_policy"] + 1):
        baseline_records = baseline_by_rep[repetition]["served_records"]
        online_records = online_by_rep[repetition]["served_records"]
        cumulative_baseline = 0.0
        cumulative_online = 0.0
        ratios = []
        first_break_even = None
        for index, (left, right) in enumerate(
            zip(baseline_records, online_records, strict=True)
        ):
            if (
                left["served_index"] != right["served_index"]
                or left["task_id"] != right["task_id"]
            ):
                raise ValueError("E21a paired trace identity differs")
            if right["route"] == "certified_cache":
                certified_baseline_ms.append(float(left["user_http_ms"]))
                certified_online_ms.append(float(right["user_http_ms"]))
            elif right["route"] == "unknown_shadow_then_oracle":
                first_use_baseline_ms.append(float(left["user_http_ms"]))
                first_use_online_ms.append(float(right["user_http_ms"]))
            cumulative_baseline += float(left["user_http_ms"])
            cumulative_online += float(right["user_http_ms"])
            if (index + 1) % tasks_per_cycle == 0:
                cycle = (index + 1) // tasks_per_cycle
                cycle_ratio = ratio(cumulative_online, cumulative_baseline)
                ratios.append({"cycle": cycle, "cumulative_latency_ratio": cycle_ratio})
                if first_break_even is None and cycle_ratio <= 1.0:
                    first_break_even = cycle
        break_even.append(
            {
                "repetition": repetition,
                "first_cumulative_break_even_cycle": first_break_even,
                "cumulative_cycles": ratios,
            }
        )

    lifecycle_ratios = {
        "throughput": ratio(
            online["served_requests_per_second"], baseline["served_requests_per_second"]
        ),
        "median_user_latency": ratio(
            online["user_http_ms"]["median"], baseline["user_http_ms"]["median"]
        ),
        "p95_user_latency": ratio(
            online["user_http_ms"]["p95"], baseline["user_http_ms"]["p95"]
        ),
        "cpu_seconds_per_served_request": ratio(
            online["cpu_seconds_per_served_request"],
            baseline["cpu_seconds_per_served_request"],
        ),
        "maximum_rss": ratio(
            online["maximum_rss_kib"]["max"], baseline["maximum_rss_kib"]["max"]
        ),
        "median_readiness": ratio(
            online["readiness_ms"]["median"], baseline["readiness_ms"]["median"]
        ),
    }
    steady_baseline = summarize(certified_baseline_ms)
    steady_online = summarize(certified_online_ms)
    first_use_baseline = summarize(first_use_baseline_ms)
    first_use_online = summarize(first_use_online_ms)
    tail_boundaries = {
        "certified_steady_state": {
            "requests_per_policy": len(certified_online_ms),
            "baseline_user_http_ms": steady_baseline,
            "online_user_http_ms": steady_online,
            "median_latency_ratio": ratio(
                steady_online["median"], steady_baseline["median"]
            ),
            "p95_latency_ratio": ratio(steady_online["p95"], steady_baseline["p95"]),
        },
        "synchronous_first_use": {
            "requests_per_policy": len(first_use_online_ms),
            "baseline_user_http_ms": first_use_baseline,
            "online_user_http_ms": first_use_online,
            "median_latency_ratio": ratio(
                first_use_online["median"], first_use_baseline["median"]
            ),
            "p95_latency_ratio": ratio(
                first_use_online["p95"], first_use_baseline["p95"]
            ),
        },
    }
    expected = contract["acceptance"]
    online_cells = by_policy["online"]
    validity_gates = {
        "native_arm64": True,
        "exact_e7c_service_and_runtime": True,
        "complete_reverse_balanced_fresh_process_matrix": len(ordered_cells)
        == contract["execution"]["total_cells"],
        "all_30_prompts_unseen_to_e13b": all(
            not set(cell["probe"]["unseen_prompt_fingerprints"].values())
            & set(contract["prior_certificate"]["prompt_fingerprints"])
            for cell in online_cells
        ),
        "zero_request_failures": baseline["request_failures"] == 0
        and online["request_failures"] == 0,
        "exact_outputs_match_all_uncached": exact_mismatches
        == expected["exact_response_mismatches"],
        "reference_answers_preserved": baseline["reference_prediction_mismatches"] == 0
        and online["reference_prediction_mismatches"] == 0,
        "unknown_cached_attempts_never_served": all(
            record["shadow_cached_attempt_served"] is False
            for cell in online_cells
            for record in cell["served_records"]
        ),
        "frozen_route_and_admission_counts": all(
            cell["probe"]["result"]["route_counts"] == expected["online_route_counts"]
            and cell["probe"]["result"]["admission_counts"]
            == expected["online_admission_counts"]
            for cell in online_cells
        ),
        "registry_counts": all(
            len(cell["probe"]["registry"]["payload"]["certified"])
            == expected["certified_transitions"]
            and len(cell["probe"]["registry"]["payload"]["denied"])
            == expected["denied_transitions"]
            for cell in online_cells
        ),
        "certified_cache_mechanism": all(
            record["served_call"]["cached_tokens"] >= workload["minimum_cached_tokens"]
            for cell in online_cells
            for record in cell["served_records"]
            if record["route"] == "certified_cache"
        ),
        "unknown_shadow_mechanism": all(
            sum(call["role"] == "unknown_cached_shadow" for call in cell["raw_calls"])
            == expected["unknown_shadow_calls"]
            for cell in online_cells
        ),
        "baseline_uncached_mechanism": all(
            call["cached_tokens"] == 0
            for cell in by_policy["all_uncached"]
            for call in cell["raw_calls"]
        ),
        "raw_call_counts": baseline["actual_http_calls"]
        == expected["all_uncached_http_calls"]
        * contract["execution"]["repetitions_per_policy"]
        and online["actual_http_calls"]
        == expected["online_http_calls"]
        * contract["execution"]["repetitions_per_policy"],
    }
    thresholds = contract["promotion_thresholds"]
    break_even_cycles = [
        item["first_cumulative_break_even_cycle"] for item in break_even
    ]
    promotion_gates = {
        "minimum_lifecycle_throughput": lifecycle_ratios["throughput"]
        >= thresholds["minimum_throughput_ratio"],
        "maximum_cpu_per_request": lifecycle_ratios["cpu_seconds_per_served_request"]
        <= thresholds["maximum_cpu_ratio"],
        "bounded_lifecycle_p95": lifecycle_ratios["p95_user_latency"]
        <= thresholds["maximum_lifecycle_p95_ratio"],
        "certified_steady_state_p95_nonregression": tail_boundaries[
            "certified_steady_state"
        ]["p95_latency_ratio"]
        <= thresholds["maximum_certified_p95_ratio"],
        "break_even_by_frozen_cycle": all(
            cycle is not None and cycle <= thresholds["maximum_break_even_cycle"]
            for cycle in break_even_cycles
        ),
        "maximum_rss_bound": lifecycle_ratios["maximum_rss"]
        <= thresholds["maximum_rss_ratio"],
        "readiness_bound": lifecycle_ratios["median_readiness"]
        <= thresholds["maximum_readiness_ratio"],
    }
    valid = all(validity_gates.values())
    promoted = valid and all(promotion_gates.values())
    status = (
        "valid_online_transition_certificate_promoted"
        if promoted
        else "valid_online_transition_certificate_no_promotion"
        if valid
        else "invalid_online_transition_certificate"
    )
    answers = [
        {
            "task_id": task_id,
            "expected": canonical_by_task[task_id]["expected"],
            "reference_prediction": canonical_by_task[task_id]["reference_prediction"],
            "prediction": canonical_by_task[task_id]["prediction"],
            "exact_response": canonical_by_task[task_id]["served_response"],
        }
        for task_id in workload["task_ids"]
    ]
    return {
        "schema_version": 1,
        "experiment_id": "E21a",
        "status": status,
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "runtime": runtime,
        "baseline": baseline,
        "online": online,
        "lifecycle_ratios": lifecycle_ratios,
        "tail_boundaries": tail_boundaries,
        "break_even": break_even,
        "quality": {
            "task_score": f"{workload['correct_per_cycle']}/{workload['unique_prompts']}",
            "baseline_correct": baseline["correct"],
            "online_correct": online["correct"],
            "exact_response_mismatches": exact_mismatches,
            "answers": answers,
        },
        "online_decisions_per_repetition": {
            "route_counts": expected["online_route_counts"],
            "admission_counts": expected["online_admission_counts"],
            "certified_transitions": expected["certified_transitions"],
            "denied_transitions": expected["denied_transitions"],
        },
        "validity_gates": validity_gates,
        "promotion_gates": promotion_gates,
        "decision": {
            "valid": valid,
            "promoted": promoted,
            "selected_policy": "online" if promoted else "all_uncached",
            "first_use_tail_regression_retained": tail_boundaries[
                "synchronous_first_use"
            ]["p95_latency_ratio"]
            > 1.0,
            "post_result_gate_change_permitted": False,
        },
        "provenance": load_object(evidence / "github.json"),
        "claim_boundary": contract["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_summary(args.evidence_dir, args.contract, args.root)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "validity_gates": result["validity_gates"],
                "promotion_gates": result["promotion_gates"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
