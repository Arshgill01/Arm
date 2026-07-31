#!/usr/bin/env python3
"""Measure the Pareto64 HTTP decision service under bounded concurrency."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlsplit

try:
    from experiments.e1_ingest import summarize
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize


def request(
    base_url: str, index: int, policy_body: bytes, timeout: float
) -> dict[str, Any]:
    parsed = urlsplit(base_url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    method = "GET" if index % 2 == 0 else "POST"
    headers = {"Accept": "application/json"}
    body = None
    if method == "POST":
        body = policy_body
        headers["Content-Type"] = "application/json"
    started = time.perf_counter_ns()
    try:
        connection.request(method, "/v1/plan", body=body, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000
        valid = (
            response.status == 200
            and isinstance(payload, dict)
            and payload.get("status") == "no_feasible_candidate"
            and payload.get("selected") is None
        )
        return {
            "index": index,
            "method": method,
            "status": response.status,
            "latency_ms": latency_ms,
            "valid": valid,
            "error": None,
        }
    except Exception as error:
        return {
            "index": index,
            "method": method,
            "status": None,
            "latency_ms": (time.perf_counter_ns() - started) / 1_000_000,
            "valid": False,
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        connection.close()


def run_probe(
    base_url: str,
    policy: dict[str, Any],
    warmups: int,
    requests: int,
    concurrency: int,
    timeout: float,
) -> dict[str, Any]:
    policy_body = json.dumps(policy, sort_keys=True).encode("utf-8")
    for index in range(warmups):
        result = request(base_url, index, policy_body, timeout)
        if not result["valid"]:
            raise RuntimeError(f"warmup request failed: {result}")

    started = time.perf_counter_ns()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(
            executor.map(
                lambda index: request(base_url, index, policy_body, timeout),
                range(requests),
            )
        )
    elapsed_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
    valid_results = [result for result in results if result["valid"]]
    failures = [result for result in results if not result["valid"]]
    return {
        "schema_version": 1,
        "experiment_id": "E5a",
        "parameters": {
            "base_url": base_url,
            "warmups": warmups,
            "requests": requests,
            "concurrency": concurrency,
            "timeout_seconds": timeout,
            "method_mix": "alternating GET and POST",
        },
        "result": {
            "valid_responses": len(valid_results),
            "failures": len(failures),
            "elapsed_seconds": elapsed_seconds,
            "requests_per_second": len(valid_results) / elapsed_seconds,
            "latency_ms": summarize(
                [float(result["latency_ms"]) for result in results]
            ),
            "status_counts": {
                str(status): sum(result["status"] == status for result in results)
                for status in sorted(
                    {result["status"] for result in results if result["status"] is not None}
                )
            },
        },
        "requests": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmups", type=int, default=20)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    if arguments.warmups < 0 or arguments.requests <= 0 or arguments.concurrency <= 0:
        raise ValueError("warmups must be non-negative; requests and concurrency positive")
    policy = json.loads(arguments.policy.read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        raise ValueError("policy must be a JSON object")
    evidence = run_probe(
        arguments.url,
        policy,
        arguments.warmups,
        arguments.requests,
        arguments.concurrency,
        arguments.timeout,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0 if evidence["result"]["failures"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
