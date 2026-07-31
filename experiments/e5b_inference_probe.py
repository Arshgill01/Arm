#!/usr/bin/env python3
"""Measure selected-model inference serving under a frozen configuration."""

from __future__ import annotations

import argparse
import http.client
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    from experiments.e1_ingest import summarize
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize


LETTERS = {"A", "B", "C", "D"}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_reference_predictions(
    manifest: dict[str, Any], candidate: str
) -> dict[str, str]:
    application = manifest.get("application")
    if not isinstance(application, dict) or candidate not in application:
        raise ValueError("reference manifest lacks the selected candidate")
    repetitions = application[candidate].get("quality_repetitions")
    if not isinstance(repetitions, list) or len(repetitions) < 2:
        raise ValueError("reference manifest lacks repeated quality predictions")
    prediction_maps = [item.get("predictions") for item in repetitions]
    if not all(isinstance(item, dict) for item in prediction_maps):
        raise ValueError("reference quality repetition lacks predictions")
    if any(item != prediction_maps[0] for item in prediction_maps[1:]):
        raise ValueError("reference predictions are not stable")
    if any(value not in LETTERS for value in prediction_maps[0].values()):
        raise ValueError("reference predictions are not standalone answer letters")
    return dict(prediction_maps[0])


def request_case(
    base_url: str,
    index: int,
    task: dict[str, Any],
    instruction: str,
    candidate: str,
    reference_prediction: str,
    max_output_tokens: int,
    seed: int,
    timeout: float,
    cache_prompt: bool | None = None,
    id_slot: int | None = None,
) -> dict[str, Any]:
    parsed = urlsplit(base_url)
    connection = http.client.HTTPConnection(
        parsed.hostname, parsed.port, timeout=timeout
    )
    request = {
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
    if cache_prompt is not None:
        request["cache_prompt"] = cache_prompt
    if id_slot is not None:
        request["id_slot"] = id_slot
    body = json.dumps(request).encode("utf-8")
    started = time.perf_counter_ns()
    try:
        connection.request(
            "POST",
            "/v1/chat/completions",
            body=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        http_ms = (time.perf_counter_ns() - started) / 1_000_000
        choices = payload.get("choices") if isinstance(payload, dict) else None
        timings = payload.get("timings") if isinstance(payload, dict) else None
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else {}
        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        predicted = content if content in LETTERS else None
        return {
            "index": index,
            "id": task["id"],
            "category": task["category"],
            "expected": task["answer"],
            "reference_prediction": reference_prediction,
            "status": response.status,
            "response": content,
            "predicted": predicted,
            "correct": predicted == task["answer"],
            "reference_match": predicted == reference_prediction,
            "termination_reason": choice.get("finish_reason")
            if isinstance(choice, dict)
            else None,
            "generated_tokens": timings.get("predicted_n")
            if isinstance(timings, dict)
            else None,
            "cached_tokens": timings.get("cache_n")
            if isinstance(timings, dict)
            else None,
            "evaluated_prompt_tokens": timings.get("prompt_n")
            if isinstance(timings, dict)
            else None,
            "encode_ms": timings.get("prompt_ms")
            if isinstance(timings, dict)
            else None,
            "decode_ms": timings.get("predicted_ms")
            if isinstance(timings, dict)
            else None,
            "http_ms": http_ms,
            "error": None,
        }
    except Exception as error:
        return {
            "index": index,
            "id": task["id"],
            "category": task["category"],
            "expected": task["answer"],
            "reference_prediction": reference_prediction,
            "status": None,
            "response": None,
            "predicted": None,
            "correct": False,
            "reference_match": False,
            "termination_reason": None,
            "generated_tokens": None,
            "cached_tokens": None,
            "evaluated_prompt_tokens": None,
            "encode_ms": None,
            "decode_ms": None,
            "http_ms": (time.perf_counter_ns() - started) / 1_000_000,
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        connection.close()


def run_probe(
    *,
    base_url: str,
    tasks_manifest: dict[str, Any],
    reference_predictions: dict[str, str],
    candidate: str,
    configuration: str,
    repetition: int,
    warmup_task_ids: list[str],
    concurrency: int,
    max_output_tokens: int,
    seed: int,
    timeout: float,
    experiment_id: str = "E5b",
    cache_prompt: bool | None = None,
    warmup_slot_ids: list[int] | None = None,
) -> dict[str, Any]:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.path not in {"", "/"}:
        raise ValueError("--url must be an HTTP origin without a path")
    instruction = tasks_manifest.get("instruction")
    raw_tasks = tasks_manifest.get("tasks")
    if tasks_manifest.get("schema_version") != 1 or not isinstance(instruction, str):
        raise ValueError("invalid task manifest")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("task manifest contains no tasks")
    tasks = {task["id"]: task for task in raw_tasks}
    if set(tasks) != set(reference_predictions):
        raise ValueError("task IDs differ from the selected reference predictions")
    if any(task_id not in tasks for task_id in warmup_task_ids):
        raise ValueError("unknown warmup task ID")
    if warmup_slot_ids is not None and (
        len(warmup_slot_ids) != len(warmup_task_ids)
        or any(slot_id < 0 for slot_id in warmup_slot_ids)
    ):
        raise ValueError("warmup slot IDs must be non-negative and match warmup tasks")

    warmups = [
        request_case(
            base_url,
            index,
            tasks[task_id],
            instruction,
            candidate,
            reference_predictions[task_id],
            max_output_tokens,
            seed,
            timeout,
            cache_prompt,
            warmup_slot_ids[index] if warmup_slot_ids is not None else None,
        )
        for index, task_id in enumerate(warmup_task_ids)
    ]
    started = time.perf_counter_ns()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        cases = list(
            executor.map(
                lambda indexed_task: request_case(
                    base_url,
                    indexed_task[0],
                    indexed_task[1],
                    instruction,
                    candidate,
                    reference_predictions[indexed_task[1]["id"]],
                    max_output_tokens,
                    seed,
                    timeout,
                    cache_prompt,
                ),
                enumerate(raw_tasks),
            )
        )
    elapsed_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
    failures = [
        case
        for case in cases
        if case["status"] != 200
        or case["error"] is not None
        or case["predicted"] is None
    ]
    valid_timings = [case for case in cases if case["encode_ms"] is not None]
    parameters = {
        "base_url": base_url,
        "candidate": candidate,
        "configuration": configuration,
        "repetition": repetition,
        "warmup_task_ids": warmup_task_ids,
        "measured_tasks": len(raw_tasks),
        "client_concurrency": concurrency,
        "max_output_tokens": max_output_tokens,
        "instruction_role": "system",
        "chat_template_mode": "model_jinja_system_instruction",
        "temperature": 0.0,
        "seed": seed,
        "timeout_seconds": timeout,
        "prompt_cache": cache_prompt,
    }
    if warmup_slot_ids is not None:
        parameters["warmup_slot_ids"] = warmup_slot_ids
    return {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "parameters": parameters,
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
            "elapsed_seconds": elapsed_seconds,
            "requests_per_second": len(cases) / elapsed_seconds,
            "http_ms": summarize([float(case["http_ms"]) for case in cases]),
            "encode_ms": (
                summarize([float(case["encode_ms"]) for case in valid_timings])
                if valid_timings
                else None
            ),
            "decode_ms": (
                summarize([float(case["decode_ms"]) for case in valid_timings])
                if valid_timings
                else None
            ),
            "cached_tokens": (
                summarize([float(case["cached_tokens"]) for case in valid_timings])
                if valid_timings
                else None
            ),
            "evaluated_prompt_tokens": (
                summarize(
                    [float(case["evaluated_prompt_tokens"]) for case in valid_timings]
                )
                if valid_timings
                else None
            ),
            "status_counts": {
                str(status): sum(case["status"] == status for case in cases)
                for status in sorted(
                    {case["status"] for case in cases if case["status"] is not None}
                )
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--reference-manifest", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--configuration", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--warmup-task", action="append", default=[])
    parser.add_argument("--warmup-slot", type=int, action="append")
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--max-output-tokens", type=int, default=8)
    parser.add_argument("--seed", type=int, default=424242)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--experiment-id", default="E5b")
    cache = parser.add_mutually_exclusive_group()
    cache.add_argument("--cache-prompt", dest="cache_prompt", action="store_true")
    cache.add_argument("--no-cache-prompt", dest="cache_prompt", action="store_false")
    parser.set_defaults(cache_prompt=None)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    if (
        arguments.repetition <= 0
        or arguments.concurrency <= 0
        or arguments.max_output_tokens <= 0
        or arguments.timeout <= 0
        or not arguments.experiment_id.strip()
    ):
        raise ValueError(
            "repetition, concurrency, output cap, and timeout must be positive"
        )
    evidence = run_probe(
        base_url=arguments.url,
        tasks_manifest=load_object(arguments.tasks),
        reference_predictions=load_reference_predictions(
            load_object(arguments.reference_manifest), arguments.candidate
        ),
        candidate=arguments.candidate,
        configuration=arguments.configuration,
        repetition=arguments.repetition,
        warmup_task_ids=arguments.warmup_task,
        concurrency=arguments.concurrency,
        max_output_tokens=arguments.max_output_tokens,
        seed=arguments.seed,
        timeout=arguments.timeout,
        experiment_id=arguments.experiment_id,
        cache_prompt=arguments.cache_prompt,
        warmup_slot_ids=arguments.warmup_slot,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
