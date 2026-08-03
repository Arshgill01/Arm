#!/usr/bin/env python3
"""Retain E18a's invalid instrumented-training timeout boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file


RUN_ID = 30858852227
JOB_ID = 91836129170
HEAD_SHA = "9718cbff72f76a343757ae1fffc858507b08e574"
ARTIFACT_ID = 8874332881
ARTIFACT_NAME = "e18a-workload-pgo-30858852227-1"
ARTIFACT_DIGEST = (
    "sha256:a182313fe7a1c0fd2557daadcec71b043ada74de3446c173644974f00727dbf1"
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
    artifacts = load_object(artifact_metadata).get("artifacts", [])
    selected = [item for item in artifacts if item.get("id") == ARTIFACT_ID]
    failed = [step for step in job.get("steps", []) if step.get("conclusion") == "failure"]
    if (
        run.get("id") != RUN_ID
        or run.get("run_attempt") != 1
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("head_sha") != HEAD_SHA
        or job.get("id") != JOB_ID
        or job.get("status") != "completed"
        or job.get("conclusion") != "failure"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or len(failed) != 1
        or failed[0].get("name") != "Independently validate complete PGO evidence"
        or len(selected) != 1
        or selected[0].get("name") != ARTIFACT_NAME
        or selected[0].get("digest") != ARTIFACT_DIGEST
        or selected[0].get("expired") is not False
    ):
        raise ValueError("E18a training-timeout GitHub identity differs")
    for name in (
        "Build exact Release control",
        "Generate exact workload profile",
        "Build workload-trained PGO binary in the same directory",
        "Run all twelve frozen fresh-process service cells",
    ):
        matches = [step for step in job["steps"] if step.get("name") == name]
        if len(matches) != 1 or matches[0].get("conclusion") != "success":
            raise ValueError(f"E18a completed boundary differs for {name}")

    contract_path = root / "experiments/e18a_contract.json"
    contract = load_object(contract_path)
    if (
        contract.get("experiment_id") != "E18a"
        or load_object(evidence / "contract.json") != contract
        or sha256_file(contract_path)
        != "649f95192ca2a9c063cde9ddafcc211693bd09e5150726f1c8f3223dea51e09c"
    ):
        raise ValueError("E18a training-timeout contract differs")
    verified_inputs = 0
    for key, relative in contract["inputs"].items():
        if not key.endswith("_path"):
            continue
        expected = contract["inputs"][key.replace("_path", "_sha256")]
        if (
            sha256_file(root / relative) != expected
            or sha256_file(evidence / "frozen-inputs" / relative) != expected
        ):
            raise ValueError(f"E18a training-timeout input differs: {relative}")
        verified_inputs += 1

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    probe = load_object(evidence / "training/probe.json")
    warmups = probe.get("warmups")
    cases = probe.get("cases")
    if (
        platform["architecture"] != "aarch64"
        or not isinstance(warmups, list)
        or len(warmups) != 2
        or not isinstance(cases, list)
        or len(cases) != 30
        or probe.get("parameters", {}).get("timeout_seconds") != 30.0
        or probe.get("parameters", {}).get("configuration") != "pgo_training"
    ):
        raise ValueError("E18a training-timeout workload differs")
    timed_out_warmups = [item for item in warmups if item.get("error") == "TimeoutError: timed out"]
    timed_out_cases = [item for item in cases if item.get("error") == "TimeoutError: timed out"]
    successful_cases = [item for item in cases if item.get("status") == 200]
    if (
        len(timed_out_warmups) != 2
        or len(timed_out_cases) != 28
        or [item.get("id") for item in successful_cases]
        != ["arithmetic-02", "logic-01"]
        or any(item.get("error") is not None for item in successful_cases)
        or probe.get("result", {}).get("failures") != 28
        or probe.get("result", {}).get("correct") != 2
        or probe.get("result", {}).get("status_counts") != {"200": 2}
    ):
        raise ValueError("E18a instrumented-training timeout evidence differs")

    profile = load_object(evidence / "pgo-profile-inventory.json")
    if (
        profile.get("file_count", 0) < contract["training"]["minimum_gcda_files"]
        or profile.get("total_size_bytes", 0) <= 0
        or not (evidence / "builds/release_control/runtime-closure.json").is_file()
        or not (evidence / "builds/workload_pgo/runtime-closure.json").is_file()
        or len(list((evidence / "cells").glob("*"))) != 12
        or (evidence / "summary.json").exists()
    ):
        raise ValueError("E18a post-training evidence boundary differs")
    log = job_log.read_text(errors="replace")
    if (
        "ValueError: invalid inference response for arithmetic-02" not in log
        or "experiments/e18a_ingest.py" not in log
    ):
        raise ValueError("E18a validation failure log differs")
    artifact = selected[0]
    return {
        "schema_version": 1,
        "experiment_id": "E18a",
        "status": "invalid_instrumented_training_timeout_after_complete_matrix",
        "experiment_result_valid": False,
        "promotion_decision_permitted": False,
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "validated_before_failure": {
            "native_arm64": True,
            "exact_contract": True,
            "frozen_inputs_verified": verified_inputs,
            "release_control_built": True,
            "instrumented_binary_built": True,
            "pgo_use_binary_built": True,
            "all_twelve_measured_cells_completed": True,
            "profile_file_count": profile["file_count"],
            "profile_total_size_bytes": profile["total_size_bytes"],
        },
        "failure": {
            "stage": "independent instrumented-training validation",
            "type": "frozen_request_timeout_exceeded_under_profile_generation",
            "training_warmups_timed_out": len(timed_out_warmups),
            "training_measured_requests": len(cases),
            "training_requests_timed_out": len(timed_out_cases),
            "training_requests_succeeded": len(successful_cases),
            "training_timeout_seconds": 30.0,
            "training_result_matches_selected_quality": False,
            "measured_matrix_eligible_for_performance_claim": False,
            "reason": (
                "The frozen profile-generation pass did not complete the exact "
                "30-task workload. The resulting profile is incomplete, so the later "
                "PGO-use measurements cannot answer the frozen experiment."
            ),
            "repair_boundary": (
                "A separately frozen successor may raise only the non-performance "
                "instrumented-training request timeout while retaining the exact "
                "source, model, profile flags, workload, service, build directories, "
                "measurement order, repetitions, acceptance gates, and claim boundary."
            ),
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
            "job_log_sha256": sha256_file(job_log),
        },
        "artifact_validation": inventory(evidence),
        "decision": {
            "pgo_result_accepted": False,
            "failed_run_rehabilitated": False,
            "measured_results_inspected_for_gate_changes": False,
            "separately_frozen_training_timeout_successor_allowed": True,
        },
        "claim_boundary": (
            "The complete measured matrix is ineligible because its profile-training "
            "prerequisite failed. This run provides no PGO performance, footprint, "
            "quality, energy, PMU, device, fleet, or cost result."
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
