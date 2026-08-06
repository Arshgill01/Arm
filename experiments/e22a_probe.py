#!/usr/bin/env python3
"""Run one N-worker E22a product deployment cell."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.request
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


SMAPS_FIELDS = (
    "Rss",
    "Pss",
    "Pss_Anon",
    "Pss_File",
    "Pss_Shmem",
    "Shared_Clean",
    "Shared_Dirty",
    "Private_Clean",
    "Private_Dirty",
    "Swap",
)


def read_faults(pid: int) -> dict[str, int]:
    fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(") ", 1)[1]
    values = fields.split()
    return {"minor": int(values[7]), "major": int(values[9])}


def read_smaps_rollup(pid: int) -> dict[str, int]:
    observed: dict[str, int] = {}
    for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
        if ":" not in line:
            continue
        name, raw = line.split(":", 1)
        if name in SMAPS_FIELDS:
            parts = raw.split()
            if len(parts) != 2 or parts[1] != "kB":
                raise ValueError(f"unexpected smaps value for {name}")
            observed[name] = int(parts[0])
    if set(observed) != set(SMAPS_FIELDS):
        raise ValueError(f"smaps_rollup fields differ for PID {pid}")
    return {f"{name.lower()}_kib": observed[name] for name in SMAPS_FIELDS}


def worker_probe(
    *,
    worker: dict[str, Any],
    barrier: threading.Barrier,
    tasks_manifest: dict[str, Any],
    references: dict[str, str],
    candidate: str,
    warmup_task_ids: list[str],
    max_output_tokens: int,
    seed: int,
    timeout: float,
) -> dict[str, Any]:
    worker_id = worker["worker"]
    base_url = f"http://{worker['host']}:{worker['port']}"
    server_pid = worker["pid"]
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
    faults_before = read_faults(server_pid)
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
    faults_after = read_faults(server_pid)
    elapsed = (completed_ns - started_ns) / 1_000_000_000
    valid = [case for case in cases if case["encode_ms"] is not None]
    failures = [
        case
        for case in cases
        if case["status"] != 200
        or case["error"] is not None
        or case["predicted"] is None
    ]
    return {
        "worker": worker_id,
        "pid": server_pid,
        "base_url": base_url,
        "warmups": warmups,
        "cases": cases,
        "result": {
            "correct": sum(case["correct"] for case in cases),
            "total": len(cases),
            "failures": len(failures),
            "reference_prediction_mismatches": sum(
                not case["reference_match"] for case in cases
            ),
            "elapsed_seconds": elapsed,
            "requests_per_second": len(cases) / elapsed,
            "http_ms": summarize([float(case["http_ms"]) for case in cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in valid]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in valid]),
            "cached_tokens": summarize(
                [float(case["cached_tokens"]) for case in valid]
            ),
            "server_process_cpu": summarize_process_cpu(
                cpu_before,
                cpu_after,
                clock_ticks_per_second=clock_ticks,
                measured_requests=len(cases),
                elapsed_seconds=elapsed,
            ),
            "page_faults": {
                "minor": faults_after["minor"] - faults_before["minor"],
                "major": faults_after["major"] - faults_before["major"],
            },
            "measurement_started_ns": started_ns,
            "measurement_completed_ns": completed_ns,
        },
    }


def gateway_smoke(
    origin: str,
    task: dict[str, Any],
    instruction: str,
    candidate: str,
    *,
    max_output_tokens: int,
    seed: int,
    timeout: float,
) -> dict[str, Any]:
    payload = {
        "model": candidate,
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": task["prompt"]},
        ],
        "temperature": 0.0,
        "seed": seed,
        "max_tokens": max_output_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = urllib.request.Request(
        f"{origin}/v1/chat/completions",
        data=json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Pareto64-Session-ID": "e22a-gateway-smoke",
        },
    )
    started = time.perf_counter_ns()
    with urllib.request.urlopen(request, timeout=timeout) as opened:
        response = json.loads(opened.read())
        headers = {
            name: opened.headers[name]
            for name in (
                "X-Pareto64-Route",
                "X-Pareto64-Admission",
                "X-Pareto64-Served-Source",
                "X-Pareto64-Worker",
                "X-Pareto64-Transition",
            )
        }
    with urllib.request.urlopen(f"{origin}/metrics", timeout=timeout) as opened:
        metrics = json.loads(opened.read())
    return {
        "http_ms": (time.perf_counter_ns() - started) / 1_000_000,
        "headers": headers,
        "response": response,
        "metrics": metrics,
    }


def run_probe(
    *,
    ready: dict[str, Any],
    tasks_manifest: dict[str, Any],
    references: dict[str, str],
    candidate: str,
    mode: str,
    worker_count: int,
    warmup_task_ids: list[str],
    max_output_tokens: int,
    seed: int,
    timeout: float,
) -> dict[str, Any]:
    workers = ready.get("workers")
    if (
        ready.get("status") != "pareto64_deployment_ready"
        or not isinstance(workers, list)
        or len(workers) != worker_count
    ):
        raise ValueError("E22a deployment readiness differs")
    barrier = threading.Barrier(worker_count + 1)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                worker_probe,
                worker=worker,
                barrier=barrier,
                tasks_manifest=tasks_manifest,
                references=references,
                candidate=candidate,
                warmup_task_ids=warmup_task_ids,
                max_output_tokens=max_output_tokens,
                seed=seed,
                timeout=timeout,
            )
            for worker in workers
        ]
        barrier.wait(timeout=timeout * 2)
        worker_results = [future.result() for future in futures]
    smaps = {
        str(worker["worker"]): read_smaps_rollup(worker["pid"]) for worker in workers
    }
    starts = [item["result"]["measurement_started_ns"] for item in worker_results]
    completions = [
        item["result"]["measurement_completed_ns"] for item in worker_results
    ]
    elapsed = (max(completions) - min(starts)) / 1_000_000_000
    all_cases = [case for worker in worker_results for case in worker["cases"]]
    total_requests = len(all_cases)
    summed_pss = sum(item["pss_kib"] for item in smaps.values())
    summed_rss = sum(item["rss_kib"] for item in smaps.values())
    total_cpu = sum(
        item["result"]["server_process_cpu"]["total_seconds"] for item in worker_results
    )
    gateway = gateway_smoke(
        ready["gateway"]["origin"],
        tasks_manifest["tasks"][0],
        tasks_manifest["instruction"],
        candidate,
        max_output_tokens=max_output_tokens,
        seed=seed,
        timeout=timeout,
    )
    return {
        "schema_version": 1,
        "experiment_id": "E22a-preflight",
        "mode": mode,
        "worker_count": worker_count,
        "deployment_sha256": ready["deployment_sha256"],
        "workers": worker_results,
        "smaps_rollup_kib": smaps,
        "group": {
            "measured_requests": total_requests,
            "request_failures": sum(
                item["result"]["failures"] for item in worker_results
            ),
            "reference_prediction_mismatches": sum(
                item["result"]["reference_prediction_mismatches"]
                for item in worker_results
            ),
            "correct": sum(item["correct"] for item in all_cases),
            "elapsed_seconds": elapsed,
            "requests_per_second": total_requests / elapsed,
            "http_ms": summarize([float(item["http_ms"]) for item in all_cases]),
            "summed_pss_kib": summed_pss,
            "summed_rss_kib": summed_rss,
            "throughput_per_gib_pss": (total_requests / elapsed)
            / (summed_pss / 1024 / 1024),
            "server_cpu_seconds": total_cpu,
            "server_cpu_seconds_per_request": total_cpu / total_requests,
            "average_server_cores_used": total_cpu / elapsed,
            "minor_page_faults": sum(
                item["result"]["page_faults"]["minor"] for item in worker_results
            ),
            "major_page_faults": sum(
                item["result"]["page_faults"]["major"] for item in worker_results
            ),
            "measurement_start_skew_ms": (max(starts) - min(starts)) / 1_000_000,
            "one_worker_ready_seconds": min(item["ready_seconds"] for item in workers),
            "all_workers_ready_seconds": max(item["ready_seconds"] for item in workers),
        },
        "gateway_smoke": gateway,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--reference-manifest", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--mode", choices=("normal", "shared"), required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--warmup-task", action="append", default=[])
    parser.add_argument("--max-output-tokens", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = run_probe(
        ready=load_object(arguments.ready),
        tasks_manifest=load_object(arguments.tasks),
        references=load_reference_predictions(
            load_object(arguments.reference_manifest), arguments.candidate
        ),
        candidate=arguments.candidate,
        mode=arguments.mode,
        worker_count=arguments.workers,
        warmup_task_ids=arguments.warmup_task,
        max_output_tokens=arguments.max_output_tokens,
        seed=arguments.seed,
        timeout=arguments.timeout,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["group"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
