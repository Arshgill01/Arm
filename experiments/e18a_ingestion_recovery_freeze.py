#!/usr/bin/env python3
"""Freeze E18a's inspection-only deterministic ingestion recovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


INPUT_PATHS = {
    "failure_manifest": Path(
        "results/manifests/e18a-successor-ingestion-failure-30861416953.json"
    ),
    "source_contract": Path("experiments/e18a_successor_contract.json"),
    "base_ingest": Path("experiments/e18a_ingest.py"),
    "fixed_ingest": Path("experiments/e18a_successor_ingest.py"),
    "failure_retain": Path("experiments/e18a_ingestion_failure_retain.py"),
    "recovery": Path("experiments/e18a_ingestion_recovery.py"),
    "freeze": Path("experiments/e18a_ingestion_recovery_freeze.py"),
    "successor_test": Path("tests/test_e18a_successor.py"),
    "recovery_test": Path("tests/test_e18a_ingestion_recovery.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    failure = load_object(root / INPUT_PATHS["failure_manifest"])
    preview = failure.get("corrected_replay_preview", {})
    if (
        failure.get("status")
        != "invalid_post_measurement_ingestion_failure_with_complete_replay"
        or failure.get("decision", {}).get("inspection_only_native_recovery_allowed")
        is not True
        or preview.get("status") != "valid_workload_pgo_no_win"
        or preview.get("hypothesis", {}).get("passed") is not False
        or preview.get("hypothesis", {}).get("selected_profile")
        != "release_control"
    ):
        raise ValueError("E18a ingestion recovery prerequisite differs")
    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    github = failure["github"]
    return {
        "schema_version": 1,
        "experiment_id": "E18a-ingestion-recovery",
        "title": "Inspection-only recovery of complete workload-PGO evidence",
        "state": (
            "frozen after the validator-only workflow failure and a local Python "
            "3.10 deterministic replay exposed the unchanged no-win, before the "
            "native recovery replays or retains that result"
        ),
        "inputs": inputs,
        "source": {
            "run_id": str(github["run_id"]),
            "run_attempt": github["run_attempt"],
            "job_id": str(github["job_id"]),
            "repository_commit": github["repository_commit"],
            "artifact_id": github["artifact_id"],
            "artifact_name": github["artifact_name"],
            "artifact_digest": github["artifact_digest"],
            "artifact_size_bytes": github["artifact_size_bytes"],
            "failure_status": failure["status"],
            "source_workflow_remains_invalid": True,
        },
        "expected_result": {
            "summary_sha256": preview["summary_sha256"],
            "status": preview["status"],
            "hypothesis_passed": False,
            "selected_profile": "release_control",
            "hypothesis": preview["hypothesis"],
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "required_architecture": "aarch64",
            "python_version": "3.10.20",
            "allowed_operations": [
                "download exact source artifact",
                "verify every extracted regular file",
                "query source run job and artifact metadata",
                "run corrected deterministic ingester",
                "write compact recovery evidence",
            ],
            "forbidden_operations": [
                "clone or build llama.cpp",
                "download a model",
                "generate or consume a new PGO profile",
                "launch llama-server",
                "rerun any service cell",
                "change source model service order repetitions or gates",
            ],
        },
        "acceptance": {
            "all_source_artifact_files_match_retained_inventory": True,
            "live_source_run_job_and_artifact_identity_match": True,
            "recovered_summary_sha256_exact": preview["summary_sha256"],
            "recovered_status_exact": preview["status"],
            "recovered_hypothesis_exact": preview["hypothesis"],
            "no_measurement_or_build_step": True,
        },
        "decision": {
            "accept_recovered_result_only_if_every_gate_passes": True,
            "pgo_promotion_expected": False,
            "failed_workflow_rehabilitated": False,
            "gate_change_allowed": False,
            "additional_measurement_allowed": False,
        },
        "negative_result_rule": (
            "Retain any source-file, GitHub identity, Python, deterministic summary, "
            "status, hypothesis, or selected-profile mismatch and stop without "
            "rebuilding, remeasuring, or changing the expected result."
        ),
        "claim_boundary": (
            "This recovery can validate only the deterministic interpretation of "
            "the exact completed native measurements in source run 30861416953. It "
            "adds no measurement and makes no generic PGO, other-model, long-context, "
            "fleet, energy, PMU, local-device, or cost claim."
        ),
    }


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
