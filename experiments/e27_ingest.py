#!/usr/bin/env python3
"""Validate and summarize the E27 native Arm campaign."""

import argparse
import json
import re
import statistics
from pathlib import Path


PROFILE_ROW = re.compile(r"^\s*(?P<percent>[0-9.]+)%\s+.*?(?P<symbol>\S.*)$")


def load_json_lines(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"empty JSON-lines file: {path}")
    return rows


def summarize(values: list[float], unit: str) -> dict:
    if len(values) != 6:
        raise ValueError(f"expected six process samples, got {len(values)}")
    if any(value <= 0 for value in values):
        raise ValueError(f"non-positive timing sample: {values}")
    median = statistics.median(values)
    return {
        "process_samples": values,
        "process_count": len(values),
        f"median_{unit}": median,
        "population_cv": statistics.pstdev(values) / statistics.mean(values),
    }


def direct_case(root: Path, case_id: str) -> dict:
    result = {}
    for variant in ("baseline", "candidate"):
        paths = sorted((root / "direct").glob(f"{case_id}-*-{variant}.json"))
        values = [float(json.loads(path.read_text())["median_us"]) for path in paths]
        result[variant] = summarize(values, "us")
    result["speedup"] = (
        result["baseline"]["median_us"] / result["candidate"]["median_us"]
    )
    return result


def inference_case(root: Path, case_id: str) -> dict:
    result = {}
    for variant in ("baseline", "candidate"):
        paths = sorted((root / "inference").glob(f"{case_id}-*-{variant}.jsonl"))
        values = []
        internal_samples = []
        for path in paths:
            rows = load_json_lines(path)
            if len(rows) != 1:
                raise ValueError(f"expected one llama-bench row in {path}, got {len(rows)}")
            row = rows[0]
            samples_ts = row.get("samples_ts")
            if not isinstance(samples_ts, list) or len(samples_ts) != 3:
                raise ValueError(f"expected three internal samples in {path}")
            values.append(float(row["avg_ts"]))
            internal_samples.extend(float(value) for value in samples_ts)
        result[variant] = summarize(values, "tokens_per_second")
        result[variant]["internal_samples_tokens_per_second"] = internal_samples
    result["speedup"] = (
        result["candidate"]["median_tokens_per_second"]
        / result["baseline"]["median_tokens_per_second"]
    )
    return result


def correctness_summary(root: Path, maximum_nmse: float) -> dict:
    rows = []
    for path in sorted((root / "correctness").glob("*.jsonl")):
        rows.extend(load_json_lines(path))
    if len(rows) != 9:
        raise ValueError(f"expected nine correctness cases, got {len(rows)}")
    maximum_observed = max(float(row["nmse"]) for row in rows)
    return {
        "case_count": len(rows),
        "maximum_nmse": maximum_observed,
        "maximum_abs_error": max(float(row["max_abs_error"]) for row in rows),
        "declared_maximum_nmse": maximum_nmse,
        "all_rows_pass": all(row.get("pass") is True for row in rows),
        "accepted": all(row.get("pass") is True for row in rows)
        and maximum_observed <= maximum_nmse,
    }


def profile_symbols(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        match = PROFILE_ROW.match(line)
        if match:
            rows.append(
                {
                    "percent": float(match.group("percent")),
                    "symbol": match.group("symbol"),
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.evidence_dir
    contract = json.loads((root / "contract.json").read_text())

    correctness = correctness_summary(
        root, float(contract["correctness"]["maximum_nmse"])
    )
    direct = {
        case["id"]: direct_case(root, case["id"])
        for case in contract["direct_performance"]["cases"]
    }
    inference = {
        case["id"]: inference_case(root, case["id"])
        for case in contract["whole_model"]["cases"]
    }

    output_diff = root / "demo" / "output.diff"
    demo = {
        "output_byte_identical": output_diff.exists() and output_diff.stat().st_size == 0,
        "output_sha256": (root / "demo" / "output-sha256.txt").read_text().splitlines(),
    }
    profile = {
        case: profile_symbols(root / "profile" / case / "perf-report-symbol.txt")
        for case in ("pp512", "pp2048", "pp4096", "candidate-pp2048")
    }

    promotion = contract["whole_model"]["promotion"]
    direct_admission = float(contract["direct_performance"]["admission_ratio"])
    gates = {
        "correctness": correctness["accepted"],
        "deterministic_demo": demo["output_byte_identical"],
        "direct_all_at_least_admission": all(
            case["speedup"] >= direct_admission for case in direct.values()
        ),
        "pp2048_material": inference["pp2048"]["speedup"]
        >= float(promotion["pp2048_ratio"]),
        "pp4096_material": inference["pp4096"]["speedup"]
        >= float(promotion["pp4096_ratio"]),
        "pp512_guard": inference["pp512"]["speedup"]
        >= float(promotion["minimum_pp512_ratio"]),
        "tg128_guard": inference["tg128"]["speedup"]
        >= float(promotion["minimum_tg128_ratio"]),
        "profile_evidence_present": all(profile.values()),
    }
    gates["accepted"] = all(gates.values())

    result = {
        "schema_version": 1,
        "experiment_id": "E27",
        "correctness": correctness,
        "direct": direct,
        "inference": inference,
        "demo": demo,
        "profile_symbols": profile,
        "gates": gates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(gates, sort_keys=True))
    return 0 if gates["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
