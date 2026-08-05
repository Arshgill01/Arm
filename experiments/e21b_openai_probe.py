#!/usr/bin/env python3
"""Run the E21b OpenAI-compatible online-certificate trace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import summarize
    from experiments.e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from experiments.e9c_probe import parse_prediction, post_json, render_tokens
    from experiments.e21a_online_policy import OnlineCertificate, identity_sha256
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e9c_probe import parse_prediction, post_json, render_tokens
    from e21a_online_policy import OnlineCertificate, identity_sha256


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def prompt_sha256(tokens: list[int]) -> str:
    return hashlib.sha256(
        json.dumps(tokens, separators=(",", ":")).encode()
    ).hexdigest()


def openai_request_payload(
    *,
    candidate: str,
    instruction: str,
    task: dict[str, Any],
    cache_prompt: bool,
    maximum_output_tokens: int,
    seed: int,
) -> dict[str, Any]:
    """Build the exact quality-path request with explicit cache routing."""
    return {
        "model": candidate,
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": task["prompt"]},
        ],
        "temperature": 0.0,
        "seed": seed,
        "max_tokens": maximum_output_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "cache_prompt": cache_prompt,
    }


def request_chat(
    origin: str,
    *,
    http_call_index: int,
    served_index: int,
    task: dict[str, Any],
    tokens: list[int],
    cache_prompt: bool,
    role: str,
    contract: dict[str, Any],
    instruction: str,
) -> dict[str, Any]:
    payload = openai_request_payload(
        candidate=contract["selected"]["candidate"],
        instruction=instruction,
        task=task,
        cache_prompt=cache_prompt,
        maximum_output_tokens=contract["workload"]["maximum_output_tokens"],
        seed=contract["workload"]["seed"],
    )
    started = time.perf_counter_ns()
    response: dict[str, Any] | None = None
    try:
        status, response = post_json(
            origin,
            contract["client"]["api_path"],
            payload,
            contract["workload"]["timeout_seconds"],
        )
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        choices = response.get("choices")
        choice = choices[0] if isinstance(choices, list) and len(choices) == 1 else {}
        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        timings = response.get("timings")
        timings = timings if isinstance(timings, dict) else {}
        return {
            "http_call_index": http_call_index,
            "served_index": served_index,
            "task_id": task["id"],
            "api_path": contract["client"]["api_path"],
            "request_payload": payload,
            "request_payload_sha256": canonical_sha256(payload),
            "prompt_sha256": prompt_sha256(tokens),
            "prompt_tokens": len(tokens),
            "cache_prompt": cache_prompt,
            "role": role,
            "http_status": status,
            "response": content,
            "prediction": parse_prediction(content),
            "stop_type": choice.get("finish_reason")
            if isinstance(choice, dict)
            else None,
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
            "api_path": contract["client"]["api_path"],
            "request_payload": payload,
            "request_payload_sha256": canonical_sha256(payload),
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


def run_probe(
    *,
    origin: str,
    contract: dict[str, Any],
    tasks: dict[str, Any],
    policy: str,
    server_pid: int,
) -> dict[str, Any]:
    if contract.get("experiment_id") != "E21b-preflight":
        raise ValueError("unsupported E21b contract")
    instruction = tasks["instruction"]
    task_by_id = {item["id"]: item for item in tasks["tasks"]}
    sequence = [
        task_by_id[task_id] for task_id in contract["workload"]["task_sequence"]
    ]
    tokens_by_id = {
        task_id: render_tokens(
            origin,
            instruction,
            task_by_id[task_id]["prompt"],
            contract["workload"]["timeout_seconds"],
        )
        for task_id in contract["workload"]["task_ids"]
    }
    fingerprints = {
        task_id: prompt_sha256(tokens) for task_id, tokens in tokens_by_id.items()
    }
    prior = set(contract["prior_certificate"]["prompt_fingerprints"])
    if (
        len(fingerprints) != contract["workload"]["unique_prompts"]
        or len(set(fingerprints.values())) != len(fingerprints)
        or set(fingerprints.values()) & prior
    ):
        raise ValueError("E21b prompt fingerprints are not unique and unseen")

    controller = OnlineCertificate(
        contract["identity"],
        minimum_cached_tokens=contract["workload"]["minimum_cached_tokens"],
    )
    raw_calls: list[dict[str, Any]] = []
    served_records: list[dict[str, Any]] = []
    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = read_process_cpu(server_pid)
    started = time.perf_counter_ns()
    tasks_per_cycle = contract["workload"]["unique_prompts"]
    for served_index, task in enumerate(sequence):
        tokens = tokens_by_id[task["id"]]
        if policy == "all_uncached":
            first = request_chat(
                origin,
                http_call_index=len(raw_calls),
                served_index=served_index,
                task=task,
                tokens=tokens,
                cache_prompt=False,
                role="baseline_uncached",
                contract=contract,
                instruction=instruction,
            )
            raw_calls.append(first)
            record = {
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
            first = request_chat(
                origin,
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
                instruction=instruction,
            )
            raw_calls.append(first)
            oracle = None
            if plan["oracle_required"]:
                oracle = request_chat(
                    origin,
                    http_call_index=len(raw_calls),
                    served_index=served_index,
                    task=task,
                    tokens=tokens,
                    cache_prompt=False,
                    role="uncached_oracle",
                    contract=contract,
                    instruction=instruction,
                )
                raw_calls.append(oracle)
            completed = controller.complete(plan, first, oracle)
            record = {
                "route": completed["route"],
                "admission": completed["admission"],
                "served_source": completed["served_source"],
                "shadow_cached_attempt_served": completed[
                    "shadow_cached_attempt_served"
                ],
                "served_response": completed["served_response"],
                "served_call": completed["served_call"],
                "user_http_ms": first["http_ms"]
                + (oracle["http_ms"] if oracle else 0.0),
                "transition_sha256": completed["transition_sha256"],
            }
        reference = contract["workload"]["reference_predictions"][task["id"]]
        record.update(
            {
                "served_index": served_index,
                "cycle_index": served_index // tasks_per_cycle + 1,
                "cycle_task_index": served_index % tasks_per_cycle,
                "task_id": task["id"],
                "prompt_sha256": fingerprints[task["id"]],
                "expected": task["answer"],
                "reference_prediction": reference,
            }
        )
        record["prediction"] = parse_prediction(record["served_response"])
        record["correct"] = record["prediction"] == record["expected"]
        record["reference_match"] = record["prediction"] == reference
        served_records.append(record)

    elapsed_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
    process_cpu = summarize_process_cpu(
        cpu_before,
        read_process_cpu(server_pid),
        clock_ticks_per_second=clock_ticks,
        measured_requests=len(served_records),
        elapsed_seconds=elapsed_seconds,
    )
    routes = Counter(record["route"] for record in served_records)
    admissions = Counter(
        record["admission"] for record in served_records if record["admission"]
    )
    return {
        "schema_version": 1,
        "experiment_id": "E21b-preflight",
        "policy": policy,
        "identity_sha256": identity_sha256(contract["identity"]),
        "client_identity_sha256": contract["client_identity_sha256"],
        "unseen_prompt_fingerprints": fingerprints,
        "served_records": served_records,
        "raw_calls": raw_calls,
        "process_cpu": process_cpu,
        "result": {
            "served_requests": len(served_records),
            "actual_http_calls": len(raw_calls),
            "elapsed_seconds": elapsed_seconds,
            "served_requests_per_second": len(served_records) / elapsed_seconds,
            "request_failures": sum(call["error"] is not None for call in raw_calls),
            "correct": sum(record["correct"] for record in served_records),
            "reference_prediction_mismatches": sum(
                not record["reference_match"] for record in served_records
            ),
            "route_counts": dict(sorted(routes.items())),
            "admission_counts": dict(sorted(admissions.items())),
            "user_http_ms": summarize(
                [record["user_http_ms"] for record in served_records]
            ),
            "raw_http_ms": summarize([record["http_ms"] for record in raw_calls]),
        },
        "registry": controller.export_registry() if policy == "online" else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--policy", choices=("all_uncached", "online"), required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(
        origin=args.url,
        contract=load_object(args.contract),
        tasks=load_object(args.tasks),
        policy=args.policy,
        server_pid=args.server_pid,
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["result"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
