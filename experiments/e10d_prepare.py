#!/usr/bin/env python3
"""Prepare the pinned E9b external holdout for exact E10d scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

try:
    from experiments.e9b_samples import sample_map
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e9b_samples import sample_map


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def tokens_sha256(tokens: list[int]) -> str:
    return hashlib.sha256(
        json.dumps(tokens, separators=(",", ":")).encode()
    ).hexdigest()


def object_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def post_json(
    session: Any,
    url: str,
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    response = session.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise TypeError(f"{url} returned a non-object")
    return value


def remote_tokenize(
    session: Any,
    base_url: str,
    text: str,
    timeout: float,
) -> list[int]:
    value = post_json(
        session,
        f"{base_url}/tokenize",
        {"content": text, "add_special": False, "parse_special": True},
        timeout,
    ).get("tokens")
    if not isinstance(value, list) or any(not isinstance(item, int) for item in value):
        raise TypeError("/tokenize returned invalid token IDs")
    return value


def move_context_spaces(context: str, continuation: str) -> tuple[str, str]:
    spaces = len(context) - len(context.rstrip())
    if spaces:
        return context[:-spaces], context[-spaces:] + continuation
    return context, continuation


def gold_index(task: Any, document: dict[str, Any], choices: list[str]) -> int:
    target = (
        task.doc_to_text(document)
        if task.multiple_input
        else task.doc_to_target(document)
    )
    if isinstance(target, int):
        result = target
    elif isinstance(target, str) and target in choices:
        result = choices.index(target)
    else:
        raise ValueError(f"unsupported target {target!r}")
    if not 0 <= result < len(choices):
        raise ValueError("gold choice index is out of range")
    return result


def prepare_request(
    *,
    context: str,
    continuation: str,
    choice_index: int,
    tokenizer: Any,
    tokenize: Callable[[str], list[int]],
    max_length: int,
) -> dict[str, Any]:
    context, continuation = move_context_spaces(context, continuation)
    local_context = tokenizer.encode(context, add_special_tokens=False)
    local_whole = tokenizer.encode(context + continuation, add_special_tokens=False)
    remote_context = tokenize(context)
    remote_whole = tokenize(context + continuation)
    if local_context != remote_context or local_whole != remote_whole:
        raise ValueError("pinned tokenizer and llama.cpp token IDs differ")
    if len(local_whole) < len(local_context):
        raise ValueError("continuation token boundary is invalid")

    continuation_tokens = local_whole[len(local_context) :]
    if not continuation_tokens:
        raise ValueError("holdout choice has no continuation tokens")
    combined = (local_context + continuation_tokens)[-max_length:]
    truncated = max(0, len(local_context) + len(continuation_tokens) - max_length)
    context_length = len(local_context) - truncated
    if context_length <= 0:
        raise ValueError("holdout continuation displaced the complete context")
    prompt_tokens = combined[:context_length]
    candidate_tokens = combined[context_length:]
    if candidate_tokens != continuation_tokens:
        raise ValueError("holdout truncation changed continuation tokens")

    return {
        "choice_index": choice_index,
        "context_text_sha256": text_sha256(context),
        "continuation_text_sha256": text_sha256(continuation),
        "joined_text_sha256": text_sha256(context + continuation),
        "original_context_tokens": len(local_context),
        "continuation_tokens": len(continuation_tokens),
        "left_truncated_tokens": truncated,
        "prompt_tokens": prompt_tokens,
        "prompt_sha256": tokens_sha256(prompt_tokens),
        "candidate_tokens": candidate_tokens,
        "candidate_sha256": tokens_sha256(candidate_tokens),
        "input_tokens": len(combined),
    }


def prepare_task(
    *,
    task_name: str,
    task: Any,
    selected_indices: list[int],
    tokenizer: Any,
    chat_template: Callable[..., str],
    tokenize: Callable[[str], list[int]],
    max_length: int,
    seed: int,
) -> dict[str, Any]:
    task.set_config(key="num_fewshot", value=0)
    task.set_fewshot_seed(seed=seed)
    task.build_all_requests(
        samples=selected_indices,
        apply_chat_template=True,
        fewshot_as_multiturn=False,
        chat_template=chat_template,
        tokenizer_name=tokenizer.name_or_path,
    )

    instances: dict[int, list[Any]] = defaultdict(list)
    for instance in task.instances:
        if instance.request_type != "loglikelihood":
            raise ValueError(f"{task_name} produced a non-loglikelihood request")
        instances[instance.doc_id].append(instance)
    if sorted(instances) != list(range(len(selected_indices))):
        raise ValueError(f"{task_name} request document order differs")

    samples: list[dict[str, Any]] = []
    choice_count = 0
    token_score_requests = 0
    for ordinal, source_index in enumerate(selected_indices):
        current = sorted(instances[ordinal], key=lambda item: item.idx)
        document = current[0].doc
        if any(item.doc != document for item in current):
            raise ValueError(f"{task_name} request documents differ within a sample")
        choices = task.doc_to_choice(document)
        if (
            not isinstance(choices, list)
            or not 2 <= len(choices) <= 4
            or any(not isinstance(choice, str) or not choice for choice in choices)
            or [item.idx for item in current] != list(range(len(choices)))
        ):
            raise ValueError(f"{task_name} produced invalid choice requests")

        requests_for_sample = [
            prepare_request(
                context=item.args[0],
                continuation=item.args[1],
                choice_index=item.idx,
                tokenizer=tokenizer,
                tokenize=tokenize,
                max_length=max_length,
            )
            for item in current
        ]
        samples.append(
            {
                "sample_ordinal": ordinal,
                "source_index": source_index,
                "source_document_sha256": object_sha256(document),
                "gold_index": gold_index(task, document, choices),
                "choice_text_lengths": [len(choice) for choice in choices],
                "choice_text_bytes": [len(choice.encode()) for choice in choices],
                "requests": requests_for_sample,
            }
        )
        choice_count += len(choices)
        token_score_requests += sum(
            len(request["candidate_tokens"]) for request in requests_for_sample
        )

    return {
        "task": task_name,
        "metrics": list(task._metric_fn_list),
        "samples": samples,
        "sample_count": len(samples),
        "choice_count": choice_count,
        "serial_candidate_requests": choice_count,
        "token_score_requests": token_score_requests,
    }


def main() -> int:
    import requests
    from lm_eval.tasks import TaskManager
    from transformers import AutoTokenizer

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--include-path", type=Path, required=True)
    parser.add_argument("--max-length", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--skip-remote-parity", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text())
    holdout = plan["planned_holdout"]
    expected_tasks = [item["task"] for item in holdout["tasks"]]
    selected = sample_map()
    if (
        args.max_length != holdout["max_length"]
        or args.seed != 424242
        or list(selected) != expected_tasks
        or any(
            len(indices) != holdout["samples_per_task"] for indices in selected.values()
        )
    ):
        raise ValueError("requested preparation differs from the frozen E9b holdout")

    tokenizer = AutoTokenizer.from_pretrained(
        plan["tokenizer"]["repository"],
        revision=plan["tokenizer"]["revision"],
        use_fast=True,
        fix_mistral_regex=plan["tokenizer"]["fix_mistral_regex"],
    )

    def chat_template(
        messages: list[dict[str, str]], add_generation_prompt: bool = True
    ) -> str:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
            continue_final_message=not add_generation_prompt,
        )

    if not args.skip_remote_parity and not args.base_url:
        raise ValueError("--base-url is required unless --skip-remote-parity is set")

    session = requests.Session()
    token_cache: dict[str, list[int]] = {}

    def tokenize(text: str) -> list[int]:
        digest = text_sha256(text)
        if digest not in token_cache:
            token_cache[digest] = (
                tokenizer.encode(text, add_special_tokens=False)
                if args.skip_remote_parity
                else remote_tokenize(session, args.base_url, text, args.timeout)
            )
        return token_cache[digest]

    manager = TaskManager(include_path=args.include_path)
    tasks = []
    for task_name in expected_tasks:
        loaded = manager.load(task_name)["tasks"]
        if list(loaded) != [task_name]:
            raise ValueError(f"{task_name} did not resolve to exactly one task")
        tasks.append(
            prepare_task(
                task_name=task_name,
                task=loaded[task_name],
                selected_indices=selected[task_name],
                tokenizer=tokenizer,
                chat_template=chat_template,
                tokenize=tokenize,
                max_length=args.max_length,
                seed=args.seed,
            )
        )

    output = {
        "schema_version": 1,
        "experiment_id": "E10d",
        "harness": plan["harness"],
        "tokenizer": plan["tokenizer"],
        "max_length": args.max_length,
        "fewshot": 0,
        "apply_chat_template": True,
        "fewshot_as_multiturn": False,
        "seed": args.seed,
        "tokenizer_parity_checked": not args.skip_remote_parity,
        "task_order": expected_tasks,
        "tasks": tasks,
        "summary": {
            "samples": sum(task["sample_count"] for task in tasks),
            "choices": sum(task["choice_count"] for task in tasks),
            "serial_candidate_requests": sum(
                task["serial_candidate_requests"] for task in tasks
            ),
            "token_score_requests": sum(task["token_score_requests"] for task in tasks),
            "unique_tokenized_texts": len(token_cache),
            "tokenizer_parity_mismatches": 0,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
