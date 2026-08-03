#!/usr/bin/env python3
"""Run one simultaneous two-worker E19a temporal trace."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_inference_probe import (
        read_process_cpu,
        summarize_process_cpu,
    )
    from experiments.e9c_probe import render_tokens, solve_prefix_recipe, system_text
    from experiments.e13b_probe import (
        cache_decision,
        load_object,
        optional_summary,
        request_completion,
        token_fingerprint,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e9c_probe import render_tokens, solve_prefix_recipe, system_text
    from e13b_probe import (
        cache_decision,
        load_object,
        optional_summary,
        request_completion,
        token_fingerprint,
    )


def prepare_trace(
    urls: list[str],
    contract: dict[str, Any],
    tasks_manifest: dict[str, Any],
    policy: str,
) -> list[dict[str, Any]]:
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
    denied = {
        item["prompt_sha256"] for item in contract["policy"]["fallback_denylist"]
    }
    if certified & denied:
        raise ValueError("E19a certificate sets overlap")

    prepared: list[dict[str, Any]] = []
    global_index = 0
    for point_index, point in enumerate(workload["point_order"]):
        cardinality = point["prefix_cardinality"]
        shared_tokens = point["shared_prefix_tokens"]
        recipe = solve_prefix_recipe(
            urls[0],
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
                worker_tokens = [
                    render_tokens(
                        url,
                        system,
                        task_by_id[task_id]["prompt"],
                        workload["timeout_seconds"],
                    )
                    for url in urls
                ]
                if worker_tokens[0] != worker_tokens[1]:
                    raise ValueError("E19a worker tokenization differs")
                tokens = worker_tokens[0]
                if tokens[:shared_tokens] != recipe["common_prefix_token_ids"]:
                    raise ValueError("E19a prompt changed its common prefix")
                if tokens[shared_tokens] != marker_token_ids[marker_index]:
                    raise ValueError("E19a prompt changed its marker boundary")
                if len(tokens) > construction["maximum_prompt_tokens"]:
                    raise ValueError("E19a prompt exceeds context contract")
                prompt_map[(marker, task_id)] = tokens

        specification = workload["point_warmups"][point_index]
        point_requests = [
            ("point_warmup", item) for item in specification["requests"]
        ] + [("measured", item) for item in specification["measured_requests"]]
        if [item[1]["task_id"] for item in point_requests[cardinality:]] != [
            task["id"] for task in measured_tasks
        ]:
            raise ValueError("E19a measured task sequence differs")
        for phase, request in point_requests:
            marker_index = request["prefix_marker_index"]
            marker = active_markers[marker_index]
            tokens = prompt_map[(marker, request["task_id"])]
            fingerprint = token_fingerprint(tokens)
            use_cache, decision = cache_decision(
                policy, fingerprint, certified, denied
            )
            if fingerprint != request["prompt_sha256"] or (
                policy == "certificate" and decision != request["expected_decision"]
            ):
                raise ValueError("E19a fingerprint or decision differs")
            worker = 1 + ((point_index + marker_index) % 2)
            prepared.append(
                {
                    "global_index": global_index,
                    "phase": phase,
                    "point_index": point_index,
                    "prefix_cardinality": cardinality,
                    "shared_prefix_tokens": shared_tokens,
                    "task_id": request["task_id"],
                    "marker": marker,
                    "marker_index": marker_index,
                    "prompt_tokens": tokens,
                    "cache_prompt": use_cache,
                    "decision": decision,
                    "worker": worker,
                }
            )
            global_index += 1
    if len(prepared) != workload["trace_requests"]:
        raise ValueError("E19a prepared trace count differs")
    return prepared


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="append", required=True)
    parser.add_argument("--server-pid", action="append", type=int, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument(
        "--policy", choices=("all_uncached", "certificate"), required=True
    )
    parser.add_argument("--repetition", type=int, choices=(1, 2), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.url) != 2 or len(args.server_pid) != 2:
        raise ValueError("E19a requires exactly two workers")
    contract = load_object(args.contract)
    if contract.get("experiment_id") != "E19a":
        raise ValueError("unsupported E19a contract")
    prepared = prepare_trace(
        args.url, contract, load_object(args.tasks), args.policy
    )
    by_worker = [
        [request for request in prepared if request["worker"] == worker]
        for worker in (1, 2)
    ]
    expected_inventory = contract["execution"]["worker_request_inventory"]
    for worker_index, requests in enumerate(by_worker):
        expected = expected_inventory[worker_index]
        if len(requests) != expected["trace_requests"] or sum(
            request["phase"] == "measured" for request in requests
        ) != expected["measured_requests"]:
            raise ValueError("E19a worker assignment differs")

    barrier = threading.Barrier(3)
    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = [read_process_cpu(pid) for pid in args.server_pid]
    outputs: list[dict[str, Any] | None] = [None, None]
    failures: list[BaseException] = []
    start_ns = [0, 0]

    def run_worker(worker_index: int) -> None:
        try:
            pid = args.server_pid[worker_index]
            barrier.wait(timeout=30)
            start_ns[worker_index] = time.perf_counter_ns()
            records = []
            for request in by_worker[worker_index]:
                request_arguments = dict(request)
                worker = request_arguments.pop("worker")
                record = request_completion(
                    args.url[worker_index],
                    **request_arguments,
                    max_output_tokens=contract["workload"]["maximum_output_tokens"],
                    seed=contract["workload"]["seed"],
                    timeout=contract["workload"]["timeout_seconds"],
                )
                record["worker"] = worker
                records.append(record)
            elapsed = (time.perf_counter_ns() - start_ns[worker_index]) / 1e9
            cpu_after = read_process_cpu(pid)
            process_cpu = summarize_process_cpu(
                cpu_before[worker_index],
                cpu_after,
                clock_ticks_per_second=clock_ticks,
                measured_requests=len(records),
                elapsed_seconds=elapsed,
            )
            outputs[worker_index] = {
                "worker": worker_index + 1,
                "parameters": {
                    "url": args.url[worker_index],
                    "server_pid": pid,
                    "trace_requests": len(records),
                    "measured_requests": sum(
                        record["phase"] == "measured" for record in records
                    ),
                },
                "records": records,
                "process_cpu": process_cpu,
                "elapsed_seconds": elapsed,
                "requests_per_second": len(records) / elapsed,
            }
        except BaseException as error:
            failures.append(error)

    threads = [
        threading.Thread(target=run_worker, args=(index,), daemon=False)
        for index in range(2)
    ]
    for thread in threads:
        thread.start()
    wall_started = time.perf_counter_ns()
    barrier.wait(timeout=30)
    for thread in threads:
        thread.join()
    wall_elapsed = (time.perf_counter_ns() - wall_started) / 1e9
    if failures:
        raise failures[0]
    workers = [output for output in outputs if output is not None]
    records = sorted(
        (record for worker in workers for record in worker["records"]),
        key=lambda record: record["global_index"],
    )
    if len(workers) != 2 or len(records) != len(prepared):
        raise ValueError("E19a simultaneous trace is incomplete")
    result = {
        "elapsed_seconds": wall_elapsed,
        "requests_per_second": len(records) / wall_elapsed,
        "measurement_start_skew_ms": abs(start_ns[0] - start_ns[1]) / 1e6,
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
        "experiment_id": "E19a",
        "policy": args.policy,
        "repetition": args.repetition,
        "assignment": contract["mechanism"]["prefix_affinity_assignment"],
        "workers": workers,
        "records": records,
        "result": result,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
