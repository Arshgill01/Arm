#!/usr/bin/env python3
"""Run one frozen E10c fixed-candidate scoring cell."""

from __future__ import annotations

import argparse
import gzip
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
    from experiments.e9c_probe import load_object, render_tokens
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e9c_probe import load_object, render_tokens


def post_raw_json(
    origin: str, path: str, payload: dict[str, Any], timeout: float
) -> tuple[int, bytes, dict[str, Any], float]:
    parsed = urlsplit(origin)
    connection = http.client.HTTPConnection(
        parsed.hostname, parsed.port, timeout=timeout
    )
    body = json.dumps(payload, separators=(",", ":")).encode()
    started = time.perf_counter_ns()
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read()
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError(f"{path} returned a non-object")
        return response.status, raw, value, elapsed_ms
    finally:
        connection.close()


def retain_raw(path: Path, raw: bytes) -> dict[str, Any]:
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(compressed)
    return {
        "path": path.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "gzip_bytes": len(compressed),
        "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
    }


def prompt_sha256(tokens: list[int]) -> str:
    return hashlib.sha256(
        json.dumps(tokens, separators=(",", ":")).encode()
    ).hexdigest()


def selected_logprob(response: dict[str, Any], token: int) -> float:
    probabilities = response.get("completion_probabilities")
    if not isinstance(probabilities, list) or len(probabilities) != 1:
        raise ValueError("completion response lacks one probability entry")
    entry = probabilities[0]
    selected = entry.get("selected_logprobs") if isinstance(entry, dict) else None
    if not isinstance(selected, list) or len(selected) != 1:
        raise ValueError("completion response lacks one selected log probability")
    item = selected[0]
    logprob = item.get("logprob") if isinstance(item, dict) else None
    if (
        not isinstance(item, dict)
        or item.get("id") != token
        or not isinstance(logprob, (int, float))
        or not math.isfinite(logprob)
    ):
        raise ValueError("selected log probability differs from the forced token")
    return float(logprob)


def serial_scores(
    origin: str,
    *,
    prompt_tokens: list[int],
    candidates: list[list[int]],
    seed: int,
    timeout: float,
    raw_dir: Path | None,
    raw_prefix: str,
) -> dict[str, Any]:
    scores: list[float] = []
    token_scores: list[list[float]] = []
    records: list[dict[str, Any]] = []
    prompt_ms = 0.0
    predicted_ms = 0.0
    response_bytes = 0
    request_ms = 0.0
    cached_tokens: list[int] = []

    for candidate_index, candidate in enumerate(candidates):
        prefix = list(prompt_tokens)
        candidate_scores: list[float] = []
        for token_index, token in enumerate(candidate):
            status, raw, response, http_ms = post_raw_json(
                origin,
                "/completion",
                {
                    "prompt": prefix,
                    "n_predict": 1,
                    "temperature": 0.0,
                    "seed": seed,
                    "cache_prompt": False,
                    "stream": False,
                    "return_tokens": False,
                    "n_probs": 0,
                    "probability_ids": [token],
                    "post_sampling_probs": False,
                },
                timeout,
            )
            if status != 200:
                raise ValueError(f"serial /completion returned HTTP {status}")
            candidate_scores.append(selected_logprob(response, token))
            timings = response.get("timings")
            if not isinstance(timings, dict):
                raise TypeError("serial response lacks timings")
            prompt_ms += float(timings["prompt_ms"])
            predicted_ms += float(timings["predicted_ms"])
            cached_tokens.append(int(timings["cache_n"]))
            response_bytes += len(raw)
            request_ms += http_ms
            if raw_dir is not None:
                records.append(
                    retain_raw(
                        raw_dir
                        / f"{raw_prefix}-c{candidate_index}-t{token_index}.json.gz",
                        raw,
                    )
                )
            prefix.append(token)
        token_scores.append(candidate_scores)
        scores.append(sum(candidate_scores))

    return {
        "candidate_sum_logprobs": scores,
        "candidate_token_logprobs": token_scores,
        "http_ms": request_ms,
        "prompt_ms": prompt_ms,
        "predicted_ms": predicted_ms,
        "response_bytes": response_bytes,
        "inference_requests": sum(len(candidate) for candidate in candidates),
        "prompt_evaluations": sum(len(candidate) for candidate in candidates),
        "cached_tokens": cached_tokens,
        "raw_responses": records,
    }


