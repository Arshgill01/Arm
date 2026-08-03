#!/usr/bin/env python3
"""Retain E17a's premeasurement cell-script permission failure."""

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


RUN_ID = "30855155720"
JOB_ID = "91824331649"
ARTIFACT_ID = "8872171485"
ARTIFACT_NAME = "e17a-kv-v-cache-preflight-30855155720-1"
ARTIFACT_DIGEST = "sha256:a3c09e979f6f49a1948d9d2979585db3425b024d7ff80a93c74b81d3efefd487"

SUPPLEMENTAL = {
    "artifact-inventory-sha256.txt",
    "github-artifact.json",
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


def artifact_inventory(evidence: Path) -> dict[str, Any]:
    entries: list[str] = []
    total_bytes = 0
    files = (item for item in evidence.rglob("*") if item.is_file())
    for item in sorted(files, key=lambda value: value.relative_to(evidence).as_posix()):
        relative = item.relative_to(evidence).as_posix()
        if relative in SUPPLEMENTAL:
            continue
        entries.append(f"{sha256_file(item)}  {relative}\n")
        total_bytes += item.stat().st_size
    inventory = evidence / "artifact-inventory-sha256.txt"
    if inventory.read_text() != "".join(entries):
        raise ValueError("E17a failure artifact inventory differs")
    return {
        "file_count": len(entries),
        "total_regular_file_bytes": total_bytes,
        "inventory_sha256": sha256_file(inventory),
        "all_extracted_regular_files_hashed": True,
    }


def build_manifest(evidence: Path, contract_relative: str, root: Path) -> dict[str, Any]:
    run = load_object(evidence / "github-run.json")
    artifact = load_object(evidence / "github-artifact.json")
    jobs = run.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 1:
        raise ValueError("E17a failure job metadata differs")
    job = jobs[0]
    failed_steps = [
        step for step in job.get("steps", []) if step.get("conclusion") == "failure"
    ]
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or str(job.get("databaseId")) != JOB_ID
        or len(failed_steps) != 1
        or failed_steps[0].get("name") != "Run all three frozen compatibility cells"
        or artifact.get("id") != int(ARTIFACT_ID)
        or artifact.get("name") != ARTIFACT_NAME
        or artifact.get("digest") != ARTIFACT_DIGEST
    ):
        raise ValueError("E17a failure provenance differs")

    contract_bytes = git_blob(root, run["headSha"], contract_relative)
    contract = json.loads(contract_bytes)
    if contract.get("experiment_id") != "E17a" or load_object(evidence / "contract.json") != contract:
        raise ValueError("E17a failure contract differs")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E17a failure is not native Arm64")
    model_digest = (evidence / "model-sha256.txt").read_text().split()
    log = (evidence / "github-run.log").read_text(errors="replace")
    if (
        len(model_digest) != 2
        or model_digest[0] != contract["selected"]["model_sha256"]
        or "e17a_kv_preflight_cell.sh: Permission denied" not in log
        or "cells/01-f16_f16/caller-exit.txt: No such file or directory" not in log
        or (evidence / "cells").exists()
        or (evidence / "summary.json").exists()
    ):
        raise ValueError("E17a premeasurement failure boundary differs")

    return {
        "schema_version": 1,
        "experiment_id": "E17a",
        "status": "invalid_premeasurement_cell_permission_failure",
        "experiment_result_valid": False,
        "configuration_attempts_started": 0,
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "platform": platform,
        "validated_before_failure": {
            "exact_contract_and_inputs": True,
            "exact_e9a_runtime_closure": True,
            "native_server_launchable": True,
            "exact_selected_model_downloaded": True,
        },
        "failure": {
            "stage": "pre-cell shell invocation",
            "exception": "experiments/e17a_kv_preflight_cell.sh: Permission denied",
            "cause": (
                "The new cell runner was stored without an executable mode. The wrapper "
                "then attempted to write caller-exit.txt before the cell directory existed."
            ),
            "repair_boundary": (
                "A separately committed successor may invoke the exact hash-bound runner "
                "through bash and create the expected cell directory before invocation. "
                "No contract, runtime, model, configuration, order, task, request, gate, "
                "or selection rule may change."
            ),
        },
        "github": {
            "run_id": RUN_ID,
            "run_attempt": 1,
            "run_url": run["url"],
            "job_id": JOB_ID,
            "repository_commit": run["headSha"],
            "artifact_name": ARTIFACT_NAME,
            "artifact_id": ARTIFACT_ID,
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": ARTIFACT_DIGEST,
            "run_log_sha256": sha256_file(evidence / "github-run.log"),
        },
        "artifact_validation": artifact_inventory(evidence),
        "decision": {
            "compatibility_result_accepted": False,
            "long_context_successor_allowed": False,
            "failed_run_rehabilitated": False,
            "separately_committed_shell_invocation_repair_allowed": True,
        },
        "claim_boundary": (
            "No configuration process or model request started. This run provides no "
            "KV compatibility, allocation, answer, quality, performance, long-context, "
            "energy, PMU, device, fleet, or cost result."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract-relative", default="experiments/e17a_contract.json")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract_relative, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
