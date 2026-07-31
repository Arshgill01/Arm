#!/usr/bin/env python3
"""Validate native E5a Pareto64 HTTP concurrency evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_probe(probe: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    expected = contract["probe"]
    parameters = probe.get("parameters")
    requests = probe.get("requests")
    result = probe.get("result")
    if probe.get("experiment_id") != "E5a":
        raise ValueError("probe does not identify E5a")
    if not isinstance(parameters, dict) or not isinstance(requests, list) or not isinstance(result, dict):
        raise ValueError("probe is missing parameters, requests, or result")
    expected_parameters = {
        "warmups": expected["warmups"],
        "requests": expected["measured_requests"],
        "concurrency": expected["concurrency"],
        "timeout_seconds": expected["timeout_seconds"],
        "method_mix": expected["method_mix"],
    }
    for key, value in expected_parameters.items():
        if parameters.get(key) != value:
            raise ValueError(f"probe parameter {key} differs from contract")
    if len(requests) != expected["measured_requests"]:
        raise ValueError("measured request count differs from contract")
    for index, request in enumerate(requests):
        expected_method = "GET" if index % 2 == 0 else "POST"
        if (
            request.get("index") != index
            or request.get("method") != expected_method
            or request.get("status") != contract["acceptance"]["http_status"]
            or request.get("valid") is not True
            or request.get("error") is not None
        ):
            raise ValueError(f"invalid measured HTTP request {index}")

    latencies = [float(request["latency_ms"]) for request in requests]
    recomputed_latency = summarize(latencies)
    if result.get("latency_ms") != recomputed_latency:
        raise ValueError("probe latency summary differs from raw requests")
    if result.get("failures") != 0 or result.get("valid_responses") != len(requests):
        raise ValueError("probe contains failed or missing responses")
    if result.get("status_counts") != {str(contract["acceptance"]["http_status"]): len(requests)}:
        raise ValueError("probe HTTP status counts differ from contract")
    if float(result.get("requests_per_second", 0)) < contract["acceptance"]["minimum_requests_per_second"]:
        raise ValueError("probe throughput missed the frozen minimum")
    if recomputed_latency["p95"] > contract["acceptance"]["maximum_p95_latency_ms"]:
        raise ValueError("probe p95 latency exceeded the frozen maximum")
    return {
        "requests": len(requests),
        "failures": result["failures"],
        "elapsed_seconds": float(result["elapsed_seconds"]),
        "requests_per_second": float(result["requests_per_second"]),
        "latency_ms": recomputed_latency,
        "status_counts": result["status_counts"],
    }


def build_manifest(
    evidence_dir: Path,
    contract_path: Path,
    manifest_path: Path,
    policy_path: Path,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E5a":
        raise ValueError("unsupported E5a contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E5a contract")
    inputs = contract["inputs"]
    if sha256_file(manifest_path) != inputs["manifest_sha256"]:
        raise ValueError("planner manifest checksum differs from contract")
    if sha256_file(policy_path) != inputs["policy_sha256"]:
        raise ValueError("planner policy checksum differs from contract")
    if sha256_file(evidence_dir / "planner-manifest.json") != inputs["manifest_sha256"]:
        raise ValueError("artifact planner manifest differs from contract")
    if sha256_file(evidence_dir / "planner-policy.json") != inputs["policy_sha256"]:
        raise ValueError("artifact planner policy differs from contract")

    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E5a":
        raise ValueError("provenance does not identify E5a")
    performance = validate_probe(load_object(evidence_dir / "probe.json"), contract)

    metrics = load_object(evidence_dir / "service-metrics.json")
    expected_service_requests = (
        contract["probe"]["readiness_requests"]
        + contract["probe"]["warmups"]
        + contract["probe"]["measured_requests"]
    )
    if metrics.get("requests") != expected_service_requests:
        raise ValueError("service request counter differs from the frozen sequence")
    if metrics.get("errors") != contract["acceptance"]["service_error_count"]:
        raise ValueError("service recorded errors")
    if metrics.get("status_counts") != {"200": expected_service_requests}:
        raise ValueError("service status counters differ from the frozen sequence")

    process = parse_time_output(
        (evidence_dir / "server-time.log").read_text(encoding="utf-8")
    )
    if process["exit_status"] != contract["acceptance"]["process_exit_status"]:
        raise ValueError("service process did not exit successfully")
    if process["maximum_rss_kib"] is None or process["maximum_rss_kib"] > contract["acceptance"]["maximum_process_rss_kib"]:
        raise ValueError("service process exceeded the frozen RSS maximum")
    stdout = (evidence_dir / "server.stdout.log").read_text(encoding="utf-8")
    if "Pareto64 listening on http://127.0.0.1:8765" not in stdout:
        raise ValueError("service startup evidence is missing")
    if (evidence_dir / "server.stderr.log").read_text(encoding="utf-8").strip():
        raise ValueError("service emitted unexpected stderr output")

    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E5a",
        "status": "valid_planner_api_concurrency",
        "scope": contract["scope"],
        "source": {
            "artifact_name": f"e5a-planner-api-{run_id}-{provenance['github_run_attempt']}",
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "artifact_retention_days": 90,
        },
        "contract": contract,
        "provenance": provenance,
        "platform": {
            **parse_lscpu((evidence_dir / "lscpu.txt").read_text(encoding="utf-8")),
            "uname": (evidence_dir / "uname.txt").read_text(encoding="utf-8").strip(),
            "python": (evidence_dir / "python-version.txt").read_text(encoding="utf-8").strip(),
        },
        "validation": {
            "input_hashes_match": True,
            "all_responses_fail_closed": True,
            "zero_request_failures": True,
            "service_counters_match": True,
            "latency_slo_passed": True,
            "throughput_slo_passed": True,
            "rss_slo_passed": True,
            "inference_server_claim_allowed": False,
        },
        "performance": performance,
        "service_metrics_before_final_request": metrics,
        "process": process,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    manifest = build_manifest(
        arguments.evidence_dir,
        arguments.contract,
        arguments.manifest,
        arguments.policy,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
