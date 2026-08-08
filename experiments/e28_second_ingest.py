#!/usr/bin/env python3
"""Validate the E28 four-variant portability run on a second Arm machine."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from e28_ingest import VARIANTS, inference_summary, load_object


NMSE_PATTERN = re.compile(r"nmse(?:8|4|_decoded)?=([0-9.eE+-]+)")


def correctness_summary(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    flash_rows = []
    for path in sorted((root / "correctness").glob("flash-*.jsonl")):
        flash_rows.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    direct_nmse = []
    for path in sorted((root / "correctness").glob("*.txt")):
        direct_nmse.extend(float(value) for value in NMSE_PATTERN.findall(path.read_text()))
    if len(flash_rows) != 9 or not direct_nmse:
        raise ValueError("second-machine correctness evidence is incomplete")
    maximum_flash = max(float(row["nmse"]) for row in flash_rows)
    threshold = float(contract["correctness"]["maximum_flash_attention_nmse"])
    return {
        "flash_case_count": len(flash_rows),
        "maximum_flash_nmse": maximum_flash,
        "maximum_direct_nmse": max(direct_nmse),
        "passed": all(row.get("pass") is True for row in flash_rows)
        and maximum_flash <= threshold
        and max(direct_nmse) <= threshold,
    }


def performance_gates(contract: dict[str, Any], inference: dict[str, Any]) -> dict[str, bool]:
    thresholds = contract["performance"]["gates"]
    gates = {
        "B_A_tg128": inference["tg128"]["B_over_A"]["ratio"] >= thresholds["B_over_A_tg128"],
        "D_C_tg128": inference["tg128"]["D_over_C"]["ratio"] >= thresholds["D_over_C_tg128"],
    }
    for case in ("pp512", "pp2048", "pp4096"):
        gates[f"C_A_{case}"] = inference[case]["C_over_A"]["ratio"] >= thresholds[f"C_over_A_{case}"]
        gates[f"D_B_{case}"] = inference[case]["D_over_B"]["ratio"] >= thresholds[f"D_over_B_{case}"]
        gates[f"B_A_{case}_guard"] = inference[case]["B_over_A"]["ratio"] >= thresholds["minimum_non_target_ratio"]
        gates[f"D_C_{case}_guard"] = inference[case]["D_over_C"]["ratio"] >= thresholds["minimum_non_target_ratio"]
    gates["C_A_tg128_guard"] = inference["tg128"]["C_over_A"]["ratio"] >= thresholds["minimum_non_target_ratio"]
    gates["D_B_tg128_guard"] = inference["tg128"]["D_over_B"]["ratio"] >= thresholds["minimum_non_target_ratio"]
    return gates


def build_summary(root: Path) -> dict[str, Any]:
    contract = load_object(root / "contract.json")
    correctness = correctness_summary(root, contract)
    inference = inference_summary(root, contract)
    gates = performance_gates(contract, inference)
    gates["direct_correctness"] = correctness["passed"]
    gates["accepted"] = all(gates.values())
    return {
        "schema_version": 1,
        "experiment_id": "E28-portability-n2",
        "model": contract["models"]["portability"],
        "correctness": correctness,
        "inference": inference,
        "cumulative_D_over_A": {
            case: inference[case]["D_over_A"] for case in ("pp512", "pp2048", "pp4096", "tg128")
        },
        "gates": gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    summary = build_summary(args.evidence_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary["gates"], sort_keys=True))
    return 0 if summary["gates"]["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
