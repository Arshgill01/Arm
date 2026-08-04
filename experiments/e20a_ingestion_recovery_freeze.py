#!/usr/bin/env python3
"""Freeze E20a's inspection-only deterministic selector recovery."""

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
    "failure_manifest": Path("results/manifests/e20a-ingestion-failure-30863505489.json"),
    "source_contract": Path("experiments/e20a_contract.json"),
    "fixed_ingest": Path("experiments/e20a_ingest.py"),
    "failure_retain": Path("experiments/e20a_ingestion_failure_retain.py"),
    "recovery": Path("experiments/e20a_ingestion_recovery.py"),
    "freeze": Path("experiments/e20a_ingestion_recovery_freeze.py"),
    "source_test": Path("tests/test_e20a.py"),
    "recovery_test": Path("tests/test_e20a_ingestion_recovery.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    failure = load_object(root / INPUT_PATHS["failure_manifest"])
    preview = failure.get("corrected_replay_preview", {})
    selection = preview.get("selection", {})
    if (
        failure.get("status")
        != "invalid_post_profile_ingestion_failure_with_complete_replay"
        or failure.get("decision", {}).get("inspection_only_native_recovery_allowed")
        is not True
        or preview.get("status") != "valid_cpu_node_profile_fusion_candidate"
        or selection.get("selected_family") != "ffn_gate_up"
        or selection.get("automatic_source_optimization_allowed") is not False
    ):
        raise ValueError("E20a recovery prerequisite differs")
    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    github = failure["github"]
    return {
        "schema_version": 1,
        "experiment_id": "E20a-ingestion-recovery",
        "title": "Inspection-only recovery of complete graph-node profile",
        "state": (
            "frozen after the validator-only failure and local Python 3.12 replay "
            "exposed the deterministic FFN gate/up selection, before native recovery"
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
            "source_workflow_remains_invalid": True,
        },
        "expected_result": {
            "summary_sha256": preview["summary_sha256"],
            "status": preview["status"],
            "quality": preview["quality"],
            "selection": selection,
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "required_architecture": "aarch64",
            "python_version": "3.12.13",
            "allowed_operations": [
                "download exact source artifact",
                "verify every extracted regular file",
                "query exact source GitHub identities",
                "run corrected deterministic selector",
                "write compact recovery evidence",
            ],
            "forbidden_operations": [
                "clone or build llama.cpp",
                "download a model",
                "launch llama-bench or llama-server",
                "repeat any benchmark or quality request",
                "change family threshold selection modes or quality gate",
            ],
        },
        "acceptance": {
            "all_source_artifact_files_match_retained_inventory": True,
            "live_source_run_job_and_artifact_identity_match": True,
            "recovered_summary_sha256_exact": preview["summary_sha256"],
            "recovered_status_exact": preview["status"],
            "recovered_quality_exact": preview["quality"],
            "recovered_selection_exact": selection,
            "no_measurement_or_build_step": True,
        },
        "decision": {
            "failed_workflow_rehabilitated": False,
            "fusion_implementation_allowed_before_recovery": False,
            "automatic_source_optimization_allowed": False,
            "separate_focused_source_contract_required_after_recovery": True,
        },
        "negative_result_rule": (
            "Retain any artifact, identity, interpreter, summary, quality, family, "
            "share, shared-layer, or threshold mismatch and stop without remeasurement."
        ),
        "claim_boundary": (
            "This recovery can validate only the deterministic target selection from "
            "the exact completed E20a software-timing artifact. Timed traces include "
            "instrumentation overhead and cannot support service-speed, PMU, cache, "
            "energy, fleet, cost, or optimization-win claims. Any FFN gate/up source "
            "work requires a separate frozen implementation and end-to-end service gate."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_contract(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
