#!/usr/bin/env python3
"""Retain E18a's premeasurement relative-patch-path failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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


RUN_ID = "30858644241"
JOB_ID = "91835461038"
ARTIFACT_ID = "8873443762"
ARTIFACT_NAME = "e18a-workload-pgo-30858644241-1"
ARTIFACT_DIGEST = (
    "sha256:2a3b2f74caa49109db5ded16fb2c07c2fa6126866bdd54f838fc5ed66fa10bb8"
)
SUPPLEMENTAL = {
    "github-artifact.json",
    "github-job.json",
    "github-run.json",
    "github-run.log",
}


def git_blob(root: Path, commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def inventory(evidence: Path) -> dict[str, Any]:
    files = []
    total = 0
    for path in sorted(
        (item for item in evidence.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(evidence).as_posix(),
    ):
        relative = path.relative_to(evidence).as_posix()
        if relative in SUPPLEMENTAL:
            continue
        size = path.stat().st_size
        files.append(
            {"path": relative, "size_bytes": size, "sha256": sha256_file(path)}
        )
        total += size
    return {
        "file_count": len(files),
        "total_regular_file_bytes": total,
        "all_extracted_regular_files_hashed": True,
        "files": files,
    }


def retain(evidence: Path, root: Path) -> dict[str, Any]:
    run = load_object(evidence / "github-run.json")
    job = load_object(evidence / "github-job.json")
    artifact = load_object(evidence / "github-artifact.json")
    jobs = run.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 1:
        raise ValueError("E18a failure run metadata differs")
    summary_job = jobs[0]
    failed_steps = [
        step
        for step in summary_job.get("steps", [])
        if step.get("conclusion") == "failure"
    ]
    if (
        str(run.get("databaseId")) != RUN_ID
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or str(summary_job.get("databaseId")) != JOB_ID
        or len(failed_steps) != 1
        or failed_steps[0].get("name") != "Pin patched source and selected model"
        or str(job.get("id")) != JOB_ID
        or job.get("conclusion") != "failure"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or artifact.get("id") != int(ARTIFACT_ID)
        or artifact.get("name") != ARTIFACT_NAME
        or artifact.get("digest") != ARTIFACT_DIGEST
    ):
        raise ValueError("E18a failure identity differs")

    commit = run["headSha"]
    contract_relative = "experiments/e18a_contract.json"
    contract_bytes = git_blob(root, commit, contract_relative)
    contract = json.loads(contract_bytes)
    if (
        contract.get("experiment_id") != "E18a"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E18a failure contract differs")
    verified_inputs = 0
    for key, relative in contract["inputs"].items():
        if not key.endswith("_path"):
            continue
        expected = contract["inputs"][key.replace("_path", "_sha256")]
        artifact_path = evidence / "frozen-inputs" / relative
        if (
            sha256_bytes(git_blob(root, commit, relative)) != expected
            or sha256_file(artifact_path) != expected
        ):
            raise ValueError(f"E18a failure input differs: {relative}")
        verified_inputs += 1

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    log = (evidence / "github-run.log").read_text(errors="replace")
    if (
        platform["architecture"] != "aarch64"
        or "error: can't open patch 'patches/llama.cpp/b10216/" not in log
        or "No such file or directory" not in log
        or (evidence / "source.json").exists()
        or (evidence / "model-sha256.txt").exists()
        or (evidence / "pgo-profile-inventory.json").exists()
        or (evidence / "summary.json").exists()
        or (evidence / "cells").exists()
    ):
        raise ValueError("E18a premeasurement failure boundary differs")

    return {
        "schema_version": 1,
        "experiment_id": "E18a",
        "status": "invalid_premeasurement_relative_patch_path_failure",
        "experiment_result_valid": False,
        "promotion_decision_permitted": False,
        "contract_sha256": sha256_bytes(contract_bytes),
        "platform": platform,
        "validated_before_failure": {
            "native_arm64": True,
            "exact_contract": True,
            "frozen_inputs_verified": verified_inputs,
            "source_commit_checked_out": True,
        },
        "failure": {
            "stage": "first source patch application",
            "message": (
                "git -C changed the patch-path resolution base to the cloned source, "
                "so the repository-relative patch path could not be opened"
            ),
            "source_patches_applied": 0,
            "model_downloaded": False,
            "builds_started": 0,
            "profile_training_started": False,
            "measured_processes_started": 0,
            "measured_requests_completed": 0,
            "repair_boundary": (
                "Resolve each unchanged contract patch path against GITHUB_WORKSPACE. "
                "Do not change the PGO mechanism, workload, order, repetitions, gates, "
                "source, model, service, or claim boundary."
            ),
        },
        "github": {
            "run_id": RUN_ID,
            "run_attempt": 1,
            "run_url": run["url"],
            "job_id": JOB_ID,
            "repository_commit": commit,
            "artifact_id": ARTIFACT_ID,
            "artifact_name": ARTIFACT_NAME,
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": ARTIFACT_DIGEST,
            "run_log_sha256": sha256_file(evidence / "github-run.log"),
        },
        "artifact_validation": inventory(evidence),
        "decision": {
            "pgo_result_accepted": False,
            "failed_run_rehabilitated": False,
            "exact_contract_retry_after_path_repair_allowed": True,
        },
        "claim_boundary": (
            "No compiler build, PGO training, model request, or measured service process "
            "started. This run provides no PGO, quality, performance, memory, energy, "
            "PMU, device, fleet, or cost result."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(args.evidence_dir, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
