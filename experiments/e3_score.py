#!/usr/bin/env python3
"""Validate and score the predeclared E3 deterministic quality runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ANSWER_PATTERN = re.compile(r"(?<![A-Z])([A-D])(?![A-Z])")
EXPECTED_REPETITIONS = 2
ABSOLUTE_ACCURACY_FLOOR = 0.75
MAX_TASK_DEFICIT_FROM_BEST = 1


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_answer(response: str) -> str | None:
    match = ANSWER_PATTERN.search(response.upper())
    return match.group(1) if match else None


def load_tasks(path: Path) -> tuple[dict[str, dict[str, str]], str]:
    manifest = load_object(path)
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported E3 task schema")
    raw_tasks = manifest.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("E3 task manifest contains no tasks")
    tasks: dict[str, dict[str, str]] = {}
    for raw_task in raw_tasks:
        if not isinstance(raw_task, dict):
            raise ValueError("every E3 task must be an object")
        task_id = raw_task.get("id")
        category = raw_task.get("category")
        answer = raw_task.get("answer")
        if not isinstance(task_id, str) or task_id in tasks:
            raise ValueError("E3 task IDs must be unique strings")
        if not isinstance(category, str) or answer not in {"A", "B", "C", "D"}:
            raise ValueError(f"invalid E3 task {task_id}")
        tasks[task_id] = {"category": category, "answer": answer}
    return tasks, sha256_file(path)


def score_run(path: Path, tasks: dict[str, dict[str, str]]) -> dict[str, Any]:
    raw = load_object(path)
    if raw.get("schema_version") != 1:
        raise ValueError(f"unsupported quality-run schema in {path}")
    cases = raw.get("cases")
    if not isinstance(cases, list) or len(cases) != len(tasks):
        raise ValueError(f"{path} does not contain every E3 task")

    seen: set[str] = set()
    predictions: dict[str, str | None] = {}
    category_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    scored_cases: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise ValueError(f"invalid quality case in {path}")
        task_id = case["id"]
        if task_id in seen or task_id not in tasks:
            raise ValueError(f"unexpected or duplicate task {task_id} in {path}")
        seen.add(task_id)
        response = case.get("response")
        if not isinstance(response, str):
            raise ValueError(f"task {task_id} has no text response")
        prediction = extract_answer(response)
        expected = tasks[task_id]["answer"]
        correct = prediction == expected
        category = tasks[task_id]["category"]
        category_counts[category][1] += 1
        category_counts[category][0] += int(correct)
        predictions[task_id] = prediction
        scored_cases.append(
            {
                "id": task_id,
                "expected": expected,
                "predicted": prediction,
                "correct": correct,
                "response": response,
            }
        )
    if seen != tasks.keys():
        raise ValueError(f"{path} task IDs do not match the manifest")
    correct_count = sum(item["correct"] for item in scored_cases)
    return {
        "source": str(path),
        "framework": raw.get("framework"),
        "model_path": raw.get("model_path"),
        "correct": correct_count,
        "total": len(tasks),
        "accuracy": correct_count / len(tasks),
        "category_accuracy": {
            category: {
                "correct": counts[0],
                "total": counts[1],
                "accuracy": counts[0] / counts[1],
            }
            for category, counts in sorted(category_counts.items())
        },
        "predictions": predictions,
        "cases": scored_cases,
    }


def build_summary(models_path: Path, tasks_path: Path, evidence_dir: Path) -> dict[str, Any]:
    models = load_object(models_path)
    variants = models.get("variants")
    if not isinstance(variants, dict) or not variants:
        raise ValueError("E3 model manifest contains no variants")
    tasks, tasks_sha256 = load_tasks(tasks_path)

    scored: dict[str, dict[str, Any]] = {}
    for variant, model in variants.items():
        repetitions = [
            score_run(
                evidence_dir
                / "variants"
                / variant
                / f"quality-repeat-{repetition}.json",
                tasks,
            )
            for repetition in range(1, EXPECTED_REPETITIONS + 1)
        ]
        expected_framework = model.get("framework")
        if any(run["framework"] != expected_framework for run in repetitions):
            raise ValueError(f"framework mismatch for {variant}")
        predictions_stable = all(
            run["predictions"] == repetitions[0]["predictions"]
            for run in repetitions[1:]
        )
        scored[variant] = {
            "framework": expected_framework,
            "repetitions": repetitions,
            "predictions_stable": predictions_stable,
            "minimum_correct": min(run["correct"] for run in repetitions),
            "minimum_accuracy": min(run["accuracy"] for run in repetitions),
        }

    best_correct = max(item["minimum_correct"] for item in scored.values())
    for item in scored.values():
        item["absolute_floor_met"] = (
            item["minimum_accuracy"] >= ABSOLUTE_ACCURACY_FLOOR
        )
        item["within_one_task_of_best"] = (
            best_correct - item["minimum_correct"] <= MAX_TASK_DEFICIT_FROM_BEST
        )
        item["quality_eligible"] = (
            item["predictions_stable"]
            and item["absolute_floor_met"]
            and item["within_one_task_of_best"]
        )

    return {
        "schema_version": 1,
        "experiment_id": "E3",
        "tasks": {
            "path": str(tasks_path),
            "sha256": tasks_sha256,
            "count": len(tasks),
        },
        "acceptance_policy": {
            "repetitions": EXPECTED_REPETITIONS,
            "prediction_parser": "first standalone uppercase A-D after case folding",
            "predictions_must_be_stable": True,
            "absolute_accuracy_floor": ABSOLUTE_ACCURACY_FLOOR,
            "maximum_task_deficit_from_best": MAX_TASK_DEFICIT_FROM_BEST,
        },
        "best_minimum_correct": best_correct,
        "variants": scored,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    summary = build_summary(
        arguments.models, arguments.tasks, arguments.evidence_dir
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
