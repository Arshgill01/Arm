#!/usr/bin/env python3
"""Run one frozen E10b exact-token probability cell."""

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
    from e9c_probe import (
        load_object,
        post_json,
        render_tokens,
        solve_prefix_recipe,
        system_text,
    )


def get_json(origin: str, path: str, timeout: float) -> tuple[int, dict[str, Any]]:
    parsed = urlsplit(origin)
    connection = http.client.HTTPConnection(
        parsed.hostname, parsed.port, timeout=timeout
    )
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        value = json.loads(response.read())
        if not isinstance(value, dict):
            raise TypeError(f"{path} returned a non-object")
        return response.status, value
    finally:
        connection.close()


def post_raw_json(
    origin: str, path: str, payload: dict[str, Any], timeout: float
) -> tuple[int, bytes, dict[str, Any]]:
    parsed = urlsplit(origin)
    connection = http.client.HTTPConnection(
        parsed.hostname, parsed.port, timeout=timeout
    )
    try:
        connection.request(
            "POST",
            path,
            body=json.dumps(payload, separators=(",", ":")).encode(),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError(f"{path} returned a non-object")
        return response.status, raw, value
    finally:
        connection.close()


def tokenize_candidate(origin: str, text: str, timeout: float) -> int:
    status, response = post_json(
        origin,
        "/tokenize",
        {"content": text, "add_special": False, "parse_special": False},
        timeout,
    )
    tokens = response.get("tokens")
    if (
        status != 200
        or not isinstance(tokens, list)
        or len(tokens) != 1
        or type(tokens[0]) is not int
    ):
        raise ValueError(f"candidate {text!r} is not exactly one token")
    return tokens[0]


def model_vocab_size(origin: str, timeout: float) -> int:
    status, response = get_json(origin, "/v1/models", timeout)
    data = response.get("data")
    if status != 200 or not isinstance(data, list) or len(data) != 1:
        raise ValueError("/v1/models did not return one model")
    meta = data[0].get("meta") if isinstance(data[0], dict) else None
    n_vocab = meta.get("n_vocab") if isinstance(meta, dict) else None
    if type(n_vocab) is not int or n_vocab <= 0:
        raise ValueError("/v1/models omitted n_vocab")
    return n_vocab


def load_prompt_construction(contract: dict[str, Any]) -> dict[str, Any]:
    construction = load_object(Path(contract["inputs"]["e10a_contract_path"]))[
        "prompt_construction"
    ]
    if not isinstance(construction, dict):
        raise TypeError("E10a prompt construction is not an object")
    return construction


def extract_scores(
    response: dict[str, Any], mode: str, candidate_ids: list[int], n_vocab: int
) -> tuple[dict[str, float], int, list[int]]:
    probabilities = response.get("completion_probabilities")
    if not isinstance(probabilities, list) or len(probabilities) != 1:
        raise ValueError("completion response lacks one probability entry")
    entry = probabilities[0]
    if not isinstance(entry, dict):
        raise TypeError("completion probability entry is not an object")
    field = "top_logprobs" if mode == "full_vocab" else "selected_logprobs"
    values = entry.get(field)
    if not isinstance(values, list):
        raise TypeError(f"completion response lacks {field}")
    expected_count = n_vocab if mode == "full_vocab" else len(candidate_ids)
    if len(values) != expected_count:
        raise ValueError(
            f"{field} has {len(values)} entries, expected {expected_count}"
        )

    by_id: dict[int, float] = {}
    order: list[int] = []
    for item in values:
        if not isinstance(item, dict):
            raise TypeError("probability item is not an object")
        token_id = item.get("id")
        logprob = item.get("logprob")
        if (
            type(token_id) is not int
            or not isinstance(logprob, (int, float))
            or not math.isfinite(logprob)
            or token_id in by_id
        ):
            raise ValueError("probability item is invalid or duplicated")
        by_id[token_id] = float(logprob)
        order.append(token_id)
    if any(token_id not in by_id for token_id in candidate_ids):
        raise ValueError("response does not cover every candidate token")
    return (
        {str(token_id): by_id[token_id] for token_id in candidate_ids},
        len(values),
        order,
    )


def request_scores(
    origin: str,
    *,
    mode: str,
    prompt_tokens: list[int],
    candidate_ids: list[int],
    n_vocab: int,
    seed: int,
    timeout: float,
    raw_path: Path | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": prompt_tokens,
        "n_predict": 1,
        "temperature": 0.0,
        "seed": seed,
        "cache_prompt": False,
        "stream": False,
        "return_tokens": True,
        "post_sampling_probs": False,
    }
    if mode == "full_vocab":
        payload["n_probs"] = n_vocab
    elif mode == "selected":
        payload["n_probs"] = 0
        payload["probability_ids"] = candidate_ids
    else:
        raise ValueError(f"unsupported mode {mode}")

    started = time.perf_counter_ns()
    status, raw, response = post_raw_json(origin, "/completion", payload, timeout)
    http_ms = (time.perf_counter_ns() - started) / 1_000_000
    if status != 200:
        raise ValueError(f"/completion returned HTTP {status}")
    scores, probability_entries, returned_order = extract_scores(
        response, mode, candidate_ids, n_vocab
    )
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    raw_record: dict[str, Any] | None = None
    if raw_path is not None:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(compressed)
        raw_record = {
            "path": raw_path.name,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "gzip_bytes": len(compressed),
            "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
        }
    ranking = sorted(
        candidate_ids, key=lambda token_id: (-scores[str(token_id)], token_id)
    )
    timings = response.get("timings")
    timings = timings if isinstance(timings, dict) else {}
    return {
        "http_status": status,
        "mode": mode,
        "prompt_tokens": len(prompt_tokens),
        "prompt_sha256": hashlib.sha256(
            json.dumps(prompt_tokens, separators=(",", ":")).encode()
        ).hexdigest(),
        "candidate_token_ids": candidate_ids,
        "candidate_logprobs": scores,
        "candidate_ranking": ranking,
        "probability_entries": probability_entries,
        "returned_selected_order": returned_order if mode == "selected" else None,
        "sampled_content": response.get("content"),
        "sampled_tokens": response.get("tokens"),
        "response_bytes": len(raw),
        "raw_response": raw_record,
        "http_ms": http_ms,
        "encode_ms": timings.get("prompt_ms"),
        "decode_ms": timings.get("predicted_ms"),
        "cached_tokens": timings.get("cache_n"),
        "evaluated_prompt_tokens": timings.get("prompt_n"),
        "error": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--mode", choices=("full_vocab", "selected"), required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_object(args.contract)
    if contract.get("experiment_id") != "E10b":
        raise ValueError("unsupported contract")
    if {"mode": args.mode, "repetition": args.repetition} not in contract["execution"][
        "cell_order"
    ]:
        raise ValueError("cell differs from the frozen order")
    workload = contract["workload"]
    tasks = load_object(args.tasks)
    task_by_id = {task["id"]: task for task in tasks["tasks"]}
    task = task_by_id[workload["task_id"]]
    construction = load_prompt_construction(contract)
    timeout = float(workload["timeout_seconds"])
    recipe = solve_prefix_recipe(
        args.url,
        workload["shared_prefix_tokens"],
        construction["variant_markers"],
        construction["variant_marker_token_ids"],
        construction["instruction_suffix"],
        task["prompt"],
        timeout,
    )
    system = system_text(
        recipe["common_filler_repetitions"],
        workload["prefix_marker"],
        construction["instruction_suffix"],
    )
    prompt_tokens = render_tokens(args.url, system, task["prompt"], timeout)
    candidate_ids = [
        tokenize_candidate(args.url, candidate, timeout)
        for candidate in workload["candidate_texts"]
    ]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate token IDs are not unique")
    n_vocab = model_vocab_size(args.url, timeout)

    warmup = request_scores(
        args.url,
        mode="selected",
        prompt_tokens=prompt_tokens,
        candidate_ids=candidate_ids,
        n_vocab=n_vocab,
        seed=workload["seed"],
        timeout=timeout,
        raw_path=None,
    )
    clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    cpu_before = read_process_cpu(args.server_pid)
    started = time.perf_counter_ns()
    cases = [
        request_scores(
            args.url,
            mode=args.mode,
            prompt_tokens=prompt_tokens,
            candidate_ids=candidate_ids,
            n_vocab=n_vocab,
            seed=workload["seed"],
            timeout=timeout,
            raw_path=args.raw_dir / f"response-{index}.json.gz",
        )
        for index in range(1, workload["measured_requests_per_cell"] + 1)
    ]
    elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
    cpu_after = read_process_cpu(args.server_pid)
    process_cpu = summarize_process_cpu(
        cpu_before,
        cpu_after,
        clock_ticks_per_second=clock_ticks,
        measured_requests=len(cases),
        elapsed_seconds=elapsed,
    )
    output = {
        "schema_version": 1,
        "experiment_id": "E10b",
        "parameters": {
            "mode": args.mode,
            "repetition": args.repetition,
            "task_id": workload["task_id"],
            "candidate_texts": workload["candidate_texts"],
            "candidate_token_ids": candidate_ids,
            "n_vocab": n_vocab,
            "cache_prompt": False,
            "measured_requests": len(cases),
            "server_pid": args.server_pid,
        },
        "prefix_recipe": recipe,
        "warmup": warmup,
        "cases": cases,
        "process_cpu": process_cpu,
        "result": {
            "elapsed_seconds": elapsed,
            "requests_per_second": len(cases) / elapsed,
            "failures": 0,
            "http_ms": summarize([case["http_ms"] for case in cases]),
            "response_bytes": summarize([case["response_bytes"] for case in cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in cases]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in cases]),
        },
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
