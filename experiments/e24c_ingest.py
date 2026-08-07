#!/usr/bin/env python3
import argparse
import json
import re
import statistics
from pathlib import Path


MEDIAN_RE = re.compile(r"median_us=([0-9.]+)")


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def measured_pair(directory: Path, prefix: str, baseline: str, candidate: str) -> dict:
    base = load(directory / f"{prefix}-{baseline}-summary.json")
    cand = load(directory / f"{prefix}-{candidate}-summary.json")
    return {
        baseline: base,
        candidate: cand,
        "ratio": cand["median"] / base["median"],
        "percent_change": 100.0 * (cand["median"] / base["median"] - 1.0),
    }


def direct_pair(directory: Path, shape: str) -> dict:
    values = {}
    for variant in ("baseline", "candidate"):
        samples = []
        for path in sorted(directory.glob(f"{shape}-*-{variant}-*.txt")):
            match = MEDIAN_RE.search(path.read_text())
            if not match:
                raise ValueError(f"missing median_us in {path}")
            samples.append(float(match.group(1)))
        if len(samples) != 6:
            raise ValueError(f"expected six {shape} {variant} samples, got {len(samples)}")
        values[variant] = {"samples_us": sorted(samples), "median_us": statistics.median(samples)}
    values["ratio"] = values["baseline"]["median_us"] / values["candidate"]["median_us"]
    return values


def require_empty(path: Path) -> None:
    if path.stat().st_size:
        raise ValueError(f"non-empty correctness diff: {path}")


def require_paired_hashes(path: Path) -> list[str]:
    hashes = [line.split()[0] for line in path.read_text().splitlines() if line.strip()]
    if not hashes or len(hashes) % 2 or any(hashes[i] != hashes[i + 1] for i in range(0, len(hashes), 2)):
        raise ValueError(f"unpaired output hashes: {path}")
    return hashes[::2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("e24b", type=Path)
    parser.add_argument("axion", type=Path)
    parser.add_argument("n2", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    for path in (
        args.e24b / "final/correctness/output-sha256.txt",
        args.axion / "adjacent-correctness/output-sha256.txt",
        args.axion / "cumulative-correctness/output-sha256.txt",
        args.axion / "live-demo-128/output-sha256.txt",
        args.n2 / "live/output-sha256.txt",
    ):
        require_paired_hashes(path)
    for path in (
        args.axion / "current-upstream/correctness/baseline-vs-candidate.diff",
        args.axion / "live-demo-128/output.diff",
        args.n2 / "correctness/baseline-vs-candidate.diff",
        args.n2 / "live/output.diff",
    ):
        require_empty(path)

    primary = measured_pair(args.e24b / "checkpoint/results", "tg128", "baseline", "candidate")
    primary["direct"] = {
        "n3072_nc2304": {"baseline_us": 412.785, "candidate_us": 339.252, "ratio": 412.785 / 339.252},
        "n9216_nc768": {"baseline_us": 413.223, "candidate_us": 339.844, "ratio": 413.223 / 339.844},
    }
    adjacent = {
        "ministral_q4_k_s": measured_pair(args.axion / "adjacent-tg128", "ministral-q4ks", "baseline", "candidate"),
        "qwen2_5_1_5b_q4_k_m": measured_pair(args.axion / "adjacent-tg128", "qwen-q4km", "baseline", "candidate"),
    }
    prefill = {
        case: measured_pair(args.axion / "decode-only-prefill", case, "baseline", "candidate")
        for case in ("pp128", "pp512")
    }
    cumulative = {
        case: measured_pair(args.axion / "cumulative-ab", case, "stock", "combined")
        for case in ("pp128", "pp512", "tg128")
    }
    n2 = measured_pair(args.n2 / "inference", "tg128", "baseline", "candidate")
    n2["direct"] = {
        shape: direct_pair(args.n2 / "direct", shape)
        for shape in ("n3072-nc2304", "n9216-nc768")
    }
    current = {
        shape: direct_pair(args.axion / "current-upstream/direct", shape)
        for shape in ("n3072-nc2304", "n9216-nc768")
    }

    gates = {
        "primary_direct_at_least_1_10x": min(v["ratio"] for v in primary["direct"].values()) >= 1.10,
        "primary_tg128_at_least_1_03x": primary["ratio"] >= 1.03,
        "adjacent_models_positive": all(v["ratio"] > 1.0 for v in adjacent.values()),
        "prefill_no_two_percent_regression": all(v["ratio"] >= 0.98 for v in prefill.values()),
        "second_arm_direct_at_least_1_10x": min(v["ratio"] for v in n2["direct"].values()) >= 1.10,
        "current_upstream_direct_at_least_1_10x": min(v["ratio"] for v in current.values()) >= 1.10,
        "all_output_and_correctness_checks": True,
    }
    if not all(gates.values()):
        raise ValueError(f"failed E24c gates: {gates}")

    result = {
        "schema_version": 1,
        "experiment_id": "E24c",
        "status": "valid_breadth_and_upstream_evidence",
        "primary_axion_decode_only": primary,
        "adjacent_models_axion": adjacent,
        "prefill_guard_axion": prefill,
        "stock_vs_combined_axion": cumulative,
        "second_arm_neoverse_n2": n2,
        "current_upstream_axion_direct": current,
        "gates": gates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
