#!/usr/bin/env python3
"""Validate current-upstream stock-versus-combined E28 evidence on Neoverse N2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from e28_current_ingest import inference_summary as current_inference_summary
from e28_ingest import NMSE_PATTERN, load_object


def correctness_summary(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    flash = []
    for path in sorted((root / "correctness").glob("flash-*.jsonl")):
        flash.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    direct_nmse = []
    for path in sorted((root / "correctness").glob("*.txt")):
        direct_nmse.extend(float(value) for value in NMSE_PATTERN.findall(path.read_text()))
    if len(flash) != 9 or not direct_nmse:
        raise ValueError("second-machine direct correctness evidence is incomplete")
    threshold = float(contract["correctness"]["maximum_flash_attention_nmse"])
    maximum_flash = max(float(row["nmse"]) for row in flash)
    maximum_direct = max(direct_nmse)
    return {
        "flash_case_count": len(flash),
        "maximum_flash_nmse": maximum_flash,
        "maximum_direct_nmse": maximum_direct,
        "passed": all(row.get("pass") is True for row in flash)
        and maximum_flash <= threshold
        and maximum_direct <= threshold,
    }


def build_summary(root: Path) -> dict[str, Any]:
    contract = load_object(root / "contract.json")
    portable_contract = json.loads(json.dumps(contract))
    portable_contract["current_upstream"]["matched_cases"] = [
        "pp512", "pp2048", "pp4096", "tg128"
    ]
    correctness = correctness_summary(root, contract)
    inference = current_inference_summary(root, portable_contract)
    sidecar = load_object(root / "source/e25-decoded-sidecar-bytes.json")
    if sidecar.get("decoded_sidecar_bytes", 0) <= 0:
        raise ValueError("decoded Q4_K sidecar byte evidence is missing")
    gates = {
        "direct_correctness": correctness["passed"],
        "six_processes_per_variant_per_case": all(
            inference[case][variant]["count"] == 6
            for case in ("pp512", "pp2048", "pp4096", "tg128")
            for variant in ("stock", "combined")
        ),
    }
    gates["accepted"] = all(gates.values())
    return {
        "schema_version": 1,
        "experiment_id": "E28-current-upstream-portability-n2",
        "model": contract["models"]["portability"],
        "correctness": correctness,
        "decoded_sidecar": sidecar,
        "inference": inference,
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
