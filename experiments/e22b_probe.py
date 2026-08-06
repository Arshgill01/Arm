#!/usr/bin/env python3
"""Run one stable-host E22b worker group with bounded PMU evidence."""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
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
    )
    from experiments.e22a_freeze import sha256_file
    from experiments.e22a_probe import (
        gateway_smoke,
        read_smaps_rollup,
        worker_probe,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import load_object, load_reference_predictions
    from e22a_freeze import sha256_file
    from e22a_probe import gateway_smoke, read_smaps_rollup, worker_probe


PERF_EVENTS = (
    "cpu_cycles",
    "inst_retired",
    "l1d_cache",
    "l1d_cache_refill",
    "l2d_cache",
)
MEMINFO_FIELDS = ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")
VMSTAT_FIELDS = ("pgfault", "pgmajfault", "oom_kill")


def read_meminfo() -> dict[str, int]:
    observed: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        name, separator, remainder = line.partition(":")
        if separator and name in MEMINFO_FIELDS:
            value, unit = remainder.split()
            if unit != "kB":
                raise ValueError(f"unexpected meminfo unit for {name}")
            observed[f"{name.lower()}_bytes"] = int(value) * 1024
    if set(observed) != {f"{name.lower()}_bytes" for name in MEMINFO_FIELDS}:
        raise ValueError("required meminfo fields differ")
    return observed


def read_vmstat() -> dict[str, int]:
    observed = {}
    for line in Path("/proc/vmstat").read_text(encoding="utf-8").splitlines():
        name, raw = line.split()
        if name in VMSTAT_FIELDS:
            observed[name] = int(raw)
    if set(observed) != set(VMSTAT_FIELDS):
        raise ValueError("required vmstat fields differ")
    return observed


def start_perf(pids: list[int], output: Path) -> subprocess.Popen[str]:
    command = ["perf", "stat", "--no-big-num", "-x,", "--output", str(output)]
    for event in PERF_EVENTS:
        command.extend(("-e", event))
    command.extend(("--pid", ",".join(str(pid) for pid in pids)))
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.2)
    if process.poll() is not None:
        raise RuntimeError(f"perf exited before measurement: {process.stderr.read()}")
    return process


def stop_perf(process: subprocess.Popen[str]) -> dict[str, Any]:
    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=30)
    if process.returncode not in (0, -signal.SIGINT, 130):
        raise RuntimeError(f"perf stat failed ({process.returncode}): {stderr}")
    return {"returncode": process.returncode, "stderr": stderr}


def parse_perf(path: Path) -> dict[str, float | int]:
    observed: dict[str, float | int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split(",")
        if len(fields) < 3:
            continue
        raw_value = fields[0].strip()
        event = fields[2].strip()
        if event not in PERF_EVENTS:
            continue
        if raw_value.startswith("<"):
            raise ValueError(f"PMU event was not counted: {event}")
        numeric = float(raw_value)
        observed[event] = int(numeric) if numeric.is_integer() else numeric
    if set(observed) != set(PERF_EVENTS) or any(
        value <= 0 for value in observed.values()
    ):
        raise ValueError("E22b PMU event set differs")
    return observed


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
    perf_output: Path,
) -> dict[str, Any]:
    workers = ready.get("workers")
    if (
        ready.get("status") != "pareto64_deployment_ready"
        or not isinstance(workers, list)
        or len(workers) != worker_count
    ):
        raise ValueError("E22b deployment readiness differs")
    barrier = threading.Barrier(worker_count + 1)
    perf_process: subprocess.Popen[str] | None = None
    perf_lifecycle: dict[str, Any] | None = None
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
        deadline = time.monotonic() + timeout * 2
        while barrier.n_waiting != worker_count:
            for future in futures:
                if future.done() and future.exception() is not None:
                    raise future.exception()  # type: ignore[misc]
            if time.monotonic() >= deadline:
                raise TimeoutError("E22b workers did not finish warmup")
            time.sleep(0.01)
        memory_before = read_meminfo()
        vmstat_before = read_vmstat()
        perf_process = start_perf([worker["pid"] for worker in workers], perf_output)
        try:
            barrier.wait(timeout=timeout * 2)
            worker_results = [future.result() for future in futures]
        finally:
            if perf_process.poll() is None:
                perf_lifecycle = stop_perf(perf_process)
    if perf_lifecycle is None:
        raise RuntimeError("E22b perf lifecycle is incomplete")
    memory_after = read_meminfo()
    vmstat_after = read_vmstat()
    pmu_events = parse_perf(perf_output)

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
        "experiment_id": "E22b-fixed-memory-curve",
        "mode": mode,
        "worker_count": worker_count,
        "deployment_sha256": ready["deployment_sha256"],
        "workers": worker_results,
        "smaps_rollup_kib": smaps,
        "memory_before_measurement": memory_before,
        "memory_after_measurement": memory_after,
        "vmstat_delta": {
            name: vmstat_after[name] - vmstat_before[name] for name in VMSTAT_FIELDS
        },
        "pmu": {
            "events": pmu_events,
            "raw_sha256": sha256_file(perf_output),
            "returncode": perf_lifecycle["returncode"],
            "stderr": perf_lifecycle["stderr"],
            "measurement_scope": "worker processes during the exact measured trace",
        },
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
            "requests_per_second_per_worker": total_requests / elapsed / worker_count,
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
    parser.add_argument("--perf-output", type=Path, required=True)
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
        perf_output=arguments.perf_output,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["group"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
