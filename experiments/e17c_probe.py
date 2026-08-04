#!/usr/bin/env python3
"""Run E17c's deterministic shorter-context retrieval and density workload."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import time

try:
    from experiments.e1_ingest import summarize
    from experiments.e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from experiments.e9c_probe import render_tokens
    from experiments.e17b_probe import request_case, require_timings, solve_prompt
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e9c_probe import render_tokens
    from e17b_probe import request_case, require_timings, solve_prompt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--slots", type=int, required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    task_manifest = json.loads(args.tasks.read_text())
    if contract.get("experiment_id") != "E17c" or args.slots not in {4, 8}:
        raise ValueError("unsupported E17c probe parameters")
    if (
        task_manifest.get("experiment_id") != "E17c"
        or args.configuration not in contract["execution"]["configurations"]
    ):
        raise ValueError("E17c configuration or tasks differ")

    target = task_manifest["target_prompt_tokens"]
    tasks = task_manifest["tasks"]
    prompts = [
        solve_prompt(
            args.url,
            task_manifest["system_instruction"],
            task,
            target["minimum"],
            target["maximum"],
            contract["workload"]["request_timeout_seconds"],
        )
        for task in tasks
    ]
    warmup_prompt = render_tokens(
        args.url,
        task_manifest["system_instruction"],
        "Record 00000: retrieval key WARMUP has authorized access code KITE-314.\n"
        "Question: Which access code belongs to retrieval key WARMUP?\n"
        "A. KITE-314\nB. MOSS-826\nC. RUNE-507\nD. VOLT-193\n"
        "Answer with exactly one uppercase letter.",
        contract["workload"]["request_timeout_seconds"],
    )
    warmup_task = {"id": "warmup", "answer": "A"}
    warmup = {
        "prompt_tokens": warmup_prompt,
        "prompt_token_count": len(warmup_prompt),
        "prompt_sha256": hashlib.sha256(
            json.dumps(warmup_prompt, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    warmups = [
        request_case(
            args.url,
            index=index,
            task=warmup_task,
            prompt=warmup,
            slot_id=index,
            scoring=contract["scoring"],
            timeout=contract["workload"]["request_timeout_seconds"],
        )
        for index in range(args.slots)
    ]
    if any(case["http_status"] != 200 or case["prediction"] != "A" for case in warmups):
        raise ValueError("E17c slot warmup differs")

    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = read_process_cpu(args.server_pid)
    started = time.perf_counter_ns()
    cases = []
    for wave_start in range(0, len(tasks), args.slots):
        indexed_wave = list(
            enumerate(tasks[wave_start : wave_start + args.slots], start=wave_start)
        )
        with ThreadPoolExecutor(max_workers=args.slots) as executor:
            cases.extend(
                executor.map(
                    lambda indexed: request_case(
                        args.url,
                        index=indexed[0],
                        task=indexed[1],
                        prompt=prompts[indexed[0]],
                        slot_id=indexed[0] - wave_start,
                        scoring=contract["scoring"],
                        timeout=contract["workload"]["request_timeout_seconds"],
                    ),
                    indexed_wave,
                )
            )
    elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
    cpu_after = read_process_cpu(args.server_pid)
    require_timings(cases)
    process_cpu = summarize_process_cpu(
        cpu_before,
        cpu_after,
        clock_ticks_per_second=clock_ticks,
        measured_requests=len(cases),
        elapsed_seconds=elapsed,
    )
    failures = [
        case
        for case in cases
        if case["http_status"] != 200
        or case["error"] is not None
        or case["prediction"] is None
    ]
    result = {
        "schema_version": 1,
        "experiment_id": "E17c",
        "configuration": args.configuration,
        "slots": args.slots,
        "repetition": args.repetition,
        "prompt_construction": [
            {key: value for key, value in prompt.items() if key != "prompt_tokens"}
            for prompt in prompts
        ],
        "warmups": warmups,
        "cases": cases,
        "result": {
            "correct": sum(case["correct"] for case in cases),
            "total": len(cases),
            "failures": len(failures),
            "elapsed_seconds": elapsed,
            "requests_per_second": len(cases) / elapsed,
            "http_ms": summarize([float(case["http_ms"]) for case in cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in cases]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in cases]),
            "prompt_tokens": summarize(
                [float(case["prompt_token_count"]) for case in cases]
            ),
            "server_process_cpu": process_cpu,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
