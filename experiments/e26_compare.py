#!/usr/bin/env python3
"""Compare deterministic float32 outputs for E26."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def read_f32(path: Path) -> tuple[float, ...]:
    data = path.read_bytes()
    if len(data) % 4:
        raise ValueError(f"not a float32 file: {path}")
    return struct.unpack(f"<{len(data) // 4}f", data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-nmse", type=float, default=1e-8)
    args = parser.parse_args()

    reference = read_f32(args.reference)
    candidate = read_f32(args.candidate)
    if len(reference) != len(candidate):
        raise ValueError("float32 output lengths differ")
    squared_error = sum((left - right) ** 2 for left, right in zip(reference, candidate))
    reference_energy = sum(value**2 for value in reference)
    nmse = squared_error / reference_energy if reference_energy else squared_error
    summary = {
        "candidate": str(args.candidate),
        "count": len(reference),
        "max_abs_error": max((abs(left - right) for left, right in zip(reference, candidate)), default=0.0),
        "nmse": nmse,
        "reference": str(args.reference),
        "tolerance": {"max_nmse": args.max_nmse},
        "within_tolerance": nmse <= args.max_nmse,
    }
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["within_tolerance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