def forked_scores(
    origin: str,
    *,
    prompt_tokens: list[int],
    candidates: list[list[int]],
    timeout: float,
    raw_dir: Path | None,
    raw_prefix: str,
) -> dict[str, Any]:
    status, raw, response, http_ms = post_raw_json(
        origin,
        "/score",
        {
            "prompt": prompt_tokens,
            "candidates": candidates,
            "cache_prompt": False,
        },
        timeout,
    )
    if status != 200:
        raise ValueError(f"forked /score returned HTTP {status}")
    if (
        response.get("object") != "candidate_scores"
        or response.get("score_semantics") != "raw_pre_sampling_logprob"
        or response.get("shared_prompt") is not True
    ):
        raise ValueError("forked response differs from the scorer contract")
    values = response.get("candidates")
    if not isinstance(values, list) or len(values) != len(candidates):
        raise ValueError("forked response candidate count differs")

    scores: list[float] = []
    token_scores: list[list[float]] = []
    contents: list[str] = []
    prompt_ms: list[float] = []
    predicted_ms: list[float] = []
    cached_tokens: list[int] = []
    for index, (item, candidate) in enumerate(zip(values, candidates)):
        if not isinstance(item, dict) or item.get("index") != index:
            raise ValueError("forked candidate order differs")
        if item.get("tokens") != candidate or not isinstance(item.get("content"), str):
            raise ValueError("forked candidate tokens or content differ")
        per_token = item.get("token_logprobs")
        if not isinstance(per_token, list) or len(per_token) != len(candidate):
            raise ValueError("forked per-token score count differs")
        current: list[float] = []
        for token_item, token in zip(per_token, candidate):
            logprob = (
                token_item.get("logprob") if isinstance(token_item, dict) else None
            )
            if (
                not isinstance(token_item, dict)
                or token_item.get("id") != token
                or not isinstance(logprob, (int, float))
                or not math.isfinite(logprob)
            ):
                raise ValueError("forked per-token score is invalid")
            current.append(float(logprob))
        score = item.get("sum_logprob")
        if (
            not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not math.isclose(float(score), sum(current), abs_tol=1e-12)
        ):
            raise ValueError("forked candidate sum differs from token scores")
        timings = item.get("timings")
        if not isinstance(timings, dict):
            raise TypeError("forked candidate lacks timings")
        scores.append(float(score))
        token_scores.append(current)
        contents.append(item["content"])
        prompt_ms.append(float(timings["prompt_ms"]))
        predicted_ms.append(float(timings["predicted_ms"]))
        cached_tokens.append(int(timings["cache_n"]))

    selected = response.get("selected_index")
    expected_selected = max(
        range(len(scores)), key=lambda index: (scores[index], -index)
    )
    if selected != expected_selected:
        raise ValueError("forked selected index differs from summed scores")
    records = []
    if raw_dir is not None:
        records.append(retain_raw(raw_dir / f"{raw_prefix}.json.gz", raw))
    return {
        "candidate_sum_logprobs": scores,
        "candidate_token_logprobs": token_scores,
        "candidate_contents": contents,
        "selected_index": selected,
        "http_ms": http_ms,
        "request_ms": response.get("request_ms"),
        "prompt_ms": max(prompt_ms),
        "predicted_ms": max(predicted_ms),
        "response_bytes": len(raw),
        "inference_requests": 1,
        "prompt_evaluations": 1,
        "cached_tokens": [int(response["prompt_tokens_cached"])],
        "candidate_cached_tokens": cached_tokens,
        "raw_responses": records,
    }


def prediction(scores: list[float], labels: list[str]) -> tuple[int, str]:
    index = max(range(len(scores)), key=lambda item: (scores[item], -item))
    return index, labels[index]


def summarize_or_none(values: list[float]) -> dict[str, float] | None:
    return summarize(values) if values else None


