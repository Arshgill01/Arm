#!/usr/bin/env python3
"""Run one baseline or online-certificate E21a native preflight trace."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import summarize
    from experiments.e5b_inference_probe import (
        read_process_cpu,
        summarize_process_cpu,
    )
    from experiments.e9c_probe import parse_prediction, post_json, render_tokens
    from experiments.e21a_online_policy import (
        OnlineCertificate,
        identity_sha256,
        valid_call,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e9c_probe import parse_prediction, post_json, render_tokens
    from e21a_online_policy import OnlineCertificate, identity_sha256, valid_call


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def prompt_sha256(tokens: list[int]) -> str:
    return hashlib.sha256(
        json.dumps(tokens, separators=(",", ":")).encode()
    ).hexdigest()


def request_completion(
    origin: str,
    *,
    http_call_index: int,
    served_index: int,
    task: dict[str, Any],
    tokens: list[int],
    cache_prompt: bool,
    role: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter_ns()
    response: dict[str, Any] | None = None
    try:
        status, response = post_json(
            origin,
            "/completion",
            {
                "prompt": tokens,
                "n_predict": contract["workload"]["maximum_output_tokens"],
                "temperature": 0.0,
                "seed": contract["workload"]["seed"],
                "cache_prompt": cache_prompt,
                "stream": False,
            },
            contract["workload"]["timeout_seconds"],
        )
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        timings = response.get("timings")
        timings = timings if isinstance(timings, dict) else {}
        content = response.get("content")
        return {
            "http_call_index": http_call_index,
            "served_index": served_index,
            "task_id": task["id"],
            "prompt_sha256": prompt_sha256(tokens),
            "prompt_tokens": len(tokens),
            "cache_prompt": cache_prompt,
            "role": role,
            "http_status": status,
            "response": content,
            "prediction": parse_prediction(content),
            "stop_type": response.get("stop_type"),
            "generated_tokens": timings.get("predicted_n"),
            "cached_tokens": timings.get("cache_n"),
            "evaluated_prompt_tokens": timings.get("prompt_n"),
            "encode_ms": timings.get("prompt_ms"),
            "decode_ms": timings.get("predicted_ms"),
            "http_ms": elapsed_ms,
            "error": None,
        }
    except Exception as error:
        return {
            "http_call_index": http_call_index,
            "served_index": served_index,
            "task_id": task["id"],
            "prompt_sha256": prompt_sha256(tokens),
            "prompt_tokens": len(tokens),
            "cache_prompt": cache_prompt,
            "role": role,
            "http_status": None,
            "response": None,
            "prediction": None,
            "stop_type": None,
            "generated_tokens": None,
            "cached_tokens": None,
            "evaluated_prompt_tokens": None,
            "encode_ms": None,
            "decode_ms": None,
            "http_ms": (time.perf_counter_ns() - started) / 1_000_000,
            "error": f"{type(error).__name__}: {error}",
            "raw_response": response,
        }


def valid_nonnegative_numbers(records: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    for record in records:
        for field in fields:
            value = record.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError(f"invalid E21a {field}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--policy", choices=("all_uncached", "online"), required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_object(args.contract)
    tasks = load_object(args.tasks)
    if contract.get("experiment_id") != "E21a-preflight":
        raise ValueError("unsupported E21a preflight contract")
    task_by_id = {item["id"]: item for item in tasks["tasks"]}
    sequence = [task_by_id[task_id] for task_id in contract["workload"]["task_sequence"]]
    tokens_by_id = {
        task["id"]: render_tokens(
            args.url,
            tasks["instruction"],
            task["prompt"],
            contract["workload"]["timeout_seconds"],
        )
        for task in {item["id"]: item for item in sequence}.values()
    }
    prior = set(contract["prior_certificate"]["prompt_fingerprints"])
    fingerprints = {task_id: prompt_sha256(tokens) for task_id, tokens in tokens_by_id.items()}
    if set(fingerprints.values()) & prior:
        raise ValueError("E21a preflight prompt is not unseen")

    controller = OnlineCertificate(
        contract["identity"],
        minimum_cached_tokens=contract["workload"]["minimum_cached_tokens"],
    )
    raw_calls: list[dict[str, Any]] = []
    served_records: list[dict[str, Any]] = []
    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = read_process_cpu(args.server_pid)
    started = time.perf_counter_ns()
    for served_index, task in enumerate(sequence):
        tokens = tokens_by_id[task["id"]]
        if args.policy == "all_uncached":
            first = request_completion(
                args.url,
                http_call_index=len(raw_calls),
                served_index=served_index,
                task=task,
                tokens=tokens,
                cache_prompt=False,
                role="baseline_uncached",
                contract=contract,
            )
            raw_calls.append(first)
            record = {
                "served_index": served_index,
                "task_id": task["id"],
                "prompt_sha256": fingerprints[task["id"]],
                "route": "baseline_uncached",
                "admission": None,
                "served_source": "baseline_uncached",
                "shadow_cached_attempt_served": False,
                "served_response": first["response"],
                "served_call": first,
                "user_http_ms": first["http_ms"],
            }
        else:
            plan = controller.plan(fingerprints[task["id"]])
            first = request_completion(
                args.url,
                http_call_index=len(raw_calls),
                served_index=served_index,
                task=task,
                tokens=tokens,
                cache_prompt=plan["first_call_cache_prompt"],
                role=(
                    "unknown_cached_shadow"
                    if plan["route"] == "unknown_shadow_then_oracle"
                    else plan["route"]
                ),
                contract=contract,
            )
            raw_calls.append(first)
            oracle = None
            if plan["oracle_required"] or (
                plan["route"] == "certified_cache" and not valid_call(first)
            ):
                oracle = request_completion(
                    args.url,
                    http_call_index=len(raw_calls),
                    served_index=served_index,
                    task=task,
                    tokens=tokens,
                    cache_prompt=False,
                    role="uncached_oracle",
                    contract=contract,
                )
                raw_calls.append(oracle)
            completed = controller.complete(plan, first, oracle)
            user_http_ms = first["http_ms"] + (oracle["http_ms"] if oracle else 0)
            record = {
                "served_index": served_index,
                "task_id": task["id"],
                "prompt_sha256": fingerprints[task["id"]],
                "route": completed["route"],
                "admission": completed["admission"],
                "served_source": completed["served_source"],
                "shadow_cached_attempt_served": completed[
                    "shadow_cached_attempt_served"
                ],
                "served_response": completed["served_response"],
                "served_call": completed["served_call"],
                "user_http_ms": user_http_ms,
                "transition_sha256": completed["transition_sha256"],
            }
        record["expected"] = task["answer"]
        record["reference_prediction"] = contract["workload"][
            "reference_predictions"
        ][task["id"]]
        record["prediction"] = parse_prediction(record["served_response"])
        record["correct"] = record["prediction"] == task["answer"]
        record["reference_match"] = (
            record["prediction"] == record["reference_prediction"]
        )
        served_records.append(record)

    elapsed_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
    cpu_after = read_process_cpu(args.server_pid)
    valid_nonnegative_numbers(
        raw_calls, ("http_ms", "encode_ms", "decode_ms", "cached_tokens")
    )
    process_cpu = summarize_process_cpu(
        cpu_before,
        cpu_after,
        clock_ticks_per_second=clock_ticks,
        measured_requests=len(served_records),
        elapsed_seconds=elapsed_seconds,
    )
    route_counts = Counter(record["route"] for record in served_records)
    admission_counts = Counter(
        record["admission"] for record in served_records if record["admission"]
    )
    output = {
        "schema_version": 1,
        "experiment_id": "E21a-preflight",
        "policy": args.policy,
        "identity_sha256": identity_sha256(contract["identity"]),
        "unseen_prompt_fingerprints": fingerprints,
        "served_records": served_records,
        "raw_calls": raw_calls,
        "process_cpu": process_cpu,
        "result": {
            "served_requests": len(served_records),
            "actual_http_calls": len(raw_calls),
            "elapsed_seconds": elapsed_seconds,
            "served_requests_per_second": len(served_records) / elapsed_seconds,
            "request_failures": sum(
                not valid_call(record["served_call"]) for record in served_records
            ),
            "correct": sum(record["correct"] for record in served_records),
            "reference_prediction_mismatches": sum(
                not record["reference_match"] for record in served_records
            ),
            "route_counts": dict(sorted(route_counts.items())),
            "admission_counts": dict(sorted(admission_counts.items())),
            "user_http_ms": summarize(
                [record["user_http_ms"] for record in served_records]
            ),
            "raw_http_ms": summarize([record["http_ms"] for record in raw_calls]),
        },
        "registry": controller.export_registry() if args.policy == "online" else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output["result"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
