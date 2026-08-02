#!/usr/bin/env python3
"""Run one frozen E9c alternating-prefix cache cell."""

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
    from experiments.e5b_inference_probe import (
        read_process_cpu,
        summarize_process_cpu,
    )
    from experiments.e5b_ingest import reference_predictions
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e5b_ingest import reference_predictions


LETTERS = {"A", "B", "C", "D"}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return value


def post_json(
    origin: str,
    path: str,
    payload: dict[str, Any],
    timeout: float,
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


def longest_common_prefix(values: list[list[int]]) -> int:
    if not values:
        raise ValueError("token sequences are empty")
    limit = min(len(value) for value in values)
    for index in range(limit):
        if len({value[index] for value in values}) != 1:
            return index
    return limit


def parse_prediction(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    stripped = text.strip().upper()
    return stripped if stripped in LETTERS else None


def render_tokens(
    origin: str,
    system: str,
    user: str,
    timeout: float,
) -> list[int]:
    status, rendered = post_json(
        origin,
        "/apply-template",
        {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout,
    )
    prompt = rendered.get("prompt")
    if status != 200 or not isinstance(prompt, str):
        raise ValueError("/apply-template did not return a prompt")
    status, tokenized = post_json(
        origin,
        "/tokenize",
        {"content": prompt, "add_special": False, "parse_special": True},
        timeout,
    )
    tokens = tokenized.get("tokens")
    if (
        status != 200
        or not isinstance(tokens, list)
        or not tokens
        or any(type(token) is not int for token in tokens)
    ):
        raise ValueError("/tokenize did not return token IDs")
    return tokens


def system_text(repetitions: int, marker: str, instruction: str) -> str:
    return "Cache" + " cache" * repetitions + f" {marker}. {instruction}"


def solve_prefix_recipe(
    origin: str,
    target: int,
    markers: list[str],
    marker_token_ids: list[int],
    instruction: str,
    calibration_prompt: str,
    timeout: float,
) -> dict[str, Any]:
    for repetitions in range(target + 32):
        sequences = [
            render_tokens(
                origin,
                system_text(repetitions, marker, instruction),
                calibration_prompt,
                timeout,
            )
            for marker in markers
        ]
        common = longest_common_prefix(sequences)
        if common != target:
            continue
        observed_markers = [sequence[target] for sequence in sequences]
        if observed_markers != marker_token_ids:
            raise ValueError("variant marker token IDs differ from the contract")
        prefix = sequences[0][:target]
        return {
            "target_shared_prefix_tokens": target,
            "common_filler_repetitions": repetitions,
            "common_prefix_token_ids": prefix,
            "common_prefix_sha256": hashlib.sha256(
                json.dumps(prefix, separators=(",", ":")).encode()
            ).hexdigest(),
            "variant_marker_token_ids": observed_markers,
        }
    raise ValueError(f"could not construct exact {target}-token common prefix")


def request_completion(
    origin: str,
    *,
    index: int,
    task: dict[str, Any],
    marker: str,
    marker_index: int,
    prompt_tokens: list[int],
    reference: str,
    cache_prompt: bool,
    max_output_tokens: int,
    seed: int,
    timeout: float,
) -> dict[str, Any]:
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
        content = response.get("content")
        timings = response.get("timings")
        timings = timings if isinstance(timings, dict) else {}
        prediction = parse_prediction(content)
        return {
            "index": index,
            "task_id": task["id"],
            "prefix_marker": marker,
            "prefix_marker_index": marker_index,
            "prompt_tokens": len(prompt_tokens),
            "prompt_sha256": hashlib.sha256(
                json.dumps(prompt_tokens, separators=(",", ":")).encode()
            ).hexdigest(),
            "reference_prediction": reference,
            "http_status": status,
            "response": content,
            "prediction": prediction,
            "reference_match": prediction == reference,
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
            "index": index,
            "task_id": task["id"],
            "prefix_marker": marker,
            "prefix_marker_index": marker_index,
            "prompt_tokens": len(prompt_tokens),
            "prompt_sha256": hashlib.sha256(
                json.dumps(prompt_tokens, separators=(",", ":")).encode()
            ).hexdigest(),
            "reference_prediction": reference,
            "http_status": None,
            "response": None,
            "prediction": None,
            "reference_match": False,
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


def require_measured_cases(cases: list[dict[str, Any]]) -> None:
    for case in cases:
        for name in (
            "encode_ms",
            "decode_ms",
            "http_ms",
            "cached_tokens",
            "evaluated_prompt_tokens",
            "response_tokens_cached",
            "response_tokens_evaluated",
        ):
            value = case.get(name)
            if (
                not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"invalid {name} in measured case")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--reference-manifest", type=Path, required=True)
    parser.add_argument("--prefix-cardinality", type=int, required=True)
    parser.add_argument("--shared-prefix-tokens", type=int, required=True)
    parser.add_argument("--cache-prompt", choices=("true", "false"), required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_object(args.contract)
    tasks_manifest = load_object(args.tasks)
    selected_manifest = load_object(args.reference_manifest)
    if contract.get("experiment_id") != "E9c":
        raise ValueError("unsupported contract")
    workload = contract["workload"]
    construction = contract["prompt_construction"]
    if args.prefix_cardinality not in workload["prefix_cardinalities"]:
        raise ValueError("prefix cardinality differs from the contract")
    if args.shared_prefix_tokens not in workload["shared_prefix_tokens"]:
        raise ValueError("shared-prefix length differs from the contract")
    if args.repetition not in {1, 2}:
        raise ValueError("repetition differs from the contract")

    task_by_id = {task["id"]: task for task in tasks_manifest["tasks"]}
    measured_tasks = [task_by_id[task_id] for task_id in workload["measured_task_ids"]]
    warmup_task = task_by_id[workload["warmup_task_id"]]
    references = reference_predictions(
        selected_manifest, contract["selected"]["candidate"]
    )
    markers = construction["variant_markers"]
    marker_token_ids = construction["variant_marker_token_ids"]
    recipe = solve_prefix_recipe(
        args.url,
        args.shared_prefix_tokens,
        markers,
        marker_token_ids,
        construction["instruction_suffix"],
        warmup_task["prompt"],
        workload["timeout_seconds"],
    )

    prompt_map: dict[tuple[str, str], list[int]] = {}
    required_task_ids = sorted(
        set(workload["measured_task_ids"] + [workload["warmup_task_id"]])
    )
    for marker_index, marker in enumerate(markers):
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
            if tokens[: args.shared_prefix_tokens] != recipe["common_prefix_token_ids"]:
                raise ValueError("rendered prompt changed the frozen common prefix")
            if tokens[args.shared_prefix_tokens] != marker_token_ids[marker_index]:
                raise ValueError("rendered prompt changed the variant boundary")
            if len(tokens) > construction["maximum_prompt_tokens"]:
                raise ValueError("rendered prompt exceeds the E7c context contract")
            prompt_map[(marker, task_id)] = tokens

    cache_prompt = args.cache_prompt == "true"
    active_markers = markers[: args.prefix_cardinality]
    warmups = []
    for index, marker in enumerate(active_markers):
        warmups.append(
            request_completion(
                args.url,
                index=index,
                task=warmup_task,
                marker=marker,
                marker_index=index,
                prompt_tokens=prompt_map[(marker, warmup_task["id"])],
                reference=references[warmup_task["id"]],
                cache_prompt=cache_prompt,
                max_output_tokens=workload["maximum_output_tokens"],
                seed=workload["seed"],
                timeout=workload["timeout_seconds"],
            )
        )

    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = read_process_cpu(args.server_pid)
    started = time.perf_counter_ns()
    cases = []
    for index, task in enumerate(measured_tasks):
        marker_index = index % args.prefix_cardinality
        marker = active_markers[marker_index]
        cases.append(
            request_completion(
                args.url,
                index=index,
                task=task,
                marker=marker,
                marker_index=marker_index,
                prompt_tokens=prompt_map[(marker, task["id"])],
                reference=references[task["id"]],
                cache_prompt=cache_prompt,
                max_output_tokens=workload["maximum_output_tokens"],
                seed=workload["seed"],
                timeout=workload["timeout_seconds"],
            )
        )
    elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
    cpu_after = read_process_cpu(args.server_pid)
    require_measured_cases(cases)
    process_cpu = summarize_process_cpu(
        cpu_before,
        cpu_after,
        clock_ticks_per_second=clock_ticks,
        measured_requests=len(cases),
        elapsed_seconds=elapsed,
    )
    request_failures = sum(
        case["http_status"] != 200 or case["error"] is not None for case in cases
    )
    invalid_predictions = sum(case["prediction"] is None for case in cases)
    mismatches = sum(not case["reference_match"] for case in cases)
    output = {
        "schema_version": 1,
        "experiment_id": "E9c",
        "parameters": {
            "prefix_cardinality": args.prefix_cardinality,
            "shared_prefix_tokens": args.shared_prefix_tokens,
            "cache_prompt": cache_prompt,
            "repetition": args.repetition,
            "measured_requests": len(cases),
            "client_concurrency": workload["client_concurrency"],
            "seed": workload["seed"],
            "maximum_output_tokens": workload["maximum_output_tokens"],
            "server_pid": args.server_pid,
        },
        "prefix_recipe": recipe,
        "warmups": warmups,
        "cases": cases,
        "process_cpu": process_cpu,
        "result": {
            "elapsed_seconds": elapsed,
            "requests_per_second": len(cases) / elapsed,
            "failures": request_failures,
            "invalid_prediction_responses": invalid_predictions,
            "reference_prediction_mismatches": mismatches,
            "http_ms": summarize([float(case["http_ms"]) for case in cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in cases]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in cases]),
            "cached_tokens": summarize(
                [float(case["cached_tokens"]) for case in cases]
            ),
            "evaluated_prompt_tokens": summarize(
                [float(case["evaluated_prompt_tokens"]) for case in cases]
            ),
            "prompt_tokens": summarize(
                [float(case["prompt_tokens"]) for case in cases]
            ),
        },
    }
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
