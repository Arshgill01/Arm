#!/usr/bin/env python3
"""Freeze E17a's shell-invocation-only successor."""

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


SUCCESSOR_INPUT_PATHS = {
    "base_contract": Path("experiments/e17a_contract.json"),
    "failure_manifest": Path("results/manifests/e17a-30855155720.json"),
    "failure_retainer": Path("experiments/e17a_permission_failure_retain.py"),
    "successor_freeze": Path("experiments/e17a_successor_freeze.py"),
    "successor_ingest": Path("experiments/e17a_successor_ingest.py"),
    "successor_test": Path("tests/test_e17a_successor.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    base = load_object(root / SUCCESSOR_INPUT_PATHS["base_contract"])
    failure = load_object(root / SUCCESSOR_INPUT_PATHS["failure_manifest"])
    if (
        base.get("experiment_id") != "E17a"
        or failure.get("status") != "invalid_premeasurement_cell_permission_failure"
        or failure.get("configuration_attempts_started") != 0
        or failure.get("decision", {}).get("separately_committed_shell_invocation_repair_allowed") is not True
    ):
        raise ValueError("E17a successor prerequisite differs")
    contract = copy.deepcopy(base)
    for name, relative in SUCCESSOR_INPUT_PATHS.items():
        contract["inputs"][f"{name}_path"] = relative.as_posix()
        contract["inputs"][f"{name}_sha256"] = sha256_file(root / relative)
    contract["state"] = (
        "separately frozen after retaining the premeasurement shell permission failure, "
        "before any configuration launch, model request, or result"
    )
    contract["first_failure"] = {
        "run_id": failure["github"]["run_id"],
        "run_attempt": failure["github"]["run_attempt"],
        "repository_commit": failure["github"]["repository_commit"],
        "artifact_name": failure["github"]["artifact_name"],
        "artifact_id": failure["github"]["artifact_id"],
        "artifact_digest": failure["github"]["artifact_digest"],
        "manifest_sha256": sha256_file(root / SUCCESSOR_INPUT_PATHS["failure_manifest"]),
        "configuration_attempts_started": 0,
        "repair": [
            "create the already-frozen cell evidence directory before invocation",
            "invoke the exact hash-bound cell runner through bash",
        ],
    }
    contract["decision"]["first_failure_rehabilitated"] = False
    contract["decision"]["successor_changes_scientific_contract"] = False
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
