#!/usr/bin/env python3
"""Validate E17a's second successor and both retained earlier failures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e17a_second_successor_freeze import (
        SECOND_SUCCESSOR_INPUT_PATHS,
    )
    from experiments.e17a_successor_ingest import build_manifest as build_first_manifest
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e17a_second_successor_freeze import SECOND_SUCCESSOR_INPUT_PATHS
    from e17a_successor_ingest import build_manifest as build_first_manifest


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict:
    contract = load_object(contract_path)
    for name, relative in SECOND_SUCCESSOR_INPUT_PATHS.items():
        if sha256_file(root / relative) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E17a second-successor input differs for {name}")
    second_failure = load_object(
        root / SECOND_SUCCESSOR_INPUT_PATHS["second_failure_manifest"]
    )
    if (
        load_object(evidence / "second-failure.json") != second_failure
        or contract.get("second_failure", {}).get("manifest_sha256")
        != sha256_file(root / SECOND_SUCCESSOR_INPUT_PATHS["second_failure_manifest"])
        or contract.get("second_failure", {}).get("configuration_processes_ready") != 3
        or contract.get("second_failure", {}).get("measured_model_requests_completed") != 0
    ):
        raise ValueError("E17a second-successor retained failure differs")
    manifest = build_first_manifest(evidence, contract_path, root)
    manifest["second_failure"] = contract["second_failure"]
    manifest["validation"]["second_failure_retained"] = True
    manifest["validation"]["subset_adapter_hash_bound"] = True
    manifest["validation"]["scientific_contract_changed_by_second_repair"] = False
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {"status": manifest["status"], "decision": manifest["decision"]},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
