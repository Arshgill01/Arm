#!/usr/bin/env python3
"""Retain E18a's validator-only failure after all measurements completed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e18a_successor_ingest import build_manifest
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file
    from e18a_successor_ingest import build_manifest


RUN_ID = 30861416953
JOB_ID = 91844009646
HEAD_SHA = "12d19a04cf9c8e1e7ceb53d5b61de43746527977"
ARTIFACT_ID = 8875533121
ARTIFACT_NAME = "e18a-workload-pgo-30861416953-1"
ARTIFACT_DIGEST = (
    "sha256:eaa2f669b7a208e6b9ac0a4b16fd5b79411f8314baee0aa98f719c99d27110fd"
)


def inventory(evidence: Path) -> dict[str, Any]:
    files = []
    total = 0
    for path in sorted(
        (item for item in evidence.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(evidence).as_posix(),
    ):
        size = path.stat().st_size
        files.append(
            {
                "path": path.relative_to(evidence).as_posix(),
                "size_bytes": size,
                "sha256": sha256_file(path),
            }
        )
        total += size
    return {
        "file_count": len(files),
        "total_regular_file_bytes": total,
        "all_extracted_regular_files_hashed": True,
        "files": files,
    }


def validate_github(
    run: dict[str, Any],
    job: dict[str, Any],
    artifact_metadata: dict[str, Any],
) -> dict[str, Any]:
    selected = [
        item
        for item in artifact_metadata.get("artifacts", [])
        if item.get("id") == ARTIFACT_ID
    ]
    failed = [step for step in job.get("steps", []) if step.get("conclusion") == "failure"]
    if (
        run.get("id") != RUN_ID
        or run.get("run_attempt") != 1
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("head_sha") != HEAD_SHA
        or job.get("id") != JOB_ID
        or job.get("run_id") != RUN_ID
        or job.get("status") != "completed"
        or job.get("conclusion") != "failure"
        or job.get("head_sha") != HEAD_SHA
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or len(failed) != 1
        or failed[0].get("name") != "Independently validate complete PGO evidence"
        or len(selected) != 1
        or selected[0].get("name") != ARTIFACT_NAME
        or selected[0].get("digest") != ARTIFACT_DIGEST
        or selected[0].get("expired") is not False
        or selected[0].get("workflow_run", {}).get("head_sha") != HEAD_SHA
        or selected[0].get("workflow_run", {}).get("id") != RUN_ID
    ):
        raise ValueError("E18a successor GitHub identity differs")
    required = (
        "Build exact Release control",
        "Generate exact workload profile",
        "Build workload-trained PGO binary in the same directory",
        "Run all twelve frozen fresh-process service cells",
        "Upload complete E18a PGO evidence",
    )
    for name in required:
        matches = [step for step in job["steps"] if step.get("name") == name]
        if len(matches) != 1 or matches[0].get("conclusion") != "success":
            raise ValueError(f"E18a successor completed boundary differs for {name}")
    return selected[0]


def retain(
    *,
    evidence: Path,
    root: Path,
    run_metadata: Path,
    job_metadata: Path,
    artifact_metadata: Path,
    job_log: Path,
) -> dict[str, Any]:
    run = load_object(run_metadata)
    job = load_object(job_metadata)
    artifact = validate_github(run, job, load_object(artifact_metadata))
    contract_path = root / "experiments/e18a_successor_contract.json"
    contract = load_object(contract_path)
    if (
        contract.get("experiment_id") != "E18a"
        or contract.get("campaign_variant") != "training-timeout-successor"
        or sha256_file(contract_path)
        != "0069ca34c075c068beea1102e26a80725afc9cb9db56677e4af09fa125cbdc36"
        or load_object(evidence / "contract.json") != contract
        or (evidence / "summary.json").exists()
        or (evidence / "file-inventory-sha256.txt").exists()
    ):
        raise ValueError("E18a successor failure contract boundary differs")

    changed_recovery_inputs = {"successor_ingest", "successor_test"}
    verified_inputs = 0
    for key, relative in contract["inputs"].items():
        if not key.endswith("_path"):
            continue
        name = key.removesuffix("_path")
        expected = contract["inputs"][f"{name}_sha256"]
        if sha256_file(evidence / "frozen-inputs" / relative) != expected:
            raise ValueError(f"E18a frozen source input differs: {relative}")
        if name not in changed_recovery_inputs and sha256_file(root / relative) != expected:
            raise ValueError(f"E18a retained repository input differs: {relative}")
        verified_inputs += 1

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    profile = load_object(evidence / "pgo-profile-inventory.json")
    provenance = load_object(evidence / "provenance.json")
    if (
        platform["architecture"] != "aarch64"
        or profile.get("file_count") != 305
        or profile.get("total_size_bytes", 0) <= 0
        or provenance.get("github_run_id") != str(RUN_ID)
        or provenance.get("github_run_attempt") != "1"
        or len(list((evidence / "cells").glob("*"))) != 12
    ):
        raise ValueError("E18a successor measured evidence boundary differs")

    log = job_log.read_text(errors="replace")
    if (
        "ValueError: E18a successor timeout boundary differs" not in log
        or "experiments/e18a_successor_ingest.py" not in log
        or "Independently validate complete PGO evidence" not in log
    ):
        raise ValueError("E18a successor failure log differs")

    replay = build_manifest(evidence, contract_path, root)
    replay_bytes = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    if (
        replay.get("status") != "valid_workload_pgo_no_win"
        or replay.get("campaign_variant") != "training-timeout-successor"
        or replay.get("decision", {}).get("failed_predecessor_rehabilitated") is not False
        or len(replay.get("performance", {}).get("release_control", {}).get("repetitions", [])) != 6
        or len(replay.get("performance", {}).get("workload_pgo", {}).get("repetitions", [])) != 6
        or replay.get("hypothesis", {}).get("passed") is not False
    ):
        raise ValueError("E18a corrected deterministic replay differs")

    return {
        "schema_version": 1,
        "experiment_id": "E18a",
        "status": "invalid_post_measurement_ingestion_failure_with_complete_replay",
        "experiment_result_valid": False,
        "promotion_decision_permitted": False,
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "validated_before_failure": {
            "native_arm64": True,
            "exact_contract": True,
            "frozen_inputs_verified": verified_inputs,
            "release_control_built": True,
            "complete_instrumented_training_pass": True,
            "pgo_use_binary_built": True,
            "all_twelve_measured_cells_completed": True,
            "profile_file_count": profile["file_count"],
            "profile_total_size_bytes": profile["total_size_bytes"],
        },
        "failure": {
            "stage": "independent post-measurement ingestion",
            "type": "recursive_successor_training_adapter",
            "scientific_measurement_failure": False,
            "raw_measurements_complete": True,
            "workflow_summary_written": False,
            "workflow_inventory_written": False,
            "reason": (
                "The successor ingester temporarily replaced the base training "
                "validator and then called that replaced symbol from its adapter, "
                "recursing into the successor-only timeout guard."
            ),
            "additional_replay_bug": (
                "After correcting the recursion, deterministic replay exposed a "
                "second output-only bug: the successor assigned into a missing "
                "decision object. The recovery fixes both validator/output defects."
            ),
        },
        "corrected_replay_preview": {
            "python_line": "3.10",
            "summary_sha256": hashlib.sha256(replay_bytes).hexdigest(),
            "status": replay["status"],
            "hypothesis": replay["hypothesis"],
            "quality_preserved": replay["hypothesis"]["gates"]["quality"],
            "performance_repetitions_per_profile": 6,
            "preview_is_product_evidence": False,
        },
        "github": {
            "run_id": RUN_ID,
            "run_attempt": 1,
            "run_url": run["html_url"],
            "job_id": JOB_ID,
            "repository_commit": HEAD_SHA,
            "artifact_id": str(ARTIFACT_ID),
            "artifact_name": ARTIFACT_NAME,
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": ARTIFACT_DIGEST,
            "artifact_expires_at": artifact["expires_at"],
            "job_log_sha256": sha256_file(job_log),
        },
        "artifact_validation": inventory(evidence),
        "decision": {
            "pgo_result_accepted_from_failed_workflow": False,
            "failed_workflow_rehabilitated": False,
            "measured_cells_may_be_rerun_in_recovery": False,
            "source_build_model_or_gates_may_change_in_recovery": False,
            "inspection_only_native_recovery_allowed": True,
        },
        "claim_boundary": (
            "This failed workflow makes no PGO performance claim. A separately "
            "frozen inspection-only recovery may download the exact artifact, verify "
            "every extracted file, and run only the corrected deterministic ingester. "
            "It may not rebuild, redownload the model, rerun training or service "
            "cells, change gates, or rehabilitate the failed workflow itself."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--job-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--job-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        evidence=args.evidence_dir,
        root=args.root,
        run_metadata=args.run_metadata,
        job_metadata=args.job_metadata,
        artifact_metadata=args.artifact_metadata,
        job_log=args.job_log,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
