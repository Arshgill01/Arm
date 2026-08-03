#!/usr/bin/env python3
"""Run the synthetic E10d serial log-probability compatibility preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e10c_probe import post_raw_json
    from experiments.e10d_probe import argmax, score_candidate
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e10c_probe import post_raw_json
    from e10d_probe import argmax, score_candidate


def tokenize(
    base_url: str, text: str, *, add_special: bool, timeout: float
) -> list[int]:
    status, _, response, _ = post_raw_json(
        base_url,
        "/tokenize",
        {
            "content": text,
            "add_special": add_special,
            "parse_special": True,
        },
        timeout,
    )
    tokens = response.get("tokens")
    if (
        status != 200
        or not isinstance(tokens, list)
        or any(not isinstance(token, int) for token in tokens)
    ):
        raise ValueError("synthetic tokenization preflight failed")
    return tokens


def token_hash(tokens: list[int]) -> str:
    return hashlib.sha256(
        json.dumps(tokens, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    prompt_text = "Question: Which phrase means four?\nAnswer:"
    candidate_texts = [" exactly four", " certainly five"]
    prompt_tokens = tokenize(
        args.base_url, prompt_text, add_special=True, timeout=args.timeout
    )
    candidates = [
        tokenize(args.base_url, text, add_special=False, timeout=args.timeout)
        for text in candidate_texts
    ]
    if not 0 < len(prompt_tokens) < 128 or any(
        not 2 <= len(candidate) <= 16 for candidate in candidates
    ):
        raise ValueError("synthetic preflight token shape differs")

    repetitions: list[dict[str, Any]] = []
    predictions: list[int] = []
    for repetition in (1, 2):
        results = [
            score_candidate(
                base_url=args.base_url,
                prompt_tokens=prompt_tokens,
                candidate_tokens=candidate,
                seed=args.seed,
                timeout=args.timeout,
                raw_dir=args.raw_dir,
                raw_prefix=f"synthetic-r{repetition}-c{index}",
            )
            for index, candidate in enumerate(candidates)
        ]
        scores = [float(result["sum_logprob"]) for result in results]
        predictions.append(argmax(scores))
        repetitions.append(
            {
                "repetition": repetition,
                "scores": scores,
                "results": results,
            }
        )

    maximum_sum_delta = max(
        abs(first - second)
        for first, second in zip(repetitions[0]["scores"], repetitions[1]["scores"])
    )
    maximum_token_delta = max(
        abs(first - second)
        for first_result, second_result in zip(
            repetitions[0]["results"], repetitions[1]["results"]
        )
        for first, second in zip(
            first_result["token_logprobs"], second_result["token_logprobs"]
        )
    )
    gates = {
        "two_candidates": len(candidates) == 2,
        "multi_token_candidates": all(len(candidate) >= 2 for candidate in candidates),
        "repeat_prediction": predictions[0] == predictions[1],
        "repeat_sum_logprob": maximum_sum_delta <= 0.000001,
        "repeat_token_logprob": maximum_token_delta <= 0.000001,
        "first_request_cache_disabled": all(
            result["cached_tokens"][0] == 0
            for repetition in repetitions
            for result in repetition["results"]
        ),
        "continuation_cache_observed": all(
            all(value > 0 for value in result["cached_tokens"][1:])
            for repetition in repetitions
            for result in repetition["results"]
        ),
        "raw_responses_retained": all(
            len(result["raw_responses"]) == len(candidate)
            for repetition in repetitions
            for result, candidate in zip(repetition["results"], candidates)
        ),
    }
    output = {
        "schema_version": 1,
        "experiment_id": "E10d-preflight",
        "status": "pass" if all(gates.values()) else "fail",
        "parameters": {
            "seed": args.seed,
            "cache_prompt_policy": "false on the first token of each candidate; true on later tokens",
            "probability_field": "selected_logprobs",
            "post_sampling_probabilities": False,
            "sampled_output_used_for_score": False,
        },
        "synthetic_inputs": {
            "prompt_text_sha256": hashlib.sha256(prompt_text.encode()).hexdigest(),
            "candidate_text_sha256": [
                hashlib.sha256(text.encode()).hexdigest() for text in candidate_texts
            ],
            "prompt_tokens": prompt_tokens,
            "prompt_token_sha256": token_hash(prompt_tokens),
            "candidate_tokens": candidates,
            "candidate_token_sha256": [token_hash(tokens) for tokens in candidates],
        },
        "repetitions": repetitions,
        "maximum_repeat_sum_logprob_delta": maximum_sum_delta,
        "maximum_repeat_token_logprob_delta": maximum_token_delta,
        "predictions": predictions,
        "validation": gates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": output["status"],
                "validation": gates,
                "maximum_repeat_sum_logprob_delta": maximum_sum_delta,
                "maximum_repeat_token_logprob_delta": maximum_token_delta,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if output["status"] != "pass":
        raise ValueError("E10d compatibility preflight failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
