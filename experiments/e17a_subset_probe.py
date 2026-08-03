#!/usr/bin/env python3
"""Run the unchanged E5b request engine with a frozen reference subset."""

from __future__ import annotations

import json
from typing import Any

try:
    from experiments import e5b_inference_probe as base
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    import e5b_inference_probe as base


def select_reference_subset(
    tasks: dict[str, Any], full_reference: dict[str, str]
) -> dict[str, str]:
    """Select only the already-frozen E17a task IDs in their frozen order."""
    task_ids = [item["id"] for item in tasks.get("tasks", [])]
    if len(task_ids) != len(set(task_ids)) or any(
        task_id not in full_reference for task_id in task_ids
    ):
        raise ValueError("E17a task subset is not uniquely covered by the stable reference")
    return {task_id: full_reference[task_id] for task_id in task_ids}


def main() -> int:
    arguments = base.parse_args()
    tasks = base.load_object(arguments.tasks)
    full_reference = base.load_reference_predictions(
        base.load_object(arguments.reference_manifest),
        arguments.candidate,
    )
    subset_reference = select_reference_subset(tasks, full_reference)
    evidence = base.run_probe(
        base_url=arguments.url,
        tasks_manifest=tasks,
        reference_predictions=subset_reference,
        candidate=arguments.candidate,
        configuration=arguments.configuration,
        repetition=arguments.repetition,
        warmup_task_ids=arguments.warmup_task,
        concurrency=arguments.concurrency,
        max_output_tokens=arguments.max_output_tokens,
        seed=arguments.seed,
        timeout=arguments.timeout,
        experiment_id=arguments.experiment_id,
        cache_prompt=arguments.cache_prompt,
        warmup_slot_ids=arguments.warmup_slot,
        server_pid=arguments.server_pid,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
