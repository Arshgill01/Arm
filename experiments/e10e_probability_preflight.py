#!/usr/bin/env python3
"""Probe the exact E10d failures with optional safe-token sampling."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

try:
    from experiments.e10c_probe import post_raw_json, retain_raw
    from experiments.e9c_probe import load_object
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e10c_probe import post_raw_json, retain_raw
    from e9c_probe import load_object


def parse_case(value: str) -> tuple[str, int, int]:
    parts = value.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("case must be task:sample_ordinal:choice")
    try:
        sample = int(parts[1])
        choice = int(parts[2])
    except ValueError as error:
        raise argparse.ArgumentTypeError("case ordinals must be integers") from error
    if sample < 0 or choice < 0:
        raise argparse.ArgumentTypeError("case ordinals must be nonnegative")
    return parts[0], sample, choice


def selected_probability(response: dict[str, Any], target: int) -> dict[str, Any]:
    probabilities = response.get("completion_probabilities")
    if not isinstance(probabilities, list) or len(probabilities) != 1:
        return {
            "status": "missing_probability_entry",
            "probability_entry_count": len(probabilities)
            if isinstance(probabilities, list)
            else None,
            "selected_token_id": None,
            "selected_logprob": None,
        }
    entry = probabilities[0]
    selected = entry.get("selected_logprobs") if isinstance(entry, dict) else None
    item = selected[0] if isinstance(selected, list) and len(selected) == 1 else None
    logprob = item.get("logprob") if isinstance(item, dict) else None
    if (
        not isinstance(item, dict)
        or item.get("id") != target
        or not isinstance(logprob, (int, float))
        or not math.isfinite(logprob)
    ):
        return {
            "status": "invalid_selected_probability",
            "probability_entry_count": 1,
            "selected_token_id": item.get("id") if isinstance(item, dict) else None,
            "selected_logprob": logprob,
        }
    return {
        "status": "ok",
        "probability_entry_count": 1,
        "selected_token_id": target,
        "selected_logprob": float(logprob),
    }


def select_request(
    prepared: dict[str, Any], case: tuple[str, int, int]
) -> tuple[dict[str, Any], dict[str, Any]]:
    task_name, sample_ordinal, choice_index = case
    selected = [
        item
        for item in prepared["cases"]
        if (
            item["task"],
            item["sample_ordinal"],
            item["choice_index"],
        )
        == (task_name, sample_ordinal, choice_index)
    ]
    if len(selected) != 1:
        raise ValueError("E10e failure-case selection differs")
    item = selected[0]
    return item, item


def run_case(
    *,
    base_url: str,
    prepared: dict[str, Any],
    case: tuple[str, int, int],
    forced_safe_token_id: int | None,
    forced_safe_logit_bias: float | None,
    seed: int,
    timeout: float,
    raw_dir: Path,
) -> dict[str, Any]:
    sample, request = select_request(prepared, case)
    task_name, sample_ordinal, choice_index = case
    prefix = list(request["prompt_tokens"])
    attempts = []
    for token_index, target in enumerate(request["candidate_tokens"]):
        body: dict[str, Any] = {
            "prompt": prefix,
            "n_predict": 1,
            "temperature": 0.0,
            "seed": seed,
            "cache_prompt": token_index > 0,
            "stream": False,
            "return_tokens": True,
            "n_probs": 0,
            "probability_ids": [target],
            "post_sampling_probs": False,
        }
        if forced_safe_token_id is not None:
            body["logit_bias"] = [
                [forced_safe_token_id, forced_safe_logit_bias]
            ]
        started = time.perf_counter_ns()
        status, raw, response, elapsed_ms = post_raw_json(
            base_url, "/completion", body, timeout
        )
        client_elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        raw_record = retain_raw(
            raw_dir
            / (
                f"{task_name}-{sample_ordinal:03d}-c{choice_index:02d}"
                f"-t{token_index:03d}.json.gz"
            ),
            raw,
        )
        probability = selected_probability(response, target)
        timings = response.get("timings")
        generated = response.get("tokens")
        attempts.append(
            {
                "token_index": token_index,
                "target_token_id": target,
                "http_status": status,
                "http_ms": elapsed_ms,
                "client_elapsed_ms": client_elapsed_ms,
                "cache_n": timings.get("cache_n")
                if isinstance(timings, dict)
                else None,
                "generated_tokens": generated,
                "raw_response": raw_record,
                **probability,
            }
        )
        if status != 200 or probability["status"] != "ok":
            break
        prefix.append(target)
    return {
        "task": task_name,
        "sample_ordinal": sample_ordinal,
        "source_index": sample["source_index"],
        "choice_index": choice_index,
        "candidate_tokens": request["candidate_tokens"],
        "attempts": attempts,
        "completed": len(attempts) == len(request["candidate_tokens"])
        and all(attempt["status"] == "ok" for attempt in attempts),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--case", type=parse_case, action="append", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--forced-safe-token-id", type=int)
    parser.add_argument("--forced-safe-logit-bias", type=float)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        args.server_pid <= 0
        or args.seed < 0
        or args.timeout <= 0
        or (args.forced_safe_token_id is not None and args.forced_safe_token_id < 0)
        or (args.forced_safe_token_id is None)
        is not (args.forced_safe_logit_bias is None)
        or (
            args.forced_safe_logit_bias is not None
            and (
                not math.isfinite(args.forced_safe_logit_bias)
                or args.forced_safe_logit_bias <= 0
            )
        )
    ):
        raise ValueError("E10e numeric parameters differ")
    prepared = load_object(args.prepared)
    if (
        prepared.get("schema_version") != 1
        or prepared.get("experiment_id") != "E10e-failure-cases"
        or prepared.get("source_e10d_prepared_sha256") is None
        or not isinstance(prepared.get("cases"), list)
        or not prepared["cases"]
    ):
        raise ValueError("E10e prepared workload differs")
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    cases = [
        run_case(
            base_url=args.base_url,
            prepared=prepared,
            case=case,
            forced_safe_token_id=args.forced_safe_token_id,
            forced_safe_logit_bias=args.forced_safe_logit_bias,
            seed=args.seed,
            timeout=args.timeout,
            raw_dir=args.raw_dir,
        )
        for case in args.case
    ]
    output = {
        "schema_version": 1,
        "experiment_id": "E10e-preflight",
        "variant": args.variant,
        "forced_safe_token_id": args.forced_safe_token_id,
        "forced_safe_logit_bias": args.forced_safe_logit_bias,
        "model": args.model,
        "model_sha256": args.model_sha256,
        "server_pid": args.server_pid,
        "parameters": {
            "seed": args.seed,
            "timeout": args.timeout,
            "cache_prompt_policy": "false for the first token of each case; true only for later tokens",
            "probability_distribution": "raw pre-sampling selected token log probability",
        },
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"variant": args.variant, "cases": len(cases)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
