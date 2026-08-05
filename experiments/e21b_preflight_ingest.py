#!/usr/bin/env python3
"""Validate the full-quality E21b OpenAI-compatible native preflight."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e9a_ingest import expected_server_argv
    from experiments.e13b_ingest import validate_process_cpu, validate_runtime
    from experiments.e21a_online_policy import identity_sha256, sha256_value, valid_call
    from experiments.e21b_openai_probe import canonical_sha256, openai_request_payload
    from experiments.evidence_readiness import load_slots_array
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import load_object, sha256_file
    from e9a_ingest import expected_server_argv
    from e13b_ingest import validate_process_cpu, validate_runtime
    from e21a_online_policy import identity_sha256, sha256_value, valid_call
    from e21b_openai_probe import canonical_sha256, openai_request_payload
    from evidence_readiness import load_slots_array


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E21b-preflight"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E21b preflight contract differs")
    for name, item in contract["inputs"].items():
        if sha256_file(root / item["path"]) != item["sha256"]:
            raise ValueError(f"E21b preflight input differs for {name}")
    return contract


def validate_recipe(
    recipe: dict[str, Any], contract: dict[str, Any], policy: str
) -> dict[str, Any]:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("experiment_id") != "E21b-preflight"
        or recipe.get("policy") != policy
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


def recompute_counts(probe: dict[str, Any]) -> dict[str, Any]:
    served = probe.get("served_records", [])
    raw = probe.get("raw_calls", [])
    result = probe.get("result", {})
    observed = {
        "served_requests": len(served),
        "actual_http_calls": len(raw),
        "route_counts": dict(
            sorted(Counter(item.get("route") for item in served).items())
        ),
        "admission_counts": dict(
            sorted(
                Counter(
                    item.get("admission")
                    for item in served
                    if item.get("admission") is not None
                ).items()
            )
        ),
        "correct": sum(item.get("correct") is True for item in served),
        "reference_prediction_mismatches": sum(
            item.get("reference_match") is not True for item in served
        ),
        "request_failures": sum(item.get("error") is not None for item in raw),
    }
    for name, value in observed.items():
        if result.get(name) != value:
            raise ValueError(f"E21b observed {name} summary differs from raw records")
    return observed


def validate_call_request(
    call: dict[str, Any],
    contract: dict[str, Any],
    tasks: dict[str, dict[str, Any]],
    instruction: str,
) -> bool:
    task = tasks.get(call.get("task_id"))
    if task is None or type(call.get("cache_prompt")) is not bool:
        return False
    expected = openai_request_payload(
        candidate=contract["selected"]["candidate"],
        instruction=instruction,
        task=task,
        cache_prompt=call["cache_prompt"],
        maximum_output_tokens=contract["workload"]["maximum_output_tokens"],
        seed=contract["workload"]["seed"],
    )
    return (
        call.get("api_path") == contract["client"]["api_path"]
        and call.get("request_payload") == expected
        and call.get("request_payload_sha256") == canonical_sha256(expected)
    )


def validate_cell(
    cell_dir: Path,
    contract: dict[str, Any],
    policy: str,
    tasks: dict[str, dict[str, Any]],
    instruction: str,
) -> dict[str, Any]:
    recipe = validate_recipe(load_object(cell_dir / "recipe.json"), contract, policy)
    probe = load_object(cell_dir / "probe.json")
    readiness = load_object(cell_dir / "readiness.json")
    slots = load_slots_array(cell_dir / "slots.json")
    process = parse_time_output((cell_dir / "server-time.log").read_text())
    pid = int((cell_dir / "server-pid.txt").read_text())
    served = probe.get("served_records", [])
    raw = probe.get("raw_calls", [])
    if (
        probe.get("experiment_id") != "E21b-preflight"
        or probe.get("policy") != policy
        or probe.get("identity_sha256") != contract["identity_sha256"]
        or probe.get("client_identity_sha256") != contract["client_identity_sha256"]
        or len(served) != contract["workload"]["served_requests"]
        or [record.get("task_id") for record in served]
        != contract["workload"]["task_sequence"]
        or readiness.get("status") != "ok"
        or not isinstance(readiness.get("ready_ms"), (int, float))
        or not math.isfinite(float(readiness["ready_ms"]))
        or len(slots) != 1
        or process["maximum_rss_kib"] is None
        or (cell_dir / "server-shell-exit.txt").read_text().strip()
        not in {str(value) for value in contract["acceptance"]["server_exit_statuses"]}
        or any(
            not validate_call_request(call, contract, tasks, instruction)
            for call in raw
        )
    ):
        raise ValueError(f"E21b {policy} cell differs")
    observed = recompute_counts(probe)
    process_cpu = validate_process_cpu(
        probe.get("process_cpu"),
        pid=pid,
        requests=len(served),
        elapsed=float(probe["result"]["elapsed_seconds"]),
    )
    return {
        "policy": policy,
        "recipe": recipe,
        "probe": probe,
        "served_records": served,
        "raw_calls": raw,
        "observed_counts": observed,
        "process_cpu": process_cpu,
        "maximum_rss_kib": process["maximum_rss_kib"],
        "readiness_ms": float(readiness["ready_ms"]),
    }


def aggregate(cell: dict[str, Any]) -> dict[str, Any]:
    records = cell["served_records"]
    result = cell["probe"]["result"]
    return {
        "served_requests": len(records),
        "actual_http_calls": len(cell["raw_calls"]),
        "served_requests_per_second": result["served_requests_per_second"],
        "user_http_ms": summarize([float(item["user_http_ms"]) for item in records]),
        "cpu_seconds_per_served_request": cell["process_cpu"]["seconds_per_request"],
        "maximum_rss_kib": cell["maximum_rss_kib"],
        "readiness_ms": cell["readiness_ms"],
        "request_failures": result["request_failures"],
        "correct": result["correct"],
        "reference_prediction_mismatches": result["reference_prediction_mismatches"],
        "answers": [
            {
                "served_index": item["served_index"],
                "task_id": item["task_id"],
                "response": item["served_response"],
                "prediction": item["prediction"],
                "expected": item["expected"],
                "reference_prediction": item["reference_prediction"],
                "route": item["route"],
                "admission": item["admission"],
            }
            for item in records
        ],
    }


def comparison_mismatches(
    baseline: list[dict[str, Any]], online: list[dict[str, Any]]
) -> int:
    mismatches = 0
    for left, right in zip(baseline, online, strict=True):
        if (
            left["served_index"] != right["served_index"]
            or left["task_id"] != right["task_id"]
            or left["prompt_sha256"] != right["prompt_sha256"]
        ):
            raise ValueError("E21b paired trace identity differs")
        mismatches += left["served_response"] != right["served_response"]
    return mismatches


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E21b preflight is not native Arm64")
    runtime = validate_runtime(evidence, contract)
    task_data = load_object(root / contract["inputs"]["tasks"]["path"])
    tasks = {item["id"]: item for item in task_data["tasks"]}
    cells = {
        policy: validate_cell(
            evidence / "cells" / f"{index:02d}-{policy}",
            contract,
            policy,
            tasks,
            task_data["instruction"],
        )
        for index, policy in enumerate(contract["execution"]["cell_order"], start=1)
    }
    baseline_records = cells["all_uncached"]["served_records"]
    online_records = cells["online"]["served_records"]
    baseline = aggregate(cells["all_uncached"])
    online = aggregate(cells["online"])
    mismatches = comparison_mismatches(baseline_records, online_records)
    online_probe = cells["online"]["probe"]
    routes = online_probe["result"]["route_counts"]
    admissions = online_probe["result"]["admission_counts"]
    registry_wrapper = online_probe.get("registry", {})
    registry = registry_wrapper.get("payload", {})
    expected = contract["acceptance"]
    certified_records = [
        item for item in online_records if item["route"] == "certified_cache"
    ]
    denied_records = [
        item for item in online_records if item["route"] == "denied_fallback"
    ]
    shadow_calls = [
        item
        for item in cells["online"]["raw_calls"]
        if item["role"] == "unknown_cached_shadow"
    ]
    certified_transitions = len(registry.get("certified", {}))
    denied_transitions = len(registry.get("denied", {}))
    allowed_routes = {
        "unknown_shadow_then_oracle",
        "certified_cache",
        "denied_fallback",
    }
    allowed_admissions = {
        "certified",
        "denied",
        "retained",
        "retained_denial",
    }
    gates = {
        "native_arm64": True,
        "exact_e7c_service_and_binary": True,
        "exact_openai_compatible_client": all(
            call["api_path"] == contract["client"]["api_path"]
            for cell in cells.values()
            for call in cell["raw_calls"]
        ),
        "all_30_prompts_unseen_to_e13b": all(
            fingerprint not in set(contract["prior_certificate"]["prompt_fingerprints"])
            for fingerprint in online_probe["unseen_prompt_fingerprints"].values()
        ),
        "zero_request_failures": baseline["request_failures"] == 0
        and online["request_failures"] == 0
        and all(
            valid_call(record["served_call"])
            for cell in cells.values()
            for record in cell["served_records"]
        ),
        "full_reference_quality_preserved": baseline["reference_prediction_mismatches"]
        == 0
        and online["reference_prediction_mismatches"] == 0
        and baseline["correct"] == expected["correct_per_policy"]
        and online["correct"] == expected["correct_per_policy"],
        "exact_online_outputs_match_uncached": mismatches
        == expected["online_vs_uncached_response_mismatches"],
        "unknown_cached_attempts_never_served": all(
            item["shadow_cached_attempt_served"] is False for item in online_records
        ),
        "adaptive_route_shape": set(routes) <= allowed_routes
        and routes.get("unknown_shadow_then_oracle", 0) == expected["unknown_routes"]
        and routes.get("certified_cache", 0) >= expected["minimum_certified_routes"]
        and routes.get("denied_fallback", 0)
        <= expected["maximum_denied_fallback_routes"]
        and routes.get("certified_cache", 0) + routes.get("denied_fallback", 0)
        == expected["known_routes"],
        "adaptive_admission_bounds": set(admissions) <= allowed_admissions
        and admissions.get("certified", 0) >= expected["minimum_certified_transitions"]
        and admissions.get("denied", 0) <= expected["maximum_denied_transitions"]
        and admissions.get("retained", 0) == routes.get("certified_cache", 0)
        and admissions.get("retained_denial", 0) == routes.get("denied_fallback", 0),
        "registry_integrity_and_bounds": registry_wrapper.get("payload_sha256")
        == sha256_value(registry)
        and registry.get("identity_sha256") == identity_sha256(contract["identity"])
        and certified_transitions == admissions.get("certified", 0)
        and denied_transitions == admissions.get("denied", 0)
        and certified_transitions >= expected["minimum_certified_transitions"]
        and denied_transitions <= expected["maximum_denied_transitions"]
        and not set(registry.get("certified", {})) & set(registry.get("denied", {})),
        "certified_cache_mechanism": len(certified_records)
        >= expected["minimum_certified_routes"]
        and all(
            item["served_call"]["cached_tokens"]
            >= contract["workload"]["minimum_cached_tokens"]
            for item in certified_records
        ),
        "denied_fallback_is_uncached": all(
            item["served_call"]["cached_tokens"] == 0 for item in denied_records
        ),
        "unknown_shadow_mechanism": len(shadow_calls)
        == expected["unknown_shadow_calls"],
        "baseline_uncached_mechanism": all(
            call["cache_prompt"] is False and call["cached_tokens"] == 0
            for call in cells["all_uncached"]["raw_calls"]
        ),
        "raw_call_counts": baseline["actual_http_calls"]
        == expected["baseline_http_calls"]
        and online["actual_http_calls"] == expected["online_http_calls"],
    }
    passed = all(gates.values())
    ratios = {
        "throughput": online["served_requests_per_second"]
        / baseline["served_requests_per_second"],
        "median_user_latency": online["user_http_ms"]["median"]
        / baseline["user_http_ms"]["median"],
        "p95_user_latency": online["user_http_ms"]["p95"]
        / baseline["user_http_ms"]["p95"],
        "cpu_seconds_per_served_request": online["cpu_seconds_per_served_request"]
        / baseline["cpu_seconds_per_served_request"],
    }
    return {
        "schema_version": 1,
        "experiment_id": "E21b-preflight",
        "status": (
            "valid_openai_online_certificate_preflight"
            if passed
            else "invalid_openai_online_certificate_preflight"
        ),
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "runtime": runtime,
        "client": contract["client"],
        "baseline": baseline,
        "online": online,
        "ratios_diagnostic_only": ratios,
        "online_decisions": {
            "route_counts": routes,
            "admission_counts": admissions,
            "certified_transitions": certified_transitions,
            "denied_transitions": denied_transitions,
            "registry_sha256": registry_wrapper.get("payload_sha256"),
        },
        "quality": {
            "task_score_per_cycle": f"{contract['workload']['correct_per_cycle']}/30",
            "online_vs_uncached_response_mismatches": mismatches,
            "baseline_correct": baseline["correct"],
            "online_correct": online["correct"],
            "baseline_reference_prediction_mismatches": baseline[
                "reference_prediction_mismatches"
            ],
            "online_reference_prediction_mismatches": online[
                "reference_prediction_mismatches"
            ],
        },
        "gates": gates,
        "decision": {
            "full_experiment_authorized": passed,
            "native_performance_claim_allowed": False,
            "preflight_timings_are_diagnostic_only": True,
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
            {"status": result["status"], "gates": result["gates"]}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
