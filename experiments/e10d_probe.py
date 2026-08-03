#!/usr/bin/env python3
"""Score one model on the frozen E10d external holdout."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import summarize
    from experiments.e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from experiments.e9c_probe import load_object
    from experiments.e10c_probe import post_raw_json, retain_raw, selected_logprob
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e9c_probe import load_object
    from e10c_probe import post_raw_json, retain_raw, selected_logprob


def argmax(values: list[float]) -> int:
    return max(range(len(values)), key=lambda index: (values[index], -index))


def score_candidate(
    *,
    base_url: str,
    prompt_tokens: list[int],
    candidate_tokens: list[int],
    seed: int,
    timeout: float,
    raw_dir: Path,
    raw_prefix: str,
) -> dict[str, Any]:
    prefix = list(prompt_tokens)
    token_logprobs: list[float] = []
    sampled_tokens: list[int] = []
    cached_tokens: list[int] = []
    http_ms = 0.0
    prompt_ms = 0.0
    predicted_ms = 0.0
    response_bytes = 0
    raw_responses: list[dict[str, Any]] = []
    greedy = True

    for token_index, token in enumerate(candidate_tokens):
        cache_prompt = token_index > 0
        status, raw, response, elapsed_ms = post_raw_json(
            base_url,
            "/completion",
            {
                "prompt": prefix,
                "n_predict": 1,
                "temperature": 0.0,
                "seed": seed,
                "cache_prompt": cache_prompt,
                "stream": False,
                "return_tokens": True,
                "n_probs": 0,
                "probability_ids": [token],
                "post_sampling_probs": False,
            },
            timeout,
        )
        if status != 200:
            raise ValueError(f"serial /completion returned HTTP {status}")
        token_logprobs.append(selected_logprob(response, token))
        timings = response.get("timings")
        generated = response.get("tokens")
        if (
            not isinstance(timings, dict)
            or not isinstance(generated, list)
            or len(generated) != 1
            or not isinstance(generated[0], int)
        ):
            raise TypeError("serial completion response is incomplete")
        cache_n = int(timings["cache_n"])
        if (token_index == 0 and cache_n != 0) or (
            token_index > 0 and not 0 < cache_n <= len(prefix)
        ):
            raise ValueError("serial continuation cache policy was not observed")
        sampled_tokens.append(generated[0])
        greedy &= generated[0] == token
        cached_tokens.append(cache_n)
        http_ms += elapsed_ms
        prompt_ms += float(timings["prompt_ms"])
        predicted_ms += float(timings["predicted_ms"])
        response_bytes += len(raw)
        raw_responses.append(
            retain_raw(raw_dir / f"{raw_prefix}-t{token_index:03d}.json.gz", raw)
        )
        prefix.append(token)

    return {
        "sum_logprob": sum(token_logprobs),
        "token_logprobs": token_logprobs,
        "is_greedy": greedy,
        "sampled_tokens": sampled_tokens,
        "cached_tokens": cached_tokens,
        "http_ms": http_ms,
        "prompt_ms": prompt_ms,
        "predicted_ms": predicted_ms,
        "response_bytes": response_bytes,
        "token_score_requests": len(candidate_tokens),
        "raw_responses": raw_responses,
    }


def score_sample(
    *,
    base_url: str,
    task_name: str,
    sample: dict[str, Any],
    seed: int,
    timeout: float,
    raw_dir: Path,
) -> dict[str, Any]:
    choice_count = len(sample["choice_text_lengths"])
    choices: list[dict[str, Any]] = []
    try:
        for request in sample["requests"]:
            choice_index = request["choice_index"]
            measured = score_candidate(
                base_url=base_url,
                prompt_tokens=request["prompt_tokens"],
                candidate_tokens=request["candidate_tokens"],
                seed=seed,
                timeout=timeout,
                raw_dir=raw_dir,
                raw_prefix=(
                    f"{task_name}-{sample['sample_ordinal']:03d}-c{choice_index:02d}"
                ),
            )
            choices.append(
                {
                    "choice_index": choice_index,
                    "prompt_sha256": request["prompt_sha256"],
                    "candidate_sha256": request["candidate_sha256"],
                    **measured,
                }
            )
        if [choice["choice_index"] for choice in choices] != list(range(choice_count)):
            raise ValueError("holdout choices were not scored in frozen order")

        scores = [float(choice["sum_logprob"]) for choice in choices]
        normalized = [
            score / length
            for score, length in zip(scores, sample["choice_text_lengths"])
        ]
        predicted = argmax(scores)
        predicted_norm = argmax(normalized)
        gold = sample["gold_index"]
        return {
            "sample_ordinal": sample["sample_ordinal"],
            "source_index": sample["source_index"],
            "source_document_sha256": sample["source_document_sha256"],
            "gold_index": gold,
            "prediction": predicted,
            "prediction_norm": predicted_norm,
            "acc": int(predicted == gold),
            "acc_norm": int(predicted_norm == gold),
            "choice_sum_logprobs": scores,
            "choice_normalized_logprobs": normalized,
            "choice_text_lengths": sample["choice_text_lengths"],
            "choices": choices,
            "error": None,
        }
    except (KeyError, OSError, TypeError, ValueError) as error:
        return {
            "sample_ordinal": sample.get("sample_ordinal"),
            "source_index": sample.get("source_index"),
            "source_document_sha256": sample.get("source_document_sha256"),
            "gold_index": sample.get("gold_index"),
            "prediction": None,
            "prediction_norm": None,
            "acc": 0,
            "acc_norm": 0,
            "choice_sum_logprobs": [],
            "choice_text_lengths": sample.get("choice_text_lengths"),
            "choices": choices,
            "error": f"{type(error).__name__}: {error}",
        }


def summarize_task(
    task: dict[str, Any], samples: list[dict[str, Any]]
) -> dict[str, Any]:
    valid = [sample for sample in samples if sample["error"] is None]
    metrics: dict[str, float | None] = {}
    for metric in task["metrics"]:
        if metric not in {"acc", "acc_norm"}:
            raise ValueError(f"unsupported holdout metric {metric}")
        metrics[metric] = (
            sum(float(sample[metric]) for sample in valid) / len(valid)
            if valid
            else None
        )
    choices = [choice for sample in valid for choice in sample["choices"]]
    return {
        "sample_count": len(samples),
        "valid_samples": len(valid),
        "failures": len(samples) - len(valid),
        "metrics": metrics,
        "candidate_requests": len(choices),
        "token_score_requests": sum(
            int(choice["token_score_requests"]) for choice in choices
        ),
        "http_ms_per_candidate": summarize(
            [float(choice["http_ms"]) for choice in choices]
        )
        if choices
        else None,
        "response_bytes_per_candidate": summarize(
            [float(choice["response_bytes"]) for choice in choices]
        )
        if choices
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    prepared = load_object(args.prepared)
    if (
        prepared.get("schema_version") != 1
        or prepared.get("experiment_id") != "E10d"
        or prepared.get("tokenizer_parity_checked") is not True
        or prepared.get("summary", {}).get("samples") != 300
        or prepared.get("summary", {}).get("choices") != 1000
        or args.seed != prepared.get("seed")
    ):
        raise ValueError("prepared workload differs from E10d")

    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = read_process_cpu(args.server_pid)
    started = time.perf_counter_ns()
    tasks: list[dict[str, Any]] = []
    for task in prepared["tasks"]:
        samples = [
            score_sample(
                base_url=args.base_url,
                task_name=task["task"],
                sample=sample,
                seed=args.seed,
                timeout=args.timeout,
                raw_dir=args.raw_dir,
            )
            for sample in task["samples"]
        ]
        tasks.append(
            {
                "task": task["task"],
                "metrics": task["metrics"],
                "samples": samples,
                "result": summarize_task(task, samples),
            }
        )
    elapsed_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
    cpu_after = read_process_cpu(args.server_pid)
    candidate_requests = sum(
        int(task["result"]["candidate_requests"]) for task in tasks
    )
    token_score_requests = sum(
        int(task["result"]["token_score_requests"]) for task in tasks
    )
    process_cpu = summarize_process_cpu(
        before=cpu_before,
        after=cpu_after,
        clock_ticks_per_second=clock_ticks,
        measured_requests=token_score_requests,
        elapsed_seconds=elapsed_seconds,
    )

    failures = sum(int(task["result"]["failures"]) for task in tasks)
    output = {
        "schema_version": 1,
        "experiment_id": "E10d",
        "model": args.model,
        "model_sha256": args.model_sha256,
        "server_pid": args.server_pid,
        "parameters": {
            "cache_prompt_policy": "false for the first token of every candidate; true only for later tokens of that candidate",
            "score_distribution": "raw pre-sampling selected token log probability",
            "sampled_output_used_for_score": False,
            "requests_per_token": 1,
            "max_length": prepared["max_length"],
            "fewshot": prepared["fewshot"],
            "apply_chat_template": prepared["apply_chat_template"],
            "seed": args.seed,
        },
        "tasks": tasks,
        "process_cpu": process_cpu,
        "result": {
            "failures": failures,
            "samples": sum(int(task["result"]["sample_count"]) for task in tasks),
            "candidate_requests": candidate_requests,
            "token_score_requests": token_score_requests,
            "elapsed_seconds": elapsed_seconds,
            "samples_per_second": 300 / elapsed_seconds,
        },
    }
    if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
        raise ValueError("invalid holdout elapsed time")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output["result"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
