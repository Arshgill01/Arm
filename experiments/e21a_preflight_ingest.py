#!/usr/bin/env python3
"""Validate the bounded native E21a online-certificate preflight."""

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
    from experiments.e21a_online_policy import valid_call
    from experiments.evidence_readiness import load_slots_array
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import load_object, sha256_file
    from e9a_ingest import expected_server_argv
    from e13b_ingest import validate_process_cpu, validate_runtime
    from e21a_online_policy import valid_call
    from evidence_readiness import load_slots_array


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E21a-preflight"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E21a preflight contract differs")
    for name, item in contract["inputs"].items():
        if sha256_file(root / item["path"]) != item["sha256"]:
            raise ValueError(f"E21a preflight input differs for {name}")
    return contract


def validate_recipe(
    recipe: dict[str, Any], contract: dict[str, Any], policy: str
) -> dict[str, Any]:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("experiment_id") != "E21a-preflight"
        or recipe.get("policy") != policy
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
    ):
        raise ValueError("E21a preflight recipe differs")
    if recipe.get("argv") != expected_server_argv(
        server,
        model_path,
        candidate=contract["selected"]["candidate"],
        profile_name="e7c_final",
    ):
        raise ValueError("E21a preflight server argv differs")
    return recipe


def validate_cell(
    cell_dir: Path, contract: dict[str, Any], policy: str
) -> dict[str, Any]:
    recipe = validate_recipe(load_object(cell_dir / "recipe.json"), contract, policy)
    probe = load_object(cell_dir / "probe.json")
    readiness = load_object(cell_dir / "readiness.json")
    slots = load_slots_array(cell_dir / "slots.json")
    process = parse_time_output((cell_dir / "server-time.log").read_text())
    if (
        probe.get("experiment_id") != "E21a-preflight"
        or probe.get("policy") != policy
        or probe.get("identity_sha256") != contract["identity_sha256"]
        or probe.get("result", {}).get("served_requests")
        != contract["workload"]["served_requests"]
        or readiness.get("status") != "ok"
        or not isinstance(readiness.get("ready_ms"), (int, float))
        or not math.isfinite(readiness["ready_ms"])
        or len(slots) != 1
        or (cell_dir / "server-shell-exit.txt").read_text().strip()
        not in {str(value) for value in contract["acceptance"]["server_exit_statuses"]}
    ):
        raise ValueError(f"E21a preflight {policy} cell differs")
    served = probe.get("served_records", [])
    raw = probe.get("raw_calls", [])
    if (
        len(served) != contract["workload"]["served_requests"]
        or [record.get("task_id") for record in served]
        != contract["workload"]["task_sequence"]
        or any(not valid_call(record.get("served_call", {})) for record in served)
    ):
        raise ValueError(f"E21a preflight {policy} trace differs")
    process_cpu = validate_process_cpu(
        probe.get("process_cpu"),
        pid=int((cell_dir / "server-pid.txt").read_text()),
        requests=len(served),
        elapsed=float(probe["result"]["elapsed_seconds"]),
    )
    return {
        "policy": policy,
        "recipe": recipe,
        "probe": probe,
        "readiness_ms": float(readiness["ready_ms"]),
        "maximum_rss_kib": process["maximum_rss_kib"],
        "process_cpu": process_cpu,
        "served_records": served,
        "raw_calls": raw,
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
            raise ValueError("E21a preflight comparison identity differs")
        mismatches += left["served_response"] != right["served_response"]
    return mismatches


def aggregate(cell: dict[str, Any]) -> dict[str, Any]:
    records = cell["served_records"]
    probe = cell["probe"]
    return {
        "served_requests": len(records),
        "actual_http_calls": len(cell["raw_calls"]),
        "served_requests_per_second": probe["result"][
            "served_requests_per_second"
        ],
        "user_http_ms": summarize([float(item["user_http_ms"]) for item in records]),
        "cpu_seconds_per_served_request": cell["process_cpu"]["seconds_per_request"],
        "maximum_rss_kib": cell["maximum_rss_kib"],
        "readiness_ms": cell["readiness_ms"],
        "request_failures": probe["result"]["request_failures"],
        "correct": probe["result"]["correct"],
        "reference_prediction_mismatches": probe["result"][
            "reference_prediction_mismatches"
        ],
        "answers": [
            {
                "served_index": item["served_index"],
                "task_id": item["task_id"],
                "prompt_sha256": item["prompt_sha256"],
                "response": item["served_response"],
                "prediction": item["prediction"],
                "expected": item["expected"],
                "reference_prediction": item["reference_prediction"],
                "route": item["route"],
            }
            for item in records
        ],
    }


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E21a preflight is not native Arm64")
    runtime = validate_runtime(evidence, contract)
    cells = {
        policy: validate_cell(evidence / "cells" / f"{index:02d}-{policy}", contract, policy)
        for index, policy in enumerate(("all_uncached", "online"), start=1)
    }
    baseline_records = cells["all_uncached"]["served_records"]
    online_records = cells["online"]["served_records"]
    mismatches = comparison_mismatches(baseline_records, online_records)
    baseline = aggregate(cells["all_uncached"])
    online = aggregate(cells["online"])
    online_probe = cells["online"]["probe"]
    registry = online_probe.get("registry", {}).get("payload", {})
    expected = contract["acceptance"]
    route_counts = online_probe["result"]["route_counts"]
    admission_counts = online_probe["result"]["admission_counts"]
    certified_records = [
        item for item in online_records if item["route"] == "certified_cache"
    ]
    shadow_calls = [
        item for item in cells["online"]["raw_calls"] if item["role"] == "unknown_cached_shadow"
    ]
    gates = {
        "native_arm64": True,
        "exact_e7c_service": True,
        "all_prompts_unseen_to_e13b": all(
            fingerprint not in set(contract["prior_certificate"]["prompt_fingerprints"])
            for fingerprint in online_probe["unseen_prompt_fingerprints"].values()
        ),
        "zero_request_failures": baseline["request_failures"] == 0
        and online["request_failures"] == 0,
        "exact_online_outputs_match_uncached": mismatches
        == expected["online_vs_uncached_response_mismatches"],
        "reference_answers_preserved": online["reference_prediction_mismatches"]
        == baseline["reference_prediction_mismatches"],
        "unknown_cached_attempts_never_served": all(
            item["shadow_cached_attempt_served"] is False for item in online_records
        ),
        "frozen_route_counts": route_counts == expected["online_route_counts"],
        "frozen_admission_counts": admission_counts
        == expected["online_admission_counts"],
        "registry_counts": len(registry.get("certified", {}))
        == expected["certified_transitions"]
        and len(registry.get("denied", {})) == expected["denied_transitions"],
        "certified_cache_mechanism": len(certified_records)
        == expected["certified_served_requests"]
        and all(
            item["served_call"]["cached_tokens"]
            >= contract["workload"]["minimum_cached_tokens"]
            for item in certified_records
        ),
        "unknown_shadow_mechanism": len(shadow_calls)
        == expected["unknown_shadow_calls"],
        "baseline_uncached_mechanism": all(
            item["cached_tokens"] == 0 for item in cells["all_uncached"]["raw_calls"]
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
        "cpu_seconds_per_served_request": online[
            "cpu_seconds_per_served_request"
        ]
        / baseline["cpu_seconds_per_served_request"],
    }
    return {
        "schema_version": 1,
        "experiment_id": "E21a-preflight",
        "status": (
            "valid_online_transition_certificate_preflight"
            if passed
            else "invalid_online_transition_certificate_preflight"
        ),
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "runtime": runtime,
        "baseline": baseline,
        "online": online,
        "ratios_diagnostic_only": ratios,
        "online_decisions": {
            "route_counts": route_counts,
            "admission_counts": admission_counts,
            "certified_transitions": len(registry.get("certified", {})),
            "denied_transitions": len(registry.get("denied", {})),
            "registry_sha256": online_probe["registry"]["payload_sha256"],
        },
        "quality": {
            "online_vs_uncached_response_mismatches": mismatches,
            "baseline_correct": baseline["correct"],
            "online_correct": online["correct"],
        },
        "gates": gates,
        "decision": {
            "full_experiment_authorized": passed,
            "native_performance_claim_allowed": False,
            "preflight_timings_are_diagnostic_only": True,
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
    print(json.dumps({"status": result["status"], "gates": result["gates"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
