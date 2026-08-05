#!/usr/bin/env python3
"""Aggregate the nine E12b root summaries without selecting nested prerequisites."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e12b_actual_ingest import aggregate_summary
    from experiments.e5b_ingest import load_object
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e12b_actual_ingest import aggregate_summary
    from e5b_ingest import load_object


def select_root_summaries(
    cells_root: Path, candidates: list[str], run_id: str
) -> list[Path]:
    expected = [
        cells_root / f"e12b-actual-{candidate}-{run_id}-1" / "summary.json"
        for candidate in candidates
    ]
    if not all(path.is_file() for path in expected):
        raise ValueError("E12b root cell summary set is incomplete")
    observed = sorted(cells_root.glob("*/summary.json"))
    if set(observed) != set(expected):
        raise ValueError("E12b root cell summary set differs")
    return expected


def build_recovered_aggregate(
    *,
    cells_root: Path,
    contract_path: Path,
    stock_path: Path,
    run_id: str,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    candidates = [item["candidate"] for item in contract["candidates"]]
    summaries = select_root_summaries(cells_root, candidates, run_id)
    recursive = list(cells_root.rglob("summary.json"))
    nested = [path for path in recursive if path.parent.name == "e12a"]
    if len(recursive) != 18 or len(nested) != 9:
        raise ValueError("E12b nested prerequisite summary evidence differs")
    return aggregate_summary(contract_path, summaries, stock_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cells-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_recovered_aggregate(
        cells_root=args.cells_root,
        contract_path=args.contract,
        stock_path=args.stock,
        run_id=args.run_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
