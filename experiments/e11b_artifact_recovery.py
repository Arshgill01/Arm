#!/usr/bin/env python3
"""Replay E11b while accepting the server's documented slots-array shape."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import experiments.e11b_ingest as ingest
    from experiments.e5b_ingest import load_object
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    import e11b_ingest as ingest
    from e5b_ingest import load_object


def load_e11b_artifact_json(path: Path) -> Any:
    """Load only slots.json as an array; retain object-only parsing elsewhere."""
    if path.name != "slots.json":
        return load_object(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(
        isinstance(slot, dict) for slot in value
    ):
        raise ValueError(f"{path} must contain a JSON array of slot objects")
    return value


def build_recovered_summary(
    evidence: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    """Apply the one-path parser correction around the frozen E11b ingester."""
    if sys.version_info[:3] != (3, 10, 20):
        raise RuntimeError("E11b replay requires the source job's Python 3.10.20")
    original_loader = ingest.load_object
    ingest.load_object = load_e11b_artifact_json
    try:
        return ingest.build_summary(evidence, contract_path, root)
    finally:
        ingest.load_object = original_loader


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_recovered_summary(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
