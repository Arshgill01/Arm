#!/usr/bin/env python3
"""Freeze E17a's subset-reference-only second successor."""

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


SECOND_SUCCESSOR_INPUT_PATHS = {
    "first_successor_contract": Path("experiments/e17a_successor_contract.json"),
    "second_failure_manifest": Path("results/manifests/e17a-30855793293.json"),
    "second_failure_retainer": Path("experiments/e17a_probe_failure_retain.py"),
    "subset_probe": Path("experiments/e17a_subset_probe.py"),
    "second_successor_freeze": Path("experiments/e17a_second_successor_freeze.py"),
    "second_successor_ingest": Path("experiments/e17a_second_successor_ingest.py"),
    "second_successor_test": Path("tests/test_e17a_second_successor.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    first_successor = load_object(
        root / SECOND_SUCCESSOR_INPUT_PATHS["first_successor_contract"]
    )
    failure = load_object(root / SECOND_SUCCESSOR_INPUT_PATHS["second_failure_manifest"])
    if (
        first_successor.get("experiment_id") != "E17a"
        or failure.get("status")
        != "invalid_premeasurement_subset_reference_probe_failure"
        or failure.get("configuration_processes_started") != 3
        or failure.get("configuration_processes_ready") != 3
        or failure.get("measured_model_requests_completed") != 0
        or failure.get("decision", {}).get(
            "separately_frozen_subset_probe_repair_allowed"
        )
        is not True
    ):
        raise ValueError("E17a second-successor prerequisite differs")

    contract = copy.deepcopy(first_successor)
    contract["inputs"]["cell_sha256"] = sha256_file(
        root / Path(contract["inputs"]["cell_path"])
    )
    for name, relative in SECOND_SUCCESSOR_INPUT_PATHS.items():
        contract["inputs"][f"{name}_path"] = relative.as_posix()
        contract["inputs"][f"{name}_sha256"] = sha256_file(root / relative)
    contract["state"] = (
        "separately frozen after retaining the pre-request subset-reference failure, "
        "before any measured request or compatibility result"
    )
    contract["second_failure"] = {
        "run_id": failure["github"]["run_id"],
        "run_attempt": failure["github"]["run_attempt"],
        "repository_commit": failure["github"]["repository_commit"],
        "artifact_name": failure["github"]["artifact_name"],
        "artifact_id": failure["github"]["artifact_id"],
        "artifact_digest": failure["github"]["artifact_digest"],
        "manifest_sha256": sha256_file(
            root / SECOND_SUCCESSOR_INPUT_PATHS["second_failure_manifest"]
        ),
        "configuration_processes_ready": 3,
        "measured_model_requests_completed": 0,
        "repair": [
            "load the unchanged stable 30-task reference prediction map",
            "filter it to the three already-frozen E17a task IDs",
            "call the unchanged E5b HTTP request engine with that exact subset",
        ],
    }
    contract["decision"]["second_failure_rehabilitated"] = False
    contract["decision"]["second_successor_changes_scientific_contract"] = False
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
