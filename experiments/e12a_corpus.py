#!/usr/bin/env python3
"""Build the frozen E12a application-conditioned imatrix corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e9b_tasks.e9b_utils import _clean_hellaswag
    from experiments.e12a_samples import sample_map
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e9b_tasks.e9b_utils import _clean_hellaswag
    from e12a_samples import sample_map


LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
APPLICATION_REPETITIONS = 8
ORDER_SALT = "pareto64-e12a-imatrix-record-order-v1"


def render_multiple_choice(question: str, choices: list[str]) -> str:
    lines = [question]
    lines.extend(f"{LETTERS[index]}. {choice}" for index, choice in enumerate(choices))
    return "\n".join(lines)


def application_records(tasks: dict[str, Any]) -> list[dict[str, str]]:
    instruction = tasks["instruction"]
    records = []
    for repetition in range(APPLICATION_REPETITIONS):
        for task in tasks["tasks"]:
            records.append(
                {
                    "source": "application",
                    "source_id": f"application:{task['id']}:r{repetition + 1}",
                    "system": instruction,
                    "user": task["prompt"],
                    "assistant": task["answer"],
                }
            )
    return records


def arc_record(row: dict[str, Any], index: int) -> dict[str, str]:
    labels = row["choices"]["label"]
    texts = row["choices"]["text"]
    answer = labels.index(row["answerKey"])
    return {
        "source": "arc_easy_train",
        "source_id": f"arc_easy_train:{index}",
        "system": "Choose the correct option. Respond with only one uppercase letter.",
        "user": render_multiple_choice(row["question"], texts),
        "assistant": LETTERS[answer],
    }


def hellaswag_record(row: dict[str, Any], index: int) -> dict[str, str]:
    context = row["ctx_a"] + " " + row["ctx_b"].capitalize()
    query = _clean_hellaswag(row["activity_label"] + ": " + context)
    choices = [_clean_hellaswag(value) for value in row["endings"]]
    return {
        "source": "hellaswag_train",
        "source_id": f"hellaswag_train:{index}",
        "system": "Choose the most plausible continuation. Respond with only one uppercase letter.",
        "user": render_multiple_choice(query, choices),
        "assistant": LETTERS[int(row["label"])],
    }


def winogrande_record(row: dict[str, Any], index: int) -> dict[str, str]:
    choices = [row["option1"], row["option2"]]
    return {
        "source": "winogrande_train",
        "source_id": f"winogrande_train:{index}",
        "system": "Choose the option that correctly fills the blank. Respond with only one uppercase letter.",
        "user": render_multiple_choice(row["sentence"], choices),
        "assistant": LETTERS[int(row["answer"]) - 1],
    }


def rank_record(record: dict[str, str]) -> bytes:
    return hashlib.sha256(f"{ORDER_SALT}\0{record['source_id']}".encode()).digest()


def main() -> int:
    from datasets import load_dataset
    from transformers import AutoTokenizer

    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if plan.get("experiment_id") != "E12a":
        raise ValueError("corpus plan does not identify E12a")
    selected = sample_map()
    records = application_records(json.loads(args.tasks.read_text()))
    datasets = {}
    for item in plan["calibration"]["datasets"]:
        dataset = load_dataset(
            item["repository"],
            item.get("configuration"),
            revision=item["revision"],
            split=item["split"],
        )
        if len(dataset) != item["split_size"]:
            raise ValueError(f"{item['name']} split size differs")
        datasets[item["name"]] = dataset
    builders = {
        "arc_easy_train": arc_record,
        "hellaswag_train": hellaswag_record,
        "winogrande_train": winogrande_record,
    }
    for name, indices in selected.items():
        records.extend(
            builders[name](datasets[name][index], index) for index in indices
        )
    records.sort(key=rank_record)

    tokenizer_plan = plan["tokenizer"]
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_plan["repository"],
        revision=tokenizer_plan["revision"],
        use_fast=True,
        fix_mistral_regex=tokenizer_plan["fix_mistral_regex"],
    )
    rendered = []
    token_counts = []
    for record in records:
        text = tokenizer.apply_chat_template(
            [
                {"role": "system", "content": record["system"]},
                {"role": "user", "content": record["user"]},
                {"role": "assistant", "content": record["assistant"]},
            ],
            tokenize=False,
            add_generation_prompt=False,
            enable_thinking=False,
        )
        rendered.append(text)
        token_counts.append(len(tokenizer.encode(text, add_special_tokens=False)))
    corpus = "\n".join(rendered) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(corpus, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "experiment_id": "E12a-corpus",
        "records": len(records),
        "source_counts": {
            source: sum(record["source"] == source for record in records)
            for source in sorted({record["source"] for record in records})
        },
        "record_order": [record["source_id"] for record in records],
        "record_sha256": [
            hashlib.sha256(
                json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            for record in records
        ],
        "rendered_token_count_sum": sum(token_counts),
        "minimum_record_tokens": min(token_counts),
        "maximum_record_tokens": max(token_counts),
        "corpus_bytes": len(corpus.encode()),
        "corpus_sha256": hashlib.sha256(corpus.encode()).hexdigest(),
        "tokenizer": tokenizer_plan,
        "selection_uses_labels": False,
        "selection_uses_model_outputs": False,
    }
    expected = plan["calibration"]["expected_corpus"]
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"generated E12a corpus {key} differs")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: manifest[key]
                for key in (
                    "records",
                    "source_counts",
                    "rendered_token_count_sum",
                    "corpus_sha256",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
