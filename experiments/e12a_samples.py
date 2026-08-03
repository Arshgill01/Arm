#!/usr/bin/env python3
"""Generate the frozen E12a imatrix calibration-index map."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SALT = "pareto64-e12a-imatrix-calibration-v1"
DATASET_SPLIT_SIZES = {
    "arc_easy_train": 2251,
    "hellaswag_train": 39905,
    "winogrande_train": 40398,
}
SAMPLES_PER_DATASET = 160


def select_indices(dataset: str, split_size: int) -> list[int]:
    """Select stable training rows without using labels or model outcomes."""
    ranked = sorted(
        range(split_size),
        key=lambda index: hashlib.sha256(
            f"{SALT}\0{dataset}\0{index}".encode()
        ).digest(),
    )
    return sorted(ranked[:SAMPLES_PER_DATASET])


def sample_map() -> dict[str, list[int]]:
    """Return all frozen calibration row indices."""
    return {
        dataset: select_indices(dataset, split_size)
        for dataset, split_size in DATASET_SPLIT_SIZES.items()
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
