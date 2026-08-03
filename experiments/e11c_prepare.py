#!/usr/bin/env python3
"""Prepare the pinned E11c sealed holdout for exact serial scoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from experiments.e10d_prepare import prepare_task, remote_tokenize, text_sha256
    from experiments.e11c_samples import sample_map
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e10d_prepare import prepare_task, remote_tokenize, text_sha256
    from e11c_samples import sample_map


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
    expected_tasks = holdout["task_order"]
    selected = sample_map()
    if (
        plan.get("experiment_id") != "E11c-plan"
        or args.max_length != holdout["max_length"]
        or args.seed != holdout["seed"]
        or set(selected) != set(expected_tasks)
        or any(
            len(indices) != holdout["samples_per_task"] for indices in selected.values()
        )
    ):
        raise ValueError("requested preparation differs from the frozen E11c holdout")

    tokenizer_plan = plan["tokenizer"]
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_plan["repository"],
        revision=tokenizer_plan["revision"],
        use_fast=True,
        fix_mistral_regex=tokenizer_plan["fix_mistral_regex"],
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
        "experiment_id": "E11c",
        "harness": plan["harness"],
        "tokenizer": tokenizer_plan,
        "max_length": args.max_length,
        "fewshot": holdout["fewshot"],
        "apply_chat_template": holdout["apply_chat_template"],
        "fewshot_as_multiturn": holdout["fewshot_as_multiturn"],
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
    if output["summary"] != holdout["expected_summary"]:
        raise ValueError("prepared E11c summary differs from the frozen shape")
    for task in tasks:
        expected = holdout["task_shapes"][task["task"]]
        candidate_lengths = [
            len(request["candidate_tokens"])
            for sample in task["samples"]
            for request in sample["requests"]
        ]
        if (
            task["sample_count"] != expected["samples"]
            or task["choice_count"] != expected["choices"]
            or task["token_score_requests"] != expected["token_score_requests"]
            or min(candidate_lengths) != expected["minimum_candidate_tokens"]
            or max(candidate_lengths) != expected["maximum_candidate_tokens"]
        ):
            raise ValueError(f"prepared {task['task']} shape differs")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
