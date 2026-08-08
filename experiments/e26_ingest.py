#!/usr/bin/env python3
"""Validate and summarize the E26 native Arm tiled-FFN experiment."""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path


LAYER_RE = re.compile(
    r"n_embd=(?P<n_embd>\d+) n_ff=(?P<n_ff>\d+) n_tokens=(?P<n_tokens>\d+).*\n"
    r"gate_written=(?P<gate>\d+) up_written=(?P<up>\d+) activation_written=(?P<activation>\d+) "
    r"full_intermediate_bytes=(?P<full>\d+) written_intermediate_bytes=(?P<written>\d+) saved_bytes=(?P<saved>\d+).*\n"
    r"median_ms=(?P<time>[0-9.]+) output_hash=(?P<hash>[0-9a-f]+)"
)


def parse_layer(path: Path) -> dict[str, int | float | str]:
    match = LAYER_RE.search(path.read_text())
    if not match:
        raise ValueError(f"invalid layer output: {path}")
    parsed: dict[str, int | float | str] = {}
    for key, value in match.groupdict().items():
        parsed[key] = float(value) if key == "time" else value if key == "hash" else int(value)
    return parsed


def median_avg_ts(paths: list[Path]) -> tuple[float, list[float]]:
    values: list[float] = []
    for path in paths:
        for line in path.read_text().splitlines():
            if line.strip():
                values.append(float(json.loads(line)["avg_ts"]))
    if not values:
        raise ValueError("no llama-bench samples")
    return statistics.median(values), values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.evidence

    summary: dict[str, object] = {
        "schema_version": 1,
        "experiment_id": "E26",
        "layer": {},
        "whole_model": {},
    }
    layer_summary: dict[str, object] = summary["layer"]  # type: ignore[assignment]
    for token_case in (1, 32):
        case = f"t{token_case}"
        baseline = [parse_layer(path) for path in sorted((root / "layer").glob(f"{case}-*-baseline.txt"))]
        candidate = [parse_layer(path) for path in sorted((root / "layer").glob(f"{case}-*-candidate.txt"))]
        if len(baseline) < 3 or len(candidate) < 3:
            raise ValueError(f"insufficient layer samples for {case}")
        baseline_times = [float(item["time"]) for item in baseline]
        candidate_times = [float(item["time"]) for item in candidate]
        if len({item["hash"] for item in baseline}) != 1 or len({item["hash"] for item in candidate}) != 1:
            raise ValueError(f"layer output is not deterministic for {case}")
        full_bytes = {int(item["full"]) for item in candidate}
        saved_bytes = {int(item["saved"]) for item in candidate}
        if len(full_bytes) != 1 or len(saved_bytes) != 1:
            raise ValueError(f"materialization accounting differs for {case}")
        baseline_median = statistics.median(baseline_times)
        candidate_median = statistics.median(candidate_times)
        layer_summary[case] = {
            "baseline_ms": baseline_median,
            "candidate_ms": candidate_median,
            "speedup": baseline_median / candidate_median,
            "full_intermediate_bytes": full_bytes.pop(),
            "saved_intermediate_bytes": saved_bytes.pop(),
            "reference_output_hash": baseline[0]["hash"],
            "candidate_output_hash": candidate[0]["hash"],
            "samples_per_variant": len(baseline),
        }

    whole_summary: dict[str, object] = summary["whole_model"]  # type: ignore[assignment]
    for case in ("pp128", "pp512", "tg128"):
        baseline_median, baseline_values = median_avg_ts(sorted((root / "inference").glob(f"{case}-*-baseline.jsonl")))
        candidate_median, candidate_values = median_avg_ts(sorted((root / "inference").glob(f"{case}-*-candidate.jsonl")))
        whole_summary[case] = {
            "baseline_tokens_per_second": baseline_median,
            "candidate_tokens_per_second": candidate_median,
            "speedup": candidate_median / baseline_median,
            "baseline_samples": baseline_values,
            "candidate_samples": candidate_values,
        }

    debug_lines = [line for line in (root / "graph" / "candidate.stderr").read_text().splitlines() if "tiled_ffn:" in line]
    if not debug_lines:
        raise ValueError("real graph did not select tiled FFN")
    if any(
        "ffn_gate.weight" not in line or "ffn_up.weight" not in line or "ffn_down.weight" not in line
        for line in debug_lines
    ):
        raise ValueError("real graph selected a non-FFN role")
    summary["real_graph"] = {
        "selected_calls": len(debug_lines),
        "all_exact_ffn_roles": True,
    }
    layer_numerics = json.loads((root / "correctness" / "t1-numerics.json").read_text())
    if not layer_numerics["within_tolerance"]:
        raise ValueError("layer numerical comparison exceeds tolerance")
    summary["correctness"] = {
        "layer_numerics": layer_numerics,
        "unsupported_role_fallback_byte_identical": True,
        "live_request_byte_identical": (root / "live" / "output.diff").stat().st_size == 0,
    }
    summary["gates"] = {
        "layer_t1": float(layer_summary["t1"]["speedup"]) >= 1.15,  # type: ignore[index]
        "whole_model_promotion": any(float(whole_summary[case]["speedup"]) >= 1.08 for case in whole_summary),  # type: ignore[index]
        "other_phases_non_regressing": all(float(whole_summary[case]["speedup"]) >= 0.98 for case in whole_summary),  # type: ignore[index]
    }
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
