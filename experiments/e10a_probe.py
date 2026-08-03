#!/usr/bin/env python3
"""Run one frozen E10a cache-divergence calibration cell."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import summarize
    from experiments.e5b_inference_probe import (
        read_process_cpu,
        summarize_process_cpu,
    )
    from experiments.e5b_ingest import reference_predictions
    from experiments.e9c_probe import (
        load_object,
        post_json,
        render_tokens,
        solve_prefix_recipe,
        system_text,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import read_process_cpu, summarize_process_cpu
    from e5b_ingest import reference_predictions
    from e9c_probe import (
        load_object,
        post_json,
        render_tokens,
        solve_prefix_recipe,
        system_text,
    )


LETTERS = ("A", "B", "C", "D")


def extract_candidate_distribution(
    response: dict[str, Any],
    *,
    expected_candidates: tuple[str, ...] = LETTERS,
) -> dict[str, float]:
    completion = response.get("completion_probabilities")
    if not isinstance(completion, list) or len(completion) != 1:
        raise ValueError("completion response lacks one probability entry")
    first = completion[0]
    top = first.get("top_probs") if isinstance(first, dict) else None
    if not isinstance(top, list) or not top:
        raise ValueError("completion response lacks post-sampling probabilities")

    allowed = set(expected_candidates)
    distribution = {candidate: 0.0 for candidate in expected_candidates}
    for item in top:
        if not isinstance(item, dict):
            raise TypeError("candidate probability is not an object")
        raw_bytes = item.get("bytes")
        probability = item.get("prob")
        if (
            not isinstance(raw_bytes, list)
            or any(
                type(value) is not int or not 0 <= value <= 255 for value in raw_bytes
            )
            or not isinstance(probability, (int, float))
            or not math.isfinite(probability)
            or probability < 0
        ):
            raise ValueError("candidate probability entry is invalid")
        try:
            candidate = bytes(raw_bytes).decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("candidate bytes are not UTF-8") from error
        if candidate not in allowed:
            raise ValueError(f"grammar leaked non-candidate token {candidate!r}")
        distribution[candidate] += float(probability)

    if any(probability <= 0 for probability in distribution.values()):
        raise ValueError("candidate distribution does not cover A/B/C/D")
    if not math.isclose(sum(distribution.values()), 1.0, abs_tol=1e-5):
        raise ValueError("candidate probabilities do not sum to one")
    return distribution


def ranked_candidates(distribution: dict[str, float]) -> list[dict[str, Any]]:
    return [
        {"candidate": candidate, "probability": probability}
        for candidate, probability in sorted(
            distribution.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def request_candidate_scores(
    origin: str,
    *,
    index: int,
    task: dict[str, Any],
    marker: str,
    marker_index: int,
    prompt_tokens: list[int],
    reference: str,
    cache_prompt: bool,
    scoring: dict[str, Any],
    seed: int,
    timeout: float,
) -> dict[str, Any]:
    started = time.perf_counter_ns()
    response: dict[str, Any] | None = None
    try:
        status, response = post_json(
            origin,
            "/completion",
            {
                "prompt": prompt_tokens,
                "n_predict": scoring["maximum_output_tokens"],
                "temperature": scoring["temperature"],
                "samplers": scoring["samplers"],
                "seed": seed,
                "grammar": scoring["grammar"],
                "n_probs": scoring["n_probs"],
                "post_sampling_probs": True,
                "return_tokens": True,
                "cache_prompt": cache_prompt,
                "stream": False,
            },
            timeout,
        )
        http_ms = (time.perf_counter_ns() - started) / 1_000_000
        if status != 200:
            raise ValueError(f"/completion returned HTTP {status}")
        distribution = extract_candidate_distribution(response)
        ranking = ranked_candidates(distribution)
        timings = response.get("timings")
        timings = timings if isinstance(timings, dict) else {}
        sampled = response.get("content")
        sampled_prediction = sampled if sampled in LETTERS else None
        prediction = ranking[0]["candidate"]
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
            "sampled_response": sampled,
            "sampled_tokens": response.get("tokens"),
            "sampled_prediction": sampled_prediction,
            "prediction": prediction,
            "reference_match": prediction == reference,
            "candidate_probabilities": distribution,
            "candidate_ranking": ranking,
            "top1_margin": ranking[0]["probability"] - ranking[1]["probability"],
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
    except (OSError, TypeError, ValueError) as error:
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
            "sampled_response": None,
            "sampled_tokens": None,
            "sampled_prediction": None,
            "prediction": None,
            "reference_match": False,
            "candidate_probabilities": None,
            "candidate_ranking": None,
            "top1_margin": None,
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
            "raw_response": response,
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
            "top1_margin",
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
    if contract.get("experiment_id") != "E10a":
        raise ValueError("unsupported contract")
    workload = contract["workload"]
    construction = contract["prompt_construction"]
    scoring = contract["candidate_scoring"]
    if args.prefix_cardinality not in workload["prefix_cardinalities"]:
        raise ValueError("prefix cardinality differs from the contract")
    if args.shared_prefix_tokens not in workload["shared_prefix_tokens"]:
        raise ValueError("shared-prefix length differs from the contract")
    if args.repetition not in set(workload["repetitions"]):
        raise ValueError("repetition differs from the contract")

    task_by_id = {task["id"]: task for task in tasks_manifest["tasks"]}
    measured_tasks = [task_by_id[task_id] for task_id in workload["task_ids"]]
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
    required_task_ids = sorted(set(workload["task_ids"] + [workload["warmup_task_id"]]))
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
            request_candidate_scores(
                args.url,
                index=index,
                task=warmup_task,
                marker=marker,
                marker_index=index,
                prompt_tokens=prompt_map[(marker, warmup_task["id"])],
                reference=references[warmup_task["id"]],
                cache_prompt=cache_prompt,
                scoring=scoring,
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
            request_candidate_scores(
                args.url,
                index=index,
                task=task,
                marker=marker,
                marker_index=marker_index,
                prompt_tokens=prompt_map[(marker, task["id"])],
                reference=references[task["id"]],
                cache_prompt=cache_prompt,
                scoring=scoring,
                seed=workload["seed"],
                timeout=workload["timeout_seconds"],
            )
        )
    elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
    cpu_after = read_process_cpu(args.server_pid)
    process_cpu = summarize_process_cpu(
        cpu_before,
        cpu_after,
        clock_ticks_per_second=clock_ticks,
        measured_requests=len(cases),
        elapsed_seconds=elapsed,
    )
    failures = sum(
        case["http_status"] != 200 or case["error"] is not None for case in cases
    )
    warmup_failures = sum(
        case["http_status"] != 200 or case["error"] is not None for case in warmups
    )
    mismatches = sum(not case["reference_match"] for case in cases)
    output: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": "E10a",
        "parameters": {
            "prefix_cardinality": args.prefix_cardinality,
            "shared_prefix_tokens": args.shared_prefix_tokens,
            "cache_prompt": cache_prompt,
            "repetition": args.repetition,
            "measured_requests": len(cases),
            "client_concurrency": workload["client_concurrency"],
            "seed": workload["seed"],
            "candidate_scoring": scoring,
            "server_pid": args.server_pid,
        },
        "prefix_recipe": recipe,
        "warmups": warmups,
        "cases": cases,
        "process_cpu": process_cpu,
    }
    if failures or warmup_failures:
        output["result"] = {
            "elapsed_seconds": elapsed,
            "requests_per_second": len(cases) / elapsed,
            "failures": failures,
            "warmup_failures": warmup_failures,
            "reference_prediction_mismatches": mismatches,
            "error_messages": sorted(
                {
                    case["error"]
                    for case in [*warmups, *cases]
                    if case.get("error") is not None
                }
            ),
        }
        args.output.write_text(
            json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 1

    require_measured_cases(cases)
    output["result"] = {
        "elapsed_seconds": elapsed,
        "requests_per_second": len(cases) / elapsed,
        "failures": failures,
        "reference_prediction_mismatches": mismatches,
        "http_ms": summarize([float(case["http_ms"]) for case in cases]),
        "encode_ms": summarize([float(case["encode_ms"]) for case in cases]),
        "decode_ms": summarize([float(case["decode_ms"]) for case in cases]),
        "cached_tokens": summarize([float(case["cached_tokens"]) for case in cases]),
        "evaluated_prompt_tokens": summarize(
            [float(case["evaluated_prompt_tokens"]) for case in cases]
        ),
        "prompt_tokens": summarize([float(case["prompt_tokens"]) for case in cases]),
        "top1_margin": summarize([float(case["top1_margin"]) for case in cases]),
    }
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
