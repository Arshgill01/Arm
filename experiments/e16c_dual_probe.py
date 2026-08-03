#!/usr/bin/env python3
"""Drive two exact E7c workers through a barrier-synchronized workload."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import summarize
    from experiments.e5b_inference_probe import (
        load_object,
        load_reference_predictions,
        read_process_cpu,
        request_case,
        summarize_process_cpu,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import (
        load_object,
        load_reference_predictions,
        read_process_cpu,
        request_case,
        summarize_process_cpu,
    )


def worker_probe(
    *,
    worker: int,
    base_url: str,
    server_pid: int,
    barrier: threading.Barrier,
    tasks_manifest: dict[str, Any],
    references: dict[str, str],
    candidate: str,
    configuration: str,
    repetition: int,
    warmup_task_ids: list[str],
    max_output_tokens: int,
    seed: int,
    timeout: float,
) -> dict[str, Any]:
    instruction = tasks_manifest["instruction"]
    tasks = tasks_manifest["tasks"]
    by_id = {task["id"]: task for task in tasks}
    warmups = [
        request_case(
            base_url,
            index,
            by_id[task_id],
            instruction,
            candidate,
            references[task_id],
            max_output_tokens,
            seed,
            timeout,
            True,
            0,
        )
        for index, task_id in enumerate(warmup_task_ids)
    ]
    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = read_process_cpu(server_pid)
    barrier.wait(timeout=timeout * 2)
    started_ns = time.perf_counter_ns()
    cases = [
        request_case(
            base_url,
            index,
            task,
            instruction,
            candidate,
            references[task["id"]],
            max_output_tokens,
            seed,
            timeout,
            True,
        )
        for index, task in enumerate(tasks)
    ]
    completed_ns = time.perf_counter_ns()
    cpu_after = read_process_cpu(server_pid)
    elapsed = (completed_ns - started_ns) / 1_000_000_000
    failures = [
        case
        for case in cases
        if case["status"] != 200
        or case["error"] is not None
        or case["predicted"] is None
    ]
    valid = [case for case in cases if case["encode_ms"] is not None]
    cpu = summarize_process_cpu(
        cpu_before,
        cpu_after,
        clock_ticks_per_second=clock_ticks,
        measured_requests=len(tasks),
        elapsed_seconds=elapsed,
    )
    return {
        "schema_version": 1,
        "experiment_id": "E16c",
        "parameters": {
            "base_url": base_url,
            "candidate": candidate,
            "configuration": configuration,
            "repetition": repetition,
            "worker": worker,
            "warmup_task_ids": warmup_task_ids,
            "warmup_slot_ids": [0] * len(warmup_task_ids),
            "measured_tasks": len(tasks),
            "client_concurrency": 1,
            "max_output_tokens": max_output_tokens,
            "instruction_role": "system",
            "chat_template_mode": "model_jinja_system_instruction",
            "temperature": 0.0,
            "seed": seed,
            "timeout_seconds": timeout,
            "prompt_cache": True,
            "server_pid": server_pid,
        },
        "warmups": warmups,
        "cases": cases,
        "result": {
            "correct": sum(case["correct"] for case in cases),
            "total": len(cases),
            "accuracy": sum(case["correct"] for case in cases) / len(cases),
            "failures": len(failures),
            "reference_prediction_mismatches": sum(
                not case["reference_match"] for case in cases
            ),
            "status_counts": {
                str(status): sum(case["status"] == status for case in cases)
                for status in sorted(
                    {case["status"] for case in cases if case["status"] is not None}
                )
            },
            "elapsed_seconds": elapsed,
            "requests_per_second": len(cases) / elapsed,
            "http_ms": summarize([float(case["http_ms"]) for case in cases]),
            "encode_ms": summarize(
                [float(case["encode_ms"]) for case in valid]
            ),
            "decode_ms": summarize(
                [float(case["decode_ms"]) for case in valid]
            ),
            "cached_tokens": summarize(
                [float(case["cached_tokens"]) for case in valid]
            ),
            "evaluated_prompt_tokens": summarize(
                [float(case["evaluated_prompt_tokens"]) for case in valid]
            ),
            "server_process_cpu": cpu,
            "measurement_started_ns": started_ns,
            "measurement_completed_ns": completed_ns,
        },
    }


def run_dual_probe(
    *,
    urls: list[str],
    server_pids: list[int],
    tasks_manifest: dict[str, Any],
    references: dict[str, str],
    candidate: str,
    configuration: str,
    repetition: int,
    warmup_task_ids: list[str],
    max_output_tokens: int,
    seed: int,
    timeout: float,
) -> dict[str, Any]:
    if len(urls) != 2 or len(server_pids) != 2:
        raise ValueError("E16c requires exactly two worker URLs and PIDs")
    barrier = threading.Barrier(3)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                worker_probe,
                worker=index + 1,
                base_url=url,
                server_pid=server_pids[index],
                barrier=barrier,
                tasks_manifest=tasks_manifest,
                references=references,
                candidate=candidate,
                configuration=configuration,
                repetition=repetition,
                warmup_task_ids=warmup_task_ids,
                max_output_tokens=max_output_tokens,
                seed=seed,
                timeout=timeout,
            )
            for index, url in enumerate(urls)
        ]
        barrier.wait(timeout=timeout * 2)
        workers = [future.result() for future in futures]
    starts = [item["result"]["measurement_started_ns"] for item in workers]
    completions = [item["result"]["measurement_completed_ns"] for item in workers]
    elapsed = (max(completions) - min(starts)) / 1_000_000_000
    total_requests = sum(item["result"]["total"] for item in workers)
    total_cpu = sum(
        item["result"]["server_process_cpu"]["total_seconds"] for item in workers
    )
    return {
        "schema_version": 1,
        "experiment_id": "E16c",
        "configuration": configuration,
        "repetition": repetition,
        "workers": workers,
        "group": {
            "workers": 2,
            "measured_requests": total_requests,
            "elapsed_seconds": elapsed,
            "requests_per_second": total_requests / elapsed,
            "server_cpu_seconds": total_cpu,
            "server_cpu_seconds_per_request": total_cpu / total_requests,
            "average_server_cores_used": total_cpu / elapsed,
            "measurement_start_skew_ms": (max(starts) - min(starts)) / 1_000_000,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="append", required=True)
    parser.add_argument("--server-pid", action="append", type=int, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--reference-manifest", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--warmup-task", action="append", default=[])
    parser.add_argument("--max-output-tokens", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tasks = load_object(args.tasks)
    references = load_reference_predictions(
        load_object(args.reference_manifest), args.candidate
    )
    result = run_dual_probe(
        urls=args.url,
        server_pids=args.server_pid,
        tasks_manifest=tasks,
        references=references,
        candidate=args.candidate,
        configuration=args.configuration,
        repetition=args.repetition,
        warmup_task_ids=args.warmup_task,
        max_output_tokens=args.max_output_tokens,
        seed=args.seed,
        timeout=args.timeout,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["group"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
