#!/usr/bin/env python3
"""Validate the E18a successor with a training-only request timeout."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

try:
    import experiments.e18a_ingest as base
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    import e18a_ingest as base
    from e5b_ingest import load_object, sha256_file


def validate_training(
    evidence: Path,
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> dict[str, Any]:
    adjusted = copy.deepcopy(contract)
    timeout = contract.get("training", {}).get("request_timeout_seconds")
    if (
        contract.get("campaign_variant") != "training-timeout-successor"
        or timeout != 180.0
        or contract["request"]["timeout_seconds"] != 30.0
    ):
        raise ValueError("E18a successor timeout boundary differs")
    adjusted["request"]["timeout_seconds"] = timeout
    result = base.validate_training(evidence, adjusted, tasks, references)
    result["request_timeout_seconds"] = timeout
    result["timeout_scope"] = "instrumented training only"
    return result


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    failure_path = root / contract["inputs"]["predecessor_failure_path"]
    failure = load_object(failure_path)
    if (
        failure.get("status")
        != "invalid_instrumented_training_timeout_after_complete_matrix"
        or sha256_file(failure_path)
        != contract["inputs"]["predecessor_failure_sha256"]
        or failure.get("decision", {}).get(
            "separately_frozen_training_timeout_successor_allowed"
        )
        is not True
    ):
        raise ValueError("E18a successor predecessor differs")
    original = base.validate_training
    base.validate_training = validate_training
    try:
        result = base.build_manifest(evidence, contract_path, root)
    finally:
        base.validate_training = original
    result["campaign_variant"] = contract["campaign_variant"]
    result["predecessor_failure"] = contract["predecessor_failure"]
    result["decision"]["failed_predecessor_rehabilitated"] = False
    return result


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
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
