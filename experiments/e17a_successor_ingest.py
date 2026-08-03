#!/usr/bin/env python3
"""Validate E17a successor evidence plus its retained first failure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e17a_kv_preflight_ingest import build_manifest as build_base_manifest
    from experiments.e17a_successor_freeze import SUCCESSOR_INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e17a_kv_preflight_ingest import build_manifest as build_base_manifest
    from e17a_successor_freeze import SUCCESSOR_INPUT_PATHS


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict:
    contract = load_object(contract_path)
    for name, relative in SUCCESSOR_INPUT_PATHS.items():
        if sha256_file(root / relative) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E17a successor input differs for {name}")
    failure = load_object(root / SUCCESSOR_INPUT_PATHS["failure_manifest"])
    if (
        load_object(evidence / "first-failure.json") != failure
        or contract.get("first_failure", {}).get("manifest_sha256")
        != sha256_file(root / SUCCESSOR_INPUT_PATHS["failure_manifest"])
        or contract.get("first_failure", {}).get("configuration_attempts_started") != 0
    ):
        raise ValueError("E17a successor first failure differs")
    manifest = build_base_manifest(evidence, contract_path, root)
    manifest["first_failure"] = contract["first_failure"]
    manifest["validation"]["first_failure_retained"] = True
    manifest["validation"]["scientific_contract_changed_by_repair"] = False
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
    print(json.dumps({"status": manifest["status"], "decision": manifest["decision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
