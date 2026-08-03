#!/usr/bin/env python3
"""Run E17b's deterministic long-context retrieval and density workload."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import time
from typing import Any

try:
    from experiments.e1_ingest import summarize
    from experiments.e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from experiments.e9c_probe import post_json, render_tokens
    from experiments.e10a_probe import extract_candidate_distribution, ranked_candidates
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e9c_probe import post_json, render_tokens
    from e10a_probe import extract_candidate_distribution, ranked_candidates


LETTERS = ("A", "B", "C", "D")


def distractor_line(seed: int, index: int) -> str:
    digest = hashlib.sha256(f"{seed}:{index}".encode()).hexdigest().upper()
    counter = int(digest[24:32], 16) % 1_000_000
    return (
        f"Record {index:05d}: locator {digest[:8]} reports code {digest[8:16]} "
        f"with counter {counter:06d} and witness {digest[16:24]}."
    )


def task_user_text(task: dict[str, Any], record_count: int) -> str:
    if record_count < 2:
        raise ValueError("record count must be at least two")
    fraction = float(task["needle_fraction"])
    if not 0 < fraction < 1:
        raise ValueError("needle fraction must be inside the ledger")
    needle_index = round((record_count - 1) * fraction)
    answer_index = LETTERS.index(task["answer"])
    lines = []
    for index in range(record_count):
        if index == needle_index:
            lines.append(
                f"Record {index:05d}: retrieval key {task['retrieval_key']} has "
                f"authorized access code {task['options'][answer_index]}."
            )
        else:
            lines.append(distractor_line(int(task["seed"]), index))
    choices = "\n".join(
        f"{letter}. {value}" for letter, value in zip(LETTERS, task["options"], strict=True)
    )
    lines.extend(
        [
            "",
            f"Question: Which access code belongs to retrieval key {task['retrieval_key']}?",
            choices,
            "Answer with exactly one uppercase letter.",
        ]
    )
    return "\n".join(lines)


def solve_prompt(
    origin: str,
    system: str,
    task: dict[str, Any],
    minimum_tokens: int,
    maximum_tokens: int,
    timeout: float,
) -> dict[str, Any]:
    if minimum_tokens <= 0 or maximum_tokens < minimum_tokens:
        raise ValueError("invalid target prompt-token interval")

    cache: dict[int, tuple[list[int], str]] = {}

    def evaluate(count: int) -> tuple[list[int], str]:
        if count not in cache:
            text = task_user_text(task, count)
            cache[count] = (render_tokens(origin, system, text, timeout), text)
        return cache[count]

    low = 2
    high = 2048
    if len(evaluate(high)[0]) < minimum_tokens:
        raise ValueError("long-context ledger generator cannot reach the target")
    while low < high:
        middle = (low + high) // 2
        if len(evaluate(middle)[0]) < minimum_tokens:
            low = middle + 1
        else:
            high = middle

    candidates = range(max(2, low - 8), min(2048, low + 8) + 1)
    solved = [
        (count, *evaluate(count))
        for count in candidates
        if minimum_tokens <= len(evaluate(count)[0]) <= maximum_tokens
    ]
    if not solved:
        raise ValueError("no deterministic ledger falls inside the prompt-token interval")
    record_count, tokens, text = min(solved, key=lambda item: (len(item[1]), item[0]))
    needle_index = round((record_count - 1) * float(task["needle_fraction"]))
    return {
        "task_id": task["id"],
        "record_count": record_count,
        "needle_index": needle_index,
        "needle_fraction": task["needle_fraction"],
        "prompt_tokens": tokens,
        "prompt_token_count": len(tokens),
        "prompt_sha256": hashlib.sha256(
            json.dumps(tokens, separators=(",", ":")).encode()
        ).hexdigest(),
        "user_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def request_case(
    origin: str,
    *,
    index: int,
    task: dict[str, Any],
    prompt: dict[str, Any],
    slot_id: int,
    scoring: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    started = time.perf_counter_ns()
    response: dict[str, Any] | None = None
    try:
        status, response = post_json(
            origin,
            "/completion",
            {
                "prompt": prompt["prompt_tokens"],
                "id_slot": slot_id,
                "n_predict": scoring["maximum_output_tokens"],
                "temperature": scoring["temperature"],
                "samplers": scoring["samplers"],
                "seed": scoring["seed"],
                "grammar": scoring["grammar"],
                "n_probs": scoring["n_probs"],
                "post_sampling_probs": True,
                "return_tokens": True,
                "cache_prompt": False,
                "stream": False,
            },
            timeout,
        )
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        if status != 200:
            raise ValueError(f"/completion returned HTTP {status}")
        distribution, candidate_mass, discarded = extract_candidate_distribution(response)
        ranking = ranked_candidates(distribution)
        timings = response.get("timings")
        timings = timings if isinstance(timings, dict) else {}
        sampled = response.get("content")
        sampled_prediction = sampled.strip().upper() if isinstance(sampled, str) else None
        if sampled_prediction not in LETTERS:
            sampled_prediction = None
        prediction = ranking[0]["candidate"]
        return {
            "index": index,
            "task_id": task["id"],
            "slot_id": slot_id,
            "expected": task["answer"],
            "prediction": prediction,
            "correct": prediction == task["answer"],
            "sampled_response": sampled,
            "sampled_prediction": sampled_prediction,
            "http_status": status,
            "prompt_token_count": prompt["prompt_token_count"],
            "prompt_sha256": prompt["prompt_sha256"],
            "candidate_probabilities": distribution,
            "candidate_ranking": ranking,
            "top1_margin": ranking[0]["probability"] - ranking[1]["probability"],
            "raw_candidate_probability_mass": candidate_mass,
            "discarded_top_probability_entries": discarded,
            "generated_tokens": timings.get("predicted_n"),
            "cached_tokens": timings.get("cache_n"),
            "evaluated_prompt_tokens": timings.get("prompt_n"),
            "response_tokens_cached": response.get("tokens_cached"),
            "response_tokens_evaluated": response.get("tokens_evaluated"),
            "encode_ms": timings.get("prompt_ms"),
            "decode_ms": timings.get("predicted_ms"),
            "http_ms": elapsed_ms,
            "error": None,
        }
    except Exception as error:
        return {
            "index": index,
            "task_id": task["id"],
            "slot_id": slot_id,
            "expected": task["answer"],
            "prediction": None,
            "correct": False,
            "sampled_response": None,
            "sampled_prediction": None,
            "http_status": None,
            "prompt_token_count": prompt["prompt_token_count"],
            "prompt_sha256": prompt["prompt_sha256"],
            "candidate_probabilities": None,
            "candidate_ranking": None,
            "top1_margin": None,
            "raw_candidate_probability_mass": None,
            "discarded_top_probability_entries": None,
            "generated_tokens": None,
            "cached_tokens": None,
            "evaluated_prompt_tokens": None,
            "response_tokens_cached": None,
            "response_tokens_evaluated": None,
            "encode_ms": None,
            "decode_ms": None,
            "http_ms": (time.perf_counter_ns() - started) / 1_000_000,
            "error": f"{type(error).__name__}: {error}",
            "raw_response": response,
        }


def require_timings(cases: list[dict[str, Any]]) -> None:
    for case in cases:
        for name in (
            "http_ms",
            "encode_ms",
            "decode_ms",
            "cached_tokens",
            "evaluated_prompt_tokens",
            "response_tokens_cached",
            "response_tokens_evaluated",
            "top1_margin",
        ):
            value = case.get(name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid E17b {name}")


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
    if contract.get("experiment_id") != "E17b" or args.slots not in {4, 8}:
        raise ValueError("unsupported E17b probe parameters")
    if args.configuration not in contract["execution"]["configurations"]:
        raise ValueError("E17b configuration differs")

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
        raise ValueError("E17b slot warmup differs")

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
        if case["http_status"] != 200 or case["error"] is not None or case["prediction"] is None
    ]
    result = {
        "schema_version": 1,
        "experiment_id": "E17b",
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
