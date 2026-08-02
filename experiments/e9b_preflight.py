#!/usr/bin/env python3
"""Preflight llama.cpp completion logprobs and the pinned E9b tokenizer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import requests
from transformers import AutoTokenizer


TOKENIZER_PROBES = (
    "Question: Water freezes at what temperature?\nAnswer:",
    " A",
    "A",
    "don't shouldn't I'm",
    "A person opens the door — then pauses.",
    "Which option is physically possible?\nAnswer:",
    "The trophy doesn't fit in the suitcase because it is too large.",
    "éclair naïve résumé",
    "[INST] Question: Which option is correct?\nAnswer: [/INST]",
)


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise TypeError(f"{url} did not return an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--tokenizer-repository", required=True)
    parser.add_argument("--tokenizer-revision", required=True)
    parser.add_argument("--tokenizer-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(
        args.tokenizer_repository,
        revision=args.tokenizer_revision,
        use_fast=True,
        fix_mistral_regex=True,
    )
    parity: list[dict[str, Any]] = []
    for text in TOKENIZER_PROBES:
        local = tokenizer.encode(text, add_special_tokens=False)
        remote = post_json(
            f"{args.base_url}/tokenize",
            {"content": text, "add_special": False, "parse_special": True},
        ).get("tokens")
        if local != remote:
            raise ValueError(f"tokenizer mismatch for probe {text!r}")
        parity.append(
            {
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "token_count": len(local),
                "tokens": local,
            }
        )

    args.tokenizer_output.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(args.tokenizer_output)
    reloaded = AutoTokenizer.from_pretrained(args.tokenizer_output, use_fast=True)
    for text in TOKENIZER_PROBES:
        if reloaded.encode(text, add_special_tokens=False) != tokenizer.encode(
            text, add_special_tokens=False
        ):
            raise ValueError("saved tokenizer snapshot changed token IDs")

    context = "Question: Water freezes at what temperature?\nAnswer:"
    continuation = " A"
    context_tokens = tokenizer.encode(context, add_special_tokens=False)
    continuation_tokens = tokenizer.encode(continuation, add_special_tokens=False)
    prompt = context_tokens + continuation_tokens
    completion = post_json(
        f"{args.base_url}/v1/completions",
        {
            "model": "ministral3_3b_q4_k_m",
            "prompt": prompt,
            "temperature": 0,
            "max_tokens": 1,
            "logprobs": 1,
            "seed": 424242,
            "echo": True,
        },
    )
    choices = completion.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("completion response did not contain one choice")
    logprobs = choices[0].get("logprobs")
    if not isinstance(logprobs, dict):
        raise ValueError("completion response omitted logprobs")
    token_logprobs = logprobs.get("token_logprobs")
    top_logprobs = logprobs.get("top_logprobs")
    expected_length = len(prompt) + 1
    if (
        not isinstance(token_logprobs, list)
        or len(token_logprobs) != expected_length
        or token_logprobs[len(context_tokens)] is None
        or not isinstance(top_logprobs, list)
        or len(top_logprobs) != expected_length
        or not isinstance(top_logprobs[len(context_tokens)], dict)
    ):
        raise ValueError("completion logprob shape is incompatible with lm-eval")

    tokenizer_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(args.tokenizer_output.iterdir())
        if path.is_file()
    }
    result = {
        "schema_version": 1,
        "status": "compatible",
        "tokenizer": {
            "repository": args.tokenizer_repository,
            "revision": args.tokenizer_revision,
            "fix_mistral_regex": True,
            "saved_file_sha256": tokenizer_hashes,
        },
        "token_parity": parity,
        "completion_logprobs": {
            "prompt_tokens": len(prompt),
            "context_tokens": len(context_tokens),
            "continuation_tokens": len(continuation_tokens),
            "response_token_entries": len(token_logprobs),
            "continuation_logprob_present": True,
            "continuation_top_logprobs_present": True,
        },
    }
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
