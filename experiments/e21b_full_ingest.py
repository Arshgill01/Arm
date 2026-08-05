#!/usr/bin/env python3
"""Validate and summarize the frozen full E21b native service matrix."""

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
    from experiments.e21b_preflight_ingest import (
        recompute_counts,
        validate_call_request,
    )
    from experiments.evidence_readiness import load_slots_array
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import load_object, sha256_file
    from e9a_ingest import expected_server_argv
    from e13b_ingest import validate_process_cpu, validate_runtime
    from e21a_online_policy import identity_sha256, sha256_value, valid_call
    from e21b_preflight_ingest import recompute_counts, validate_call_request
    from evidence_readiness import load_slots_array


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E21b"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E21b full contract differs")
    for name, item in contract["inputs"].items():
        if sha256_file(root / item["path"]) != item["sha256"]:
            raise ValueError(f"E21b full input differs for {name}")
    return contract


def validate_recipe(
    recipe: dict[str, Any], contract: dict[str, Any], policy: str, repetition: int
) -> dict[str, Any]:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("experiment_id") != "E21b"
        or recipe.get("policy") != policy
        or recipe.get("repetition") != repetition
        or recipe.get("profile_name") != "e7c_final"
        or recipe.get("service") != contract["service"]
        or recipe.get("client") != contract["client"]
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
        raise ValueError("E21b recipe differs from exact E7c service/client")
    return recipe


def expected_cell_path(cell: dict[str, Any]) -> str:
    return f"{cell['index']:02d}-{cell['policy']}-r{cell['repetition']}"


def supported_timing(call: dict[str, Any]) -> bool:
    if call.get("error") is not None:
        return False
    for name in ("http_ms", "encode_ms", "decode_ms", "cached_tokens"):
        value = call.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not math.isfinite(float(value)) or float(value) < 0:
            return False
    return True