def run_case(
    mode: str,
    origin: str,
    *,
    index: int,
    task: dict[str, Any],
    prompt_tokens: list[int],
    candidate_tokens: list[list[int]],
    candidate_labels: list[str],
    seed: int,
    timeout: float,
    raw_dir: Path,
) -> dict[str, Any]:
    try:
        if mode == "serial":
            measured = serial_scores(
                origin,
                prompt_tokens=prompt_tokens,
                candidates=candidate_tokens,
                seed=seed,
                timeout=timeout,
                raw_dir=raw_dir,
                raw_prefix=f"{index:02d}-{task['id']}",
            )
        elif mode == "forked":
            measured = forked_scores(
                origin,
                prompt_tokens=prompt_tokens,
                candidates=candidate_tokens,
                timeout=timeout,
                raw_dir=raw_dir,
                raw_prefix=f"{index:02d}-{task['id']}",
            )
        else:
            raise ValueError(f"unsupported mode {mode}")
        selected_index, selected = prediction(
            measured["candidate_sum_logprobs"], candidate_labels
        )
        return {
            "index": index,
            "task_id": task["id"],
            "category": task["category"],
            "expected": task["answer"],
            "prediction": selected,
            "selected_index": selected_index,
            "correct": selected == task["answer"],
            "prompt_tokens": len(prompt_tokens),
            "prompt_sha256": prompt_sha256(prompt_tokens),
            **measured,
            "error": None,
        }
    except (KeyError, OSError, TypeError, ValueError) as error:
        return {
            "index": index,
            "task_id": task.get("id"),
            "category": task.get("category"),
            "expected": task.get("answer"),
            "prediction": None,
            "selected_index": None,
            "correct": False,
            "prompt_tokens": len(prompt_tokens),
            "prompt_sha256": prompt_sha256(prompt_tokens),
            "error": f"{type(error).__name__}: {error}",
        }


