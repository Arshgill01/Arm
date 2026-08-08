#!/usr/bin/env python3
import argparse
import json
import math
import re
import statistics
from pathlib import Path


MICRO_PATTERN = re.compile(
    r"median_ms=(?P<median_ms>[0-9.]+).*checksum=(?P<checksum>[-+0-9.eE]+)"
)
CORRECTNESS_PATTERN = re.compile(
    r"nb=(?P<nb>\d+) seed=(?P<seed>\d+) nmse=(?P<nmse>[-+0-9.eE]+) "
    r"max_abs=(?P<max_abs>[-+0-9.eE]+)"
)


def read_samples(root: Path, tag: str, variant: str) -> list[float]:
    values: list[float] = []
    for path in sorted((root / "inference").glob(f"{tag}-*-{variant}.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                values.extend(json.loads(line)["samples_ts"])
    return values


def sample_stats(values: list[float]) -> dict[str, object]:
    if not values:
        raise ValueError("missing benchmark samples")
    mean = statistics.mean(values)
    return {
        "samples": values,
        "sample_count": len(values),
        "mean_tokens_per_second": mean,
        "population_cv": statistics.pstdev(values) / mean,
    }


def read_micro(root: Path, variant: str) -> dict[str, object]:
    medians: list[float] = []
    checksums: list[float] = []
    for path in sorted((root / "micro").glob(f"*-{variant}.txt")):
        match = MICRO_PATTERN.search(path.read_text())
        if match is None:
            raise ValueError(f"cannot parse {path}")
        medians.append(float(match.group("median_ms")))
        checksums.append(float(match.group("checksum")))
    if not medians:
        raise ValueError(f"missing microbenchmark results for {variant}")
    return {
        "median_ms_by_round": medians,
        "median_of_round_medians_ms": statistics.median(medians),
        "checksums": checksums,
    }


def read_correctness(root: Path, variant: str) -> dict[str, object]:
    rows = []
    path = root / "correctness" / f"{variant}.txt"
    for line in path.read_text().splitlines():
        match = CORRECTNESS_PATTERN.fullmatch(line)
        if match is None:
            raise ValueError(f"cannot parse correctness row in {path}: {line}")
        rows.append(
            {
                "nb": int(match.group("nb")),
                "seed": int(match.group("seed")),
                "nmse": float(match.group("nmse")),
                "max_abs": float(match.group("max_abs")),
            }
        )
    if len(rows) != 15:
        raise ValueError(f"expected 15 correctness rows in {path}, found {len(rows)}")
    return {
        "case_count": len(rows),
        "max_nmse": max(row["nmse"] for row in rows),
        "max_abs": max(row["max_abs"] for row in rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.evidence_dir

    inference = {}
    for tag in ("pp128", "pp512", "tg128"):
        baseline = sample_stats(read_samples(root, tag, "baseline"))
        candidate = sample_stats(read_samples(root, tag, "candidate"))
        inference[tag] = {
            "baseline": baseline,
            "candidate": candidate,
            "speedup": (
                candidate["mean_tokens_per_second"]
                / baseline["mean_tokens_per_second"]
            ),
        }

    micro = {
        variant: read_micro(root, variant) for variant in ("baseline", "candidate")
    }
    micro["speedup"] = (
        micro["baseline"]["median_of_round_medians_ms"]
        / micro["candidate"]["median_of_round_medians_ms"]
    )

    correctness = {
        variant: read_correctness(root, variant)
        for variant in ("baseline", "candidate")
    }
    correctness_diff = root / "correctness" / "baseline-vs-candidate.diff"
    correctness["baseline_candidate_exact_match"] = (
        correctness_diff.exists() and correctness_diff.stat().st_size == 0
    )
    correctness["micro_checksum_match"] = all(
        math.isclose(left, right, rel_tol=0.0, abs_tol=0.0)
        for left, right in zip(
            micro["baseline"]["checksums"],
            micro["candidate"]["checksums"],
            strict=True,
        )
    )

    gates = {
        "correctness": (
            correctness["baseline_candidate_exact_match"]
            and correctness["micro_checksum_match"]
            and correctness["candidate"]["max_nmse"] <= 5e-4
        ),
        "sample_count": all(
            inference[tag][variant]["sample_count"] >= 6
            for tag in inference
            for variant in ("baseline", "candidate")
        ),
        "pp128_material": inference["pp128"]["speedup"] >= 1.05,
        "pp512_positive": inference["pp512"]["speedup"] >= 1.03,
        "decode_no_material_regression": inference["tg128"]["speedup"] >= 0.98,
    }
    gates["accepted"] = all(gates.values())

    result = {
        "schema_version": 1,
        "inference": inference,
        "micro": micro,
        "correctness": correctness,
        "gates": gates,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["gates"], sort_keys=True))
    return 0 if gates["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
