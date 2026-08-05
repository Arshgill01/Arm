#!/usr/bin/env python3
"""Run one full E21a baseline or online-certificate service trace."""

from __future__ import annotations

import argparse
import json
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
    from experiments.e9c_probe import parse_prediction, render_tokens
    from experiments.e21a_online_policy import (
        OnlineCertificate,
        identity_sha256,
        valid_call,
    )
    from experiments.e21a_preflight_probe import (
        load_object,
        prompt_sha256,
        request_completion,
        valid_nonnegative_numbers,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e9c_probe import parse_prediction, render_tokens
    from e21a_online_policy import OnlineCertificate, identity_sha256, valid_call
    from e21a_preflight_probe import (
        load_object,
        prompt_sha256,
        request_completion,
        valid_nonnegative_numbers,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--policy", choices=("all_uncached", "online"), required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_object(args.contract)
    tasks = load_object(args.tasks)
    if contract.get("experiment_id") != "E21a":
        raise ValueError("unsupported E21a contract")
    task_by_id = {item["id"]: item for item in tasks["tasks"]}
    sequence = [
        task_by_id[task_id] for task_id in contract["workload"]["task_sequence"]
    ]
    tokens_by_id = {
        task_id: render_tokens(
            args.url,
            tasks["instruction"],
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
        raise ValueError("E21a full prompt fingerprints are not unique and unseen")

    controller = OnlineCertificate(
        contract["identity"],
        minimum_cached_tokens=contract["workload"]["minimum_cached_tokens"],
    )
    raw_calls: list[dict[str, Any]] = []
    served_records: list[dict[str, Any]] = []
    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = read_process_cpu(args.server_pid)
    started = time.perf_counter_ns()
    tasks_per_cycle = len(contract["workload"]["task_ids"])
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
            record = {
                "route": completed["route"],
                "admission": completed["admission"],
                "served_source": completed["served_source"],
                "shadow_cached_attempt_served": completed[
                    "shadow_cached_attempt_served"
                ],
                "served_response": completed["served_response"],
                "served_call": completed["served_call"],
                "user_http_ms": first["http_ms"] + (oracle["http_ms"] if oracle else 0),
                "transition_sha256": completed["transition_sha256"],
            }
        record.update(
            {
                "served_index": served_index,
                "cycle_index": served_index // tasks_per_cycle + 1,
                "cycle_task_index": served_index % tasks_per_cycle,
                "task_id": task["id"],
                "prompt_sha256": fingerprints[task["id"]],
                "expected": task["answer"],
                "reference_prediction": contract["workload"]["reference_predictions"][
                    task["id"]
                ],
            }
        )
        record["prediction"] = parse_prediction(record["served_response"])
        record["correct"] = record["prediction"] == record["expected"]
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
        "experiment_id": "E21a",
        "policy": args.policy,
        "repetition": args.repetition,
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
