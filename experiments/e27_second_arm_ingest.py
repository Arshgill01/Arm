#!/usr/bin/env python3
"""Summarize the E27 adjacent-model run on the second Arm CPU."""

import argparse
import json
import statistics
from pathlib import Path


def six_values(directory: Path, pattern: str, field: str) -> list[float]:
    values = []
    for path in sorted(directory.glob(pattern)):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line]
        if len(rows) != 1:
            raise ValueError(f"expected one JSON row in {path}")
        values.append(float(rows[0][field]))
    if len(values) != 6 or any(value <= 0 for value in values):
        raise ValueError(f"expected six positive values for {pattern}, got {values}")
    return values


def pair(root: Path, subdir: str, case: str, field: str, lower_is_better: bool) -> dict:
    result = {}
    for variant in ("baseline", "candidate"):
        values = six_values(root / subdir, f"{case}-*-{variant}.json*", field)
        result[variant] = {
            "process_samples": values,
            "median": statistics.median(values),
            "population_cv": statistics.pstdev(values) / statistics.mean(values),
        }
    if lower_is_better:
        result["speedup"] = result["baseline"]["median"] / result["candidate"]["median"]
    else:
        result["speedup"] = result["candidate"]["median"] / result["baseline"]["median"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.evidence_dir
    correctness_rows = [
        json.loads(line)
        for line in (root / "correctness/d128-q64-kv512.jsonl").read_text().splitlines()
        if line
    ]
    correctness = {
        "case_count": len(correctness_rows),
        "maximum_nmse": max(float(row["nmse"]) for row in correctness_rows),
        "accepted": len(correctness_rows) == 3
        and all(row.get("pass") is True for row in correctness_rows),
    }
    direct = {
        case: pair(root, "direct", case, "median_us", True)
        for case in ("d128-q512-kv512", "d128-q512-kv2048")
    }
    inference = {
        case: pair(root, "inference", case, "avg_ts", False)
        for case in ("pp512", "pp2048", "tg64")
    }
    gates = {
        "correctness": correctness["accepted"],
        "direct_all_at_least_1_20x": all(value["speedup"] >= 1.20 for value in direct.values()),
        "pp2048_at_least_1_05x": inference["pp2048"]["speedup"] >= 1.05,
        "pp512_guard": inference["pp512"]["speedup"] >= 0.98,
        "tg64_guard": inference["tg64"]["speedup"] >= 0.98,
    }
    gates["accepted"] = all(gates.values())
    result = {
        "schema_version": 1,
        "experiment_id": "E27-second-arm",
        "correctness": correctness,
        "direct": direct,
        "inference": inference,
        "gates": gates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(gates, sort_keys=True))
    return 0 if gates["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
