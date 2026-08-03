#!/usr/bin/env python3
"""Run one frozen E13a all-uncached or certificate-controlled trace."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from experiments.e1_ingest import summarize
    from experiments.e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from experiments.e9c_probe import render_tokens, solve_prefix_recipe, system_text
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e9c_probe import render_tokens, solve_prefix_recipe, system_text


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return value


def token_fingerprint(tokens: list[int]) -> str:
    return hashlib.sha256(
        json.dumps(tokens, separators=(",", ":")).encode()
    ).hexdigest()


def cache_decision(
    policy: str,
    fingerprint: str,
    certified: set[str],
    denied: set[str],
) -> tuple[bool, str]:
    if policy == "all_uncached":
        return False, "baseline_uncached"
    if policy != "certificate":
        raise ValueError("unsupported E13a policy")
    if fingerprint in certified:
        return True, "certified_cache"
    if fingerprint in denied:
        return False, "calibration_fallback"
    return False, "unknown_fallback"


def post_json(
    origin: str, path: str, payload: dict[str, Any], timeout: float
) -> tuple[int, dict[str, Any]]:
    parsed = urlsplit(origin)
    connection = http.client.HTTPConnection(
        parsed.hostname, parsed.port, timeout=timeout
    )
    try:
        connection.request(
            "POST",
            path,
            body=json.dumps(payload).encode(),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        value = json.loads(response.read())
        if not isinstance(value, dict):
            raise TypeError(f"{path} returned a non-object")
        return response.status, value
    finally:
        connection.close()


def request_completion(
    origin: str,
    *,
    global_index: int,
    phase: str,
    point_index: int,
    prefix_cardinality: int,
    shared_prefix_tokens: int,
    task_id: str,
    marker: str,
    marker_index: int,
    prompt_tokens: list[int],
    cache_prompt: bool,
    decision: str,
    max_output_tokens: int,
    seed: int,
    timeout: float,
) -> dict[str, Any]:
    fingerprint = token_fingerprint(prompt_tokens)
    started = time.perf_counter_ns()
    try:
        status, response = post_json(
            origin,
            "/completion",
            {
                "prompt": prompt_tokens,
                "n_predict": max_output_tokens,
                "temperature": 0.0,
                "seed": seed,
                "cache_prompt": cache_prompt,
                "stream": False,
            },
            timeout,
        )
        http_ms = (time.perf_counter_ns() - started) / 1_000_000
        timings = response.get("timings")
        timings = timings if isinstance(timings, dict) else {}
        return {
            "global_index": global_index,
            "phase": phase,
            "point_index": point_index,
            "prefix_cardinality": prefix_cardinality,
            "shared_prefix_tokens": shared_prefix_tokens,
            "task_id": task_id,
            "prefix_marker": marker,
            "prefix_marker_index": marker_index,
            "prompt_tokens": len(prompt_tokens),
            "prompt_sha256": fingerprint,
            "cache_prompt": cache_prompt,
            "decision": decision,
            "http_status": status,
            "response": response.get("content"),
            "stop_type": response.get("stop_type"),
            "generated_tokens": timings.get("predicted_n"),
            "cached_tokens": timings.get("cache_n"),
            "evaluated_prompt_tokens": timings.get("prompt_n"),
            "response_tokens_cached": response.get("tokens_cached"),
            "response_tokens_evaluated": response.get("tokens_evaluated"),
            "encode_ms": timings.get("prompt_ms"),
            "decode_ms": timings.get("predicted_ms"),
            "http_ms": http_ms,
            "error": None,
        }
    except Exception as error:
        return {
            "global_index": global_index,
            "phase": phase,
            "point_index": point_index,
            "prefix_cardinality": prefix_cardinality,
            "shared_prefix_tokens": shared_prefix_tokens,
            "task_id": task_id,
            "prefix_marker": marker,
            "prefix_marker_index": marker_index,
            "prompt_tokens": len(prompt_tokens),
            "prompt_sha256": fingerprint,
            "cache_prompt": cache_prompt,
            "decision": decision,
            "http_status": None,
            "response": None,
            "stop_type": None,
            "generated_tokens": None,
            "cached_tokens": None,
            "evaluated_prompt_tokens": None,
            "response_tokens_cached": None,
            "response_tokens_evaluated": None,
            "encode_ms": None,
            "decode_ms": None,
            "http_ms": (time.perf_counter_ns() - started) / 1_000_000,
            "error": f"{type(error).__name__}: {error}",
        }


def measured_values(records: list[dict[str, Any]], name: str) -> list[float]:
    values = []
    for record in records:
        value = record.get(name)
        if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
            values.append(float(value))
    return values


def optional_summary(
    records: list[dict[str, Any]], name: str
) -> dict[str, float] | None:
    values = measured_values(records, name)
    return summarize(values) if values else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument(
        "--policy", choices=("all_uncached", "certificate"), required=True
    )
    parser.add_argument("--repetition", type=int, choices=(1, 2), required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_object(args.contract)
    tasks_manifest = load_object(args.tasks)
    if contract.get("experiment_id") != "E13a":
        raise ValueError("unsupported contract")
    workload = contract["workload"]
    construction = contract["prompt_construction"]
    task_by_id = {task["id"]: task for task in tasks_manifest["tasks"]}
    measured_tasks = [task_by_id[name] for name in workload["measured_task_ids"]]
    warmup_task = task_by_id[workload["warmup_task_id"]]
    markers = construction["variant_markers"]
    marker_token_ids = construction["variant_marker_token_ids"]
    certified = {
        item["prompt_sha256"] for item in contract["policy"]["certified_allowlist"]
    }
    denied = {item["prompt_sha256"] for item in contract["policy"]["fallback_denylist"]}
    if certified & denied:
        raise ValueError("E13a certificate sets overlap")

    prepared_requests: list[dict[str, Any]] = []
    global_index = 0
    for point_index, point in enumerate(workload["point_order"]):
        cardinality = point["prefix_cardinality"]
        shared_tokens = point["shared_prefix_tokens"]
        recipe = solve_prefix_recipe(
            args.url,
            shared_tokens,
            markers,
            marker_token_ids,
            construction["instruction_suffix"],
            warmup_task["prompt"],
            workload["timeout_seconds"],
        )
        active_markers = markers[:cardinality]
        required_task_ids = sorted(
            set(workload["measured_task_ids"] + [workload["warmup_task_id"]])
        )
        prompt_map: dict[tuple[str, str], list[int]] = {}
        for marker_index, marker in enumerate(active_markers):
            system = system_text(
                recipe["common_filler_repetitions"],
                marker,
                construction["instruction_suffix"],
            )
            for task_id in required_task_ids:
                tokens = render_tokens(
                    args.url,
                    system,
                    task_by_id[task_id]["prompt"],
                    workload["timeout_seconds"],
                )
                if tokens[:shared_tokens] != recipe["common_prefix_token_ids"]:
                    raise ValueError("E13a prompt changed its common prefix")
                if tokens[shared_tokens] != marker_token_ids[marker_index]:
                    raise ValueError("E13a prompt changed its marker boundary")
                if len(tokens) > construction["maximum_prompt_tokens"]:
                    raise ValueError("E13a prompt exceeds context contract")
                prompt_map[(marker, task_id)] = tokens

        point_requests: list[tuple[str, int, dict[str, Any]]] = [
            ("point_warmup", index, warmup_task) for index in range(cardinality)
        ] + [
            ("measured", index % cardinality, task)
            for index, task in enumerate(measured_tasks)
        ]
        for phase, marker_index, task in point_requests:
            marker = active_markers[marker_index]
            tokens = prompt_map[(marker, task["id"])]
            fingerprint = token_fingerprint(tokens)
            use_cache, decision = cache_decision(
                args.policy, fingerprint, certified, denied
            )
            prepared_requests.append(
                {
                    "global_index": global_index,
                    "phase": phase,
                    "point_index": point_index,
                    "prefix_cardinality": cardinality,
                    "shared_prefix_tokens": shared_tokens,
                    "task_id": task["id"],
                    "marker": marker,
                    "marker_index": marker_index,
                    "prompt_tokens": tokens,
                    "cache_prompt": use_cache,
                    "decision": decision,
                }
            )
            global_index += 1

    if len(prepared_requests) != workload["trace_requests"]:
        raise ValueError("E13a prepared trace count differs from contract")
    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = read_process_cpu(args.server_pid)
    started = time.perf_counter_ns()
    records = [
        request_completion(
            args.url,
            **request,
            max_output_tokens=workload["maximum_output_tokens"],
            seed=workload["seed"],
            timeout=workload["timeout_seconds"],
        )
        for request in prepared_requests
    ]
    elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
    cpu_after = read_process_cpu(args.server_pid)
    process_cpu = summarize_process_cpu(
        cpu_before,
        cpu_after,
        clock_ticks_per_second=clock_ticks,
        measured_requests=len(records),
        elapsed_seconds=elapsed,
    )
    measured = [record for record in records if record["phase"] == "measured"]
    if (
        len(records) != workload["trace_requests"]
        or len(measured) != workload["measured_requests"]
    ):
        raise ValueError("E13a trace count differs from contract")
    result = {
        "elapsed_seconds": elapsed,
        "requests_per_second": len(records) / elapsed,
        "request_failures": sum(
            record["http_status"] != 200
            or record["error"] is not None
            or not isinstance(record["response"], str)
            for record in records
        ),
        "http_ms": optional_summary(records, "http_ms"),
        "encode_ms": optional_summary(records, "encode_ms"),
        "decode_ms": optional_summary(records, "decode_ms"),
        "cached_tokens": optional_summary(records, "cached_tokens"),
        "decision_counts": {
            name: sum(record["decision"] == name for record in records)
            for name in (
                "baseline_uncached",
                "certified_cache",
                "calibration_fallback",
                "unknown_fallback",
            )
        },
    }
    output = {
        "schema_version": 1,
        "experiment_id": "E13a",
        "parameters": {
            "policy": args.policy,
            "repetition": args.repetition,
            "server_pid": args.server_pid,
            "trace_requests": len(records),
            "measured_requests": len(measured),
            "client_concurrency": workload["client_concurrency"],
            "seed": workload["seed"],
            "maximum_output_tokens": workload["maximum_output_tokens"],
        },
        "records": records,
        "process_cpu": process_cpu,
        "result": result,
    }
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
