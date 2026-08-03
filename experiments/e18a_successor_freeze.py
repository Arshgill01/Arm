#!/usr/bin/env python3
"""Freeze E18a's training-timeout-only successor."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


ORIGINAL = Path("experiments/e18a_contract.json")
ADDITIONAL_INPUTS = {
    "predecessor_failure": Path(
        "results/manifests/e18a-training-timeout-30858852227.json"
    ),
    "successor_freeze": Path("experiments/e18a_successor_freeze.py"),
    "successor_ingest": Path("experiments/e18a_successor_ingest.py"),
    "successor_test": Path("tests/test_e18a_successor.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    original = load_object(root / ORIGINAL)
    failure = load_object(root / ADDITIONAL_INPUTS["predecessor_failure"])
    if (
        original.get("experiment_id") != "E18a"
        or original.get("request", {}).get("timeout_seconds") != 30.0
        or failure.get("status")
        != "invalid_instrumented_training_timeout_after_complete_matrix"
        or failure.get("contract_sha256") != sha256_file(root / ORIGINAL)
        or failure.get("failure", {}).get("training_timeout_seconds") != 30.0
        or failure.get("failure", {}).get("training_requests_timed_out") != 28
        or failure.get("decision", {}).get(
            "separately_frozen_training_timeout_successor_allowed"
        )
        is not True
    ):
        raise ValueError("E18a successor prerequisites differ")
    contract = copy.deepcopy(original)
    contract["campaign_variant"] = "training-timeout-successor"
    contract["state"] = (
        "frozen after retaining the 30-second instrumented-training timeout and "
        "before observing any successor training, profile, build, or service result"
    )
    contract["training"]["request_timeout_seconds"] = 180.0
    contract["training"]["request_timeout_scope"] = (
        "instrumented profile-generation pass only; measured service cells retain "
        "the original 30-second request timeout"
    )
    contract["predecessor_failure"] = {
        "run_id": failure["github"]["run_id"],
        "artifact": failure["github"]["artifact_name"],
        "artifact_digest": failure["github"]["artifact_digest"],
        "status": failure["status"],
        "failed_run_rehabilitated": False,
    }
    for name, relative in ADDITIONAL_INPUTS.items():
        contract["inputs"][f"{name}_path"] = relative.as_posix()
        contract["inputs"][f"{name}_sha256"] = sha256_file(root / relative)
    contract["decision"]["predecessor_failure_retained"] = True
    contract["decision"]["measured_service_timeout_changed"] = False
    contract["decision"]["training_timeout_is_performance_evidence"] = False
    contract["negative_result_rule"] = (
        "Retain any repeated training timeout, quality mismatch, incomplete profile, "
        "build failure, service failure, quality regression, performance regression, "
        "dispersion, footprint regression, or gate failure without changing the "
        "180-second training-only timeout or any original performance gate."
    )
    return contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
