#!/usr/bin/env python3
"""Validate and score the frozen E4a accept-backlog search."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
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


def validate_run(
    run_dir: Path, backlog: int, contract: dict[str, Any]
) -> dict[str, Any]:
    probe = load_object(run_dir / "probe.json")
    parameters = probe.get("parameters")
    raw_requests = probe.get("requests")
    result = probe.get("result")
    expected = contract["probe"]
    if (
        not isinstance(parameters, dict)
        or not isinstance(raw_requests, list)
        or not isinstance(result, dict)
    ):
        raise ValueError(f"{run_dir.name} has malformed probe evidence")
    expected_parameters = {
        "warmups": expected["warmups"],
        "requests": expected["measured_requests"],
        "concurrency": expected["concurrency"],
        "timeout_seconds": expected["timeout_seconds"],
        "method_mix": expected["method_mix"],
    }
    for key, value in expected_parameters.items():
        if parameters.get(key) != value:
            raise ValueError(f"{run_dir.name} parameter {key} differs from contract")
    if len(raw_requests) != expected["measured_requests"]:
        raise ValueError(f"{run_dir.name} request count differs from contract")
    for index, request in enumerate(raw_requests):
        method = "GET" if index % 2 == 0 else "POST"
        if request.get("index") != index or request.get("method") != method:
            raise ValueError(f"{run_dir.name} contains invalid request {index}")
        if request.get("valid") is True:
            if (
                request.get("status") != contract["acceptance"]["http_status"]
                or request.get("error") is not None
            ):
                raise ValueError(f"{run_dir.name} contains invalid success {index}")
        elif request.get("error") is None and request.get("status") == 200:
            raise ValueError(f"{run_dir.name} contains ambiguous failure {index}")

    failure_count = sum(request.get("valid") is not True for request in raw_requests)
    valid_count = len(raw_requests) - failure_count
    if (
        result.get("failures") != failure_count
        or result.get("valid_responses") != valid_count
    ):
        raise ValueError(f"{run_dir.name} response counts differ from raw evidence")
    status_counts = {
        str(status): sum(request.get("status") == status for request in raw_requests)
        for status in sorted(
            {
                request.get("status")
                for request in raw_requests
                if request.get("status") is not None
            }
        )
    }
    if result.get("status_counts") != status_counts:
        raise ValueError(f"{run_dir.name} status counts differ from raw evidence")

    latencies = [float(request["latency_ms"]) for request in raw_requests]
    latency_summary = summarize(latencies)
    if result.get("latency_ms") != latency_summary:
        raise ValueError(f"{run_dir.name} latency summary differs from raw evidence")
    metrics = load_object(run_dir / "service-metrics.json")
    expected_service_requests = (
        expected["readiness_requests"]
        + expected["warmups"]
        + expected["measured_requests"]
    )
    if (
        metrics.get("requests") != expected_service_requests - failure_count
        or metrics.get("errors") != 0
        or metrics.get("status_counts")
        != {"200": expected_service_requests - failure_count}
    ):
        raise ValueError(f"{run_dir.name} service counters differ from contract")
    process = parse_time_output(
        (run_dir / "server-time.log").read_text(encoding="utf-8")
    )
    if process["exit_status"] != contract["acceptance"]["process_exit_status"]:
        raise ValueError(f"{run_dir.name} service process failed")
    stdout = (run_dir / "server.stdout.log").read_text(encoding="utf-8")
    if f"backlog={backlog}" not in stdout:
        raise ValueError(f"{run_dir.name} lacks backlog runtime evidence")
    if (run_dir / "server.stderr.log").read_text(encoding="utf-8").strip():
        raise ValueError(f"{run_dir.name} emitted unexpected stderr")
    command = json.loads((run_dir / "command.json").read_text(encoding="utf-8"))
    if not isinstance(command, list) or "--backlog" not in command:
        raise ValueError(f"{run_dir.name} command evidence is invalid")
    backlog_index = command.index("--backlog") + 1
    if backlog_index >= len(command) or command[backlog_index] != str(backlog):
        raise ValueError(f"{run_dir.name} command backlog differs")
    maximum_rss_kib = process["maximum_rss_kib"]
    if not isinstance(maximum_rss_kib, int):
        raise ValueError(f"{run_dir.name} lacks maximum RSS evidence")
    return {
        "backlog": backlog,
        "tail_breaches": sum(
            latency > expected["tail_breach_ms"] for latency in latencies
        ),
        "latency_ms": latency_summary,
        "requests_per_second": float(result["requests_per_second"]),
        "failures": failure_count,
        "maximum_rss_kib": maximum_rss_kib,
        "process": process,
        "latencies": latencies,
    }


def select_candidate(candidates: dict[int, dict[str, Any]]) -> int:
    return min(
        candidates,
        key=lambda backlog: (
            candidates[backlog]["total_failures"],
            candidates[backlog]["total_tail_breaches"],
            backlog,
            candidates[backlog]["pooled_latency_ms"]["p95"],
        ),
    )


def evaluate_win(
    candidates: dict[int, dict[str, Any]], selected_backlog: int, contract: dict[str, Any]
) -> dict[str, bool]:
    acceptance = contract["acceptance"]
    default = candidates[5]
    selected = candidates[selected_backlog]
    criteria = {
        "default_tail_reproduced_each_round": all(
            round_data["tail_breaches"]
            >= acceptance["minimum_default_breaches_per_round"]
            for round_data in default["rounds"]
        ),
        "selected_is_larger_than_default": selected_backlog > 5,
        "selected_has_zero_failures": (
            selected["total_failures"]
            <= acceptance["maximum_selected_failures"]
        ),
        "selected_eliminates_tail_breaches": (
            selected["total_tail_breaches"]
            <= acceptance["maximum_selected_total_breaches"]
        ),
        "selected_p95_within_slo": (
            selected["pooled_latency_ms"]["p95"]
            <= acceptance["maximum_selected_p95_latency_ms"]
        ),
        "throughput_guardrail_met": (
            selected["median_round_requests_per_second"]
            >= default["median_round_requests_per_second"]
            * acceptance["minimum_throughput_ratio_to_default"]
        ),
        "rss_guardrail_met": (
            selected["maximum_rss_kib"]
            <= default["maximum_rss_kib"]
            + acceptance["maximum_rss_increase_kib"]
        ),
    }
    return criteria


def build_manifest(
    evidence_dir: Path, contract_path: Path, manifest_path: Path, policy_path: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("experiment_id") != "E4a":
        raise ValueError("contract does not identify E4a")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E4a contract")
    if sha256_file(manifest_path) != contract["inputs"]["manifest_sha256"]:
        raise ValueError("planner manifest checksum differs from contract")
    if sha256_file(policy_path) != contract["inputs"]["policy_sha256"]:
        raise ValueError("planner policy checksum differs from contract")
    if sha256_file(evidence_dir / "planner-manifest.json") != contract["inputs"]["manifest_sha256"]:
        raise ValueError("artifact planner manifest differs from contract")
    if sha256_file(evidence_dir / "planner-policy.json") != contract["inputs"]["policy_sha256"]:
        raise ValueError("artifact planner policy differs from contract")

    execution = load_object(evidence_dir / "search" / "execution.json")
    expected_runs = sum(len(order) for order in contract["execution_order"])
    if len(execution.get("runs", [])) != expected_runs:
        raise ValueError("search execution count differs from contract")
    expected_keys = {
        (round_number, backlog)
        for round_number, order in enumerate(contract["execution_order"], start=1)
        for backlog in order
    }
    run_records = {
        (run["round"], run["backlog"]): run for run in execution["runs"]
    }
    if len(run_records) != expected_runs or set(run_records) != expected_keys:
        raise ValueError("search execution contains duplicate or unexpected runs")
    candidates: dict[int, dict[str, Any]] = {}
    for backlog in contract["candidates"]:
        rounds = []
        pooled_latencies: list[float] = []
        for round_number, order in enumerate(contract["execution_order"], start=1):
            position = order.index(backlog) + 1
            execution_record = run_records.get((round_number, backlog))
            if execution_record is None or execution_record["position"] != position:
                raise ValueError("search execution order differs from contract")
            run_dir = evidence_dir / "search" / execution_record["directory"]
            round_data = validate_run(run_dir, backlog, contract)
            round_data["round"] = round_number
            round_data["position"] = position
            pooled_latencies.extend(round_data.pop("latencies"))
            rounds.append(round_data)
        candidates[backlog] = {
            "backlog": backlog,
            "rounds": rounds,
            "total_tail_breaches": sum(item["tail_breaches"] for item in rounds),
            "total_failures": sum(item["failures"] for item in rounds),
            "pooled_latency_ms": summarize(pooled_latencies),
            "median_round_requests_per_second": statistics.median(
                item["requests_per_second"] for item in rounds
            ),
            "maximum_rss_kib": max(item["maximum_rss_kib"] for item in rounds),
        }

    selected_backlog = select_candidate(candidates)
    criteria = evaluate_win(candidates, selected_backlog, contract)
    won = all(criteria.values())
    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E4a":
        raise ValueError("provenance does not identify E4a")
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E4a",
        "status": "valid_tuner_win" if won else "valid_no_tuner_win",
        "source": {
            "artifact_name": f"e4a-backlog-tuner-{run_id}-{provenance['github_run_attempt']}",
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
        "search": {
            "elapsed_seconds": float(execution["search_elapsed_seconds"]),
            "evaluated_configurations": expected_runs,
            "unique_candidates": len(candidates),
            "execution_order": contract["execution_order"],
        },
        "candidates": {str(key): value for key, value in candidates.items()},
        "selection": {
            "selected_backlog": selected_backlog,
            "criteria": criteria,
            "validated_win": won,
            **contract["selection"],
        },
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