def validate_cell(
    cell_dir: Path,
    contract: dict[str, Any],
    policy: str,
    repetition: int,
    tasks: dict[str, dict[str, Any]],
    instruction: str,
) -> dict[str, Any]:
    recipe = validate_recipe(
        load_object(cell_dir / "recipe.json"), contract, policy, repetition
    )
    probe = load_object(cell_dir / "probe.json")
    readiness = load_object(cell_dir / "readiness.json")
    slots = load_slots_array(cell_dir / "slots.json")
    process = parse_time_output((cell_dir / "server-time.log").read_text())
    pid = int((cell_dir / "server-pid.txt").read_text().strip())
    served = probe.get("served_records", [])
    raw = probe.get("raw_calls", [])
    fingerprints = probe.get("unseen_prompt_fingerprints", {})
    workload = contract["workload"]
    if (
        probe.get("experiment_id") != "E21b"
        or probe.get("policy") != policy
        or probe.get("repetition") != repetition
        or probe.get("identity_sha256") != contract["identity_sha256"]
        or probe.get("client_identity_sha256") != contract["client_identity_sha256"]
        or len(served) != workload["served_requests_per_cell"]
        or [record.get("task_id") for record in served] != workload["task_sequence"]
        or len(fingerprints) != workload["unique_prompts"]
        or len(set(fingerprints.values())) != workload["unique_prompts"]
        or readiness.get("status") != "ok"
        or not isinstance(readiness.get("ready_ms"), (int, float))
        or not math.isfinite(float(readiness["ready_ms"]))
        or len(slots) != 1
        or process["maximum_rss_kib"] is None
        or (cell_dir / "server-shell-exit.txt").read_text().strip()
        not in {str(value) for value in contract["acceptance"]["server_exit_statuses"]}
    ):
        raise ValueError(f"E21b {policy} r{repetition} cell structure differs")
    observed = recompute_counts(probe)
    process_cpu = validate_process_cpu(
        probe.get("process_cpu"),
        pid=pid,
        requests=len(served),
        elapsed=float(probe["result"]["elapsed_seconds"]),
    )
    registry_wrapper = probe.get("registry")
    registry = (
        registry_wrapper.get("payload", {})
        if isinstance(registry_wrapper, dict)
        else {}
    )
    return {
        "policy": policy,
        "repetition": repetition,
        "recipe": recipe,
        "probe": probe,
        "served_records": served,
        "raw_calls": raw,
        "observed_counts": observed,
        "process_cpu": process_cpu,
        "maximum_rss_kib": process["maximum_rss_kib"],
        "readiness_ms": float(readiness["ready_ms"]),
        "server_pid": pid,
        "all_requests_exact": all(
            validate_call_request(call, contract, tasks, instruction) for call in raw
        ),
        "all_calls_valid": all(valid_call(call) for call in raw),
        "timing_schema_supported": all(supported_timing(call) for call in raw),
        "fingerprints_unseen": not set(fingerprints.values())
        & set(contract["prior_certificate"]["prompt_fingerprints"]),
        "registry_wrapper": registry_wrapper,
        "registry": registry,
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
        raise ValueError("E21b ratio baseline is not positive")
    return candidate / baseline


def summarized_pair(
    baseline_values: list[float], online_values: list[float]
) -> dict[str, Any] | None:
    if not baseline_values or not online_values:
        return None
    baseline = summarize(baseline_values)
    online = summarize(online_values)
    return {
        "requests_per_policy": len(online_values),
        "baseline_user_http_ms": baseline,
        "online_user_http_ms": online,
        "median_latency_ratio": ratio(online["median"], baseline["median"]),
        "p95_latency_ratio": ratio(online["p95"], baseline["p95"]),
    }


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E21b full matrix is not native Arm64")
    runtime = validate_runtime(evidence, contract)
    task_data = load_object(root / contract["inputs"]["tasks"]["path"])
    tasks = {item["id"]: item for item in task_data["tasks"]}
    ordered_cells = [
        validate_cell(
            evidence / "cells" / expected_cell_path(spec),
            contract,
            spec["policy"],
            spec["repetition"],
            tasks,
            task_data["instruction"],
        )
        for spec in contract["execution"]["cell_order"]
    ]
    by_policy = {
        policy: [cell for cell in ordered_cells if cell["policy"] == policy]
        for policy in ("all_uncached", "online")
    }
    baseline = aggregate_policy(by_policy["all_uncached"])
    online = aggregate_policy(by_policy["online"])
    baseline_by_rep = {cell["repetition"]: cell for cell in by_policy["all_uncached"]}
    online_by_rep = {cell["repetition"]: cell for cell in by_policy["online"]}
    paired_mismatches = 0
    baseline_cross_repetition_mismatches = 0
    canonical = baseline_by_rep[1]["served_records"]
    certified_online_ms: list[float] = []
    certified_baseline_ms: list[float] = []
    first_use_online_ms: list[float] = []
    first_use_baseline_ms: list[float] = []
    fallback_online_ms: list[float] = []
    fallback_baseline_ms: list[float] = []
    break_even = []
    workload = contract["workload"]
    tasks_per_cycle = workload["unique_prompts"]
    for repetition in range(1, contract["execution"]["repetitions_per_policy"] + 1):
        baseline_records = baseline_by_rep[repetition]["served_records"]
        online_records = online_by_rep[repetition]["served_records"]
        cumulative_baseline = 0.0
        cumulative_online = 0.0
        cumulative_cycles = []
        first_break_even = None
        for index, (left, right) in enumerate(
            zip(baseline_records, online_records, strict=True)
        ):
            if (
                left["served_index"] != right["served_index"]
                or left["task_id"] != right["task_id"]
                or left["prompt_sha256"] != right["prompt_sha256"]
            ):
                raise ValueError("E21b paired trace identity differs")
            paired_mismatches += left["served_response"] != right["served_response"]
            baseline_cross_repetition_mismatches += (
                left["served_response"] != canonical[index]["served_response"]
            )
            if right["route"] == "certified_cache":
                certified_baseline_ms.append(float(left["user_http_ms"]))
                certified_online_ms.append(float(right["user_http_ms"]))
            elif right["route"] == "unknown_shadow_then_oracle":
                first_use_baseline_ms.append(float(left["user_http_ms"]))
                first_use_online_ms.append(float(right["user_http_ms"]))
            elif right["route"] == "denied_fallback":
                fallback_baseline_ms.append(float(left["user_http_ms"]))
                fallback_online_ms.append(float(right["user_http_ms"]))
            cumulative_baseline += float(left["user_http_ms"])
            cumulative_online += float(right["user_http_ms"])
            if (index + 1) % tasks_per_cycle == 0:
                cycle = (index + 1) // tasks_per_cycle
                cycle_ratio = ratio(cumulative_online, cumulative_baseline)
                cumulative_cycles.append(
                    {"cycle": cycle, "cumulative_latency_ratio": cycle_ratio}
                )
                if first_break_even is None and cycle_ratio <= 1.0:
                    first_break_even = cycle
        break_even.append(
            {
                "repetition": repetition,
                "first_cumulative_break_even_cycle": first_break_even,
                "cumulative_cycles": cumulative_cycles,
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
    tail_boundaries = {
        "certified_steady_state": summarized_pair(
            certified_baseline_ms, certified_online_ms
        ),
        "synchronous_first_use": summarized_pair(
            first_use_baseline_ms, first_use_online_ms
        ),
        "denied_fallback": summarized_pair(fallback_baseline_ms, fallback_online_ms),
    }
    expected = contract["acceptance"]
    online_cells = by_policy["online"]
    baseline_cells = by_policy["all_uncached"]

    def online_shape(cell: dict[str, Any]) -> bool:
        routes = cell["probe"]["result"]["route_counts"]
        admissions = cell["probe"]["result"]["admission_counts"]
        return (
            set(routes)
            <= {"unknown_shadow_then_oracle", "certified_cache", "denied_fallback"}
            and routes.get("unknown_shadow_then_oracle", 0)
            == expected["unknown_routes"]
            and routes.get("certified_cache", 0) >= expected["minimum_certified_routes"]
            and routes.get("denied_fallback", 0)
            <= expected["maximum_denied_fallback_routes"]
            and routes.get("certified_cache", 0) + routes.get("denied_fallback", 0)
            == expected["known_routes"]
            and set(admissions)
            <= {"certified", "denied", "retained", "retained_denial"}
            and admissions.get("certified", 0)
            >= expected["minimum_certified_transitions"]
            and admissions.get("denied", 0) <= expected["maximum_denied_transitions"]
            and admissions.get("certified", 0) + admissions.get("denied", 0)
            == expected["unknown_routes"]
            and admissions.get("retained", 0) == routes.get("certified_cache", 0)
            and admissions.get("retained_denial", 0) == routes.get("denied_fallback", 0)
        )

    def registry_valid(cell: dict[str, Any]) -> bool:
        wrapper = cell["registry_wrapper"]
        payload = cell["registry"]
        admissions = cell["probe"]["result"]["admission_counts"]
        return (
            isinstance(wrapper, dict)
            and wrapper.get("payload_sha256") == sha256_value(payload)
            and payload.get("identity_sha256") == identity_sha256(contract["identity"])
            and len(payload.get("certified", {})) == admissions.get("certified", 0)
            and len(payload.get("denied", {})) == admissions.get("denied", 0)
            and not set(payload.get("certified", {})) & set(payload.get("denied", {}))
        )

    validity_gates = {
        "native_arm64": True,
        "exact_e7c_service_binary_and_client": True,
        "complete_reverse_balanced_fresh_process_matrix": len(ordered_cells)
        == contract["execution"]["total_cells"],
        "all_30_prompts_unseen_to_e13b": all(
            cell["fingerprints_unseen"] for cell in ordered_cells
        ),
        "exact_openai_compatible_requests": all(
            cell["all_requests_exact"] for cell in ordered_cells
        ),
        "supported_timing_schema": all(
            cell["timing_schema_supported"] for cell in ordered_cells
        ),
        "zero_request_failures": baseline["request_failures"] == 0
        and online["request_failures"] == 0
        and all(cell["all_calls_valid"] for cell in ordered_cells),
        "full_reference_quality_preserved": baseline["reference_prediction_mismatches"]
        == 0
        and online["reference_prediction_mismatches"] == 0
        and baseline["correct"] == workload["correct_per_cell"] * len(baseline_cells)
        and online["correct"] == workload["correct_per_cell"] * len(online_cells),
        "exact_online_outputs_match_paired_uncached": paired_mismatches
        == expected["online_vs_uncached_response_mismatches"],
        "unknown_cached_attempts_never_served": all(
            record["shadow_cached_attempt_served"] is False
            for cell in online_cells
            for record in cell["served_records"]
        ),
        "adaptive_route_and_admission_bounds": all(
            online_shape(cell) for cell in online_cells
        ),
        "registry_integrity_and_bounds": all(
            registry_valid(cell) for cell in online_cells
        ),
        "certified_cache_mechanism": all(
            record["served_call"]["cached_tokens"] >= workload["minimum_cached_tokens"]
            for cell in online_cells
            for record in cell["served_records"]
            if record["route"] == "certified_cache"
        ),
        "denied_fallback_is_uncached": all(
            record["served_call"]["cached_tokens"] == 0
            for cell in online_cells
            for record in cell["served_records"]
            if record["route"] == "denied_fallback"
        ),
        "unknown_shadow_mechanism": all(
            sum(call["role"] == "unknown_cached_shadow" for call in cell["raw_calls"])
            == expected["unknown_shadow_calls"]
            for cell in online_cells
        ),
        "baseline_uncached_mechanism": all(
            cell["registry_wrapper"] is None
            and all(
                call["cache_prompt"] is False and call["cached_tokens"] == 0
                for call in cell["raw_calls"]
            )
            for cell in baseline_cells
        ),
        "raw_call_counts": baseline["actual_http_calls"]
        == expected["baseline_http_calls_per_cell"] * len(baseline_cells)
        and online["actual_http_calls"]
        == expected["online_http_calls_per_cell"] * len(online_cells),
    }
    thresholds = contract["promotion_thresholds"]
    break_even_cycles = [
        item["first_cumulative_break_even_cycle"] for item in break_even
    ]
    steady = tail_boundaries["certified_steady_state"]
    promotion_gates = {
        "minimum_lifecycle_throughput": lifecycle_ratios["throughput"]
        >= thresholds["minimum_throughput_ratio"],
        "maximum_cpu_per_request": lifecycle_ratios["cpu_seconds_per_served_request"]
        <= thresholds["maximum_cpu_ratio"],
        "bounded_lifecycle_p95": lifecycle_ratios["p95_user_latency"]
        <= thresholds["maximum_lifecycle_p95_ratio"],
        "certified_steady_state_p95_nonregression": steady is not None
        and steady["p95_latency_ratio"] <= thresholds["maximum_certified_p95_ratio"],
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
        "valid_openai_online_certificate_promoted"
        if promoted
        else "valid_openai_online_certificate_no_performance_promotion"
        if valid
        else "invalid_openai_online_certificate"
    )
    answers = [
        {
            "task_id": record["task_id"],
            "expected": record["expected"],
            "reference_prediction": record["reference_prediction"],
            "prediction": record["prediction"],
            "exact_response": record["served_response"],
        }
        for record in canonical[: workload["unique_prompts"]]
    ]
    decisions = []
    for cell in sorted(online_cells, key=lambda item: item["repetition"]):
        result = cell["probe"]["result"]
        decisions.append(
            {
                "repetition": cell["repetition"],
                "route_counts": result["route_counts"],
                "admission_counts": result["admission_counts"],
                "certified_transitions": len(cell["registry"].get("certified", {})),
                "denied_transitions": len(cell["registry"].get("denied", {})),
                "revocations": 0,
                "registry_sha256": cell["registry_wrapper"].get("payload_sha256"),
            }
        )
    return {
        "schema_version": 1,
        "experiment_id": "E21b",
        "status": status,
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "runtime": runtime,
        "client": contract["client"],
        "baseline": baseline,
        "online": online,
        "lifecycle_ratios": lifecycle_ratios,
        "tail_boundaries": tail_boundaries,
        "break_even": break_even,
        "quality": {
            "task_score": (
                f"{workload['correct_per_cycle']}/{workload['unique_prompts']}"
            ),
            "baseline_correct": baseline["correct"],
            "online_correct": online["correct"],
            "paired_exact_response_mismatches": paired_mismatches,
            "baseline_cross_repetition_exact_response_mismatches": (
                baseline_cross_repetition_mismatches
            ),
            "answers": answers,
        },
        "online_decisions_per_repetition": decisions,
        "revocation_boundary": {
            "observed_revocations": 0,
            "post_certification_revocation_supported": False,
            "reason": (
                "This bounded policy uses one exact shadow/oracle comparison per "
                "identity-bound transition and does not periodically re-probe a "
                "certified transition. Identity changes invalidate the registry."
            ),
        },
        "validity_gates": validity_gates,
        "promotion_gates": promotion_gates,
        "decision": {
            "valid": valid,
            "safety_certificate_established": valid,
            "performance_policy_promoted": promoted,
            "selected_policy": "online" if promoted else "all_uncached",
            "first_use_tail_regression_retained": (
                tail_boundaries["synchronous_first_use"] is not None
                and tail_boundaries["synchronous_first_use"]["p95_latency_ratio"] > 1.0
            ),
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