def calibration(
    origin: str,
    *,
    prompt_tokens: list[int],
    candidates: list[list[int]],
    seed: int,
    timeout: float,
    raw_dir: Path,
) -> dict[str, Any]:
    try:
        serial = serial_scores(
            origin,
            prompt_tokens=prompt_tokens,
            candidates=candidates,
            seed=seed,
            timeout=timeout,
            raw_dir=raw_dir,
            raw_prefix="calibration-serial",
        )
        forked = forked_scores(
            origin,
            prompt_tokens=prompt_tokens,
            candidates=candidates,
            timeout=timeout,
            raw_dir=raw_dir,
            raw_prefix="calibration-forked",
        )
        deltas = [
            abs(serial_score - forked_score)
            for serial_score, forked_score in zip(
                serial["candidate_sum_logprobs"],
                forked["candidate_sum_logprobs"],
            )
        ]
        token_deltas = [
            abs(serial_token - forked_token)
            for serial_candidate, forked_candidate in zip(
                serial["candidate_token_logprobs"],
                forked["candidate_token_logprobs"],
            )
            for serial_token, forked_token in zip(serial_candidate, forked_candidate)
        ]
        return {
            "candidate_tokens": candidates,
            "serial_sum_logprobs": serial["candidate_sum_logprobs"],
            "forked_sum_logprobs": forked["candidate_sum_logprobs"],
            "maximum_absolute_sum_logprob_delta": max(deltas),
            "maximum_absolute_token_logprob_delta": max(token_deltas),
            "serial_raw_responses": serial["raw_responses"],
            "forked_raw_responses": forked["raw_responses"],
            "error": None,
        }
    except (KeyError, OSError, TypeError, ValueError) as error:
        return {"error": f"{type(error).__name__}: {error}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--mode", choices=("serial", "forked"), required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_object(args.contract)
    if contract.get("experiment_id") != "E10c":
        raise ValueError("unsupported contract")
    if {"mode": args.mode, "repetition": args.repetition} not in contract["execution"][
        "cell_order"
    ]:
        raise ValueError("cell differs from the frozen order")
    tasks = load_object(args.tasks)
    if tasks.get("schema_version") != 1 or not isinstance(tasks.get("tasks"), list):
        raise ValueError("invalid task manifest")
    instruction = tasks.get("instruction")
    if not isinstance(instruction, str) or not instruction:
        raise ValueError("task manifest lacks an instruction")
    if len(tasks["tasks"]) != contract["workload"]["task_count"]:
        raise ValueError("task count differs from the frozen workload")

    workload = contract["workload"]
    candidate_labels = workload["candidate_labels"]
    candidate_ids = workload["candidate_token_ids"]
    candidate_tokens = [[token] for token in candidate_ids]
    timeout = float(workload["timeout_seconds"])
    prompts = [
        render_tokens(args.url, instruction, task["prompt"], timeout)
        for task in tasks["tasks"]
    ]
    prompt_records = [
        {
            "task_id": task["id"],
            "tokens": len(tokens),
            "sha256": prompt_sha256(tokens),
        }
        for task, tokens in zip(tasks["tasks"], prompts)
    ]

    multi = calibration(
        args.url,
        prompt_tokens=prompts[0],
        candidates=workload["multi_token_calibration_candidates"],
        seed=workload["seed"],
        timeout=timeout,
        raw_dir=args.raw_dir,
    )

    if args.mode == "serial":
        serial_scores(
            args.url,
            prompt_tokens=prompts[0],
            candidates=candidate_tokens,
            seed=workload["seed"],
            timeout=timeout,
            raw_dir=None,
            raw_prefix="warmup",
        )
    else:
        forked_scores(
            args.url,
            prompt_tokens=prompts[0],
            candidates=candidate_tokens,
            timeout=timeout,
            raw_dir=None,
            raw_prefix="warmup",
        )

    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = read_process_cpu(args.server_pid)
    started = time.perf_counter_ns()
    cases = [
        run_case(
            args.mode,
            args.url,
            index=index,
            task=task,
            prompt_tokens=prompt_tokens,
            candidate_tokens=candidate_tokens,
            candidate_labels=candidate_labels,
            seed=workload["seed"],
            timeout=timeout,
            raw_dir=args.raw_dir,
        )
        for index, (task, prompt_tokens) in enumerate(
            zip(tasks["tasks"], prompts), start=1
        )
    ]
    elapsed_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
    cpu_after = read_process_cpu(args.server_pid)
    process_cpu = summarize_process_cpu(
        before=cpu_before,
        after=cpu_after,
        clock_ticks_per_second=clock_ticks,
        measured_requests=len(cases),
        elapsed_seconds=elapsed_seconds,
    )

    failures = sum(case["error"] is not None for case in cases)
    correct = sum(case["correct"] for case in cases)
    valid = [case for case in cases if case["error"] is None]
    result = {
        "failures": failures,
        "correct": correct,
        "total": len(cases),
        "accuracy": correct / len(cases),
        "elapsed_seconds": elapsed_seconds,
        "tasks_per_second": len(cases) / elapsed_seconds,
        "http_ms": summarize_or_none([float(case["http_ms"]) for case in valid]),
        "prompt_ms": summarize_or_none([float(case["prompt_ms"]) for case in valid]),
        "predicted_ms": summarize_or_none(
            [float(case["predicted_ms"]) for case in valid]
        ),
        "response_bytes": summarize_or_none(
            [float(case["response_bytes"]) for case in valid]
        ),
        "inference_requests": sum(int(case["inference_requests"]) for case in valid),
        "prompt_evaluations": sum(int(case["prompt_evaluations"]) for case in valid),
    }
    output = {
        "schema_version": 1,
        "experiment_id": "E10c",
        "parameters": {
            "mode": args.mode,
            "repetition": args.repetition,
            "server_pid": args.server_pid,
            "task_count": len(cases),
            "candidate_labels": candidate_labels,
            "candidate_token_ids": candidate_ids,
            "cache_prompt": False,
            "seed": workload["seed"],
        },
        "prompt_records": prompt_records,
        "multi_token_calibration": multi,
        "cases": cases,
        "process_cpu": process_cpu,
        "result": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"mode": args.mode, "repetition": args.repetition, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
