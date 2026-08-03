#!/usr/bin/env python3
"""Generate the frozen E11c sealed-confirmation sample-index map."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SALT = "pareto64-e11c-sealed-mmlu-v1"
TASK_SPLIT_SIZES = {
    "e11c_mmlu_computer_security": 100,
    "e11c_mmlu_machine_learning": 112,
    "e11c_mmlu_business_ethics": 100,
}
SAMPLES_PER_TASK = 80


def select_indices(task: str, split_size: int) -> list[int]:
    """Select a stable subset without using labels or model outcomes."""
    ranked = sorted(
        range(split_size),
        key=lambda index: hashlib.sha256(f"{SALT}\0{task}\0{index}".encode()).digest(),
    )
    return sorted(ranked[:SAMPLES_PER_TASK])


def sample_map() -> dict[str, list[int]]:
    """Return all frozen task sample indices."""
    return {
        task: select_indices(task, split_size)
        for task, split_size in TASK_SPLIT_SIZES.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(sample_map(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
