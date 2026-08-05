#!/usr/bin/env python3
"""Bind the independently replayed E20c no-win to its GitHub artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e20c_ingest import build_manifest
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e20c_ingest import build_manifest


RUN_ID = 30870229218
JOB_ID = 91870547126
ARTIFACT_ID = 8877825372
ARTIFACT_NAME = "e20c-repack-pair-30870229218-1"
ARTIFACT_DIGEST = (
    "sha256:22175f3be8da0c3009e9573a0a7385cf4ea9acec7343a4486ebd8d4f01f62fbb"
)
HEAD_SHA = "10dc5b02630e3950e5850da7db67d28c8cb68b83"
INVENTORY_FILES = 195
ARTIFACT_ROOT = f"/results/raw/e20c-{RUN_ID}-1/"


def validate_workflow_inventory(evidence: Path) -> dict[str, Any]:
    inventory = evidence / "file-inventory-sha256.txt"
    entries: dict[str, str] = {}
    for line in inventory.read_text().splitlines():
        digest, separator, absolute = line.partition("  ")
        if (
            not separator
            or len(digest) != 64
            or ARTIFACT_ROOT not in absolute
        ):
            raise ValueError("E20c workflow inventory line differs")
        relative = absolute.split(ARTIFACT_ROOT, 1)[1]
        if relative in entries:
            raise ValueError("E20c workflow inventory repeats a path")
        path = evidence / relative
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"E20c workflow inventory differs for {relative}")
        entries[relative] = digest
    required = {
        "contract.json",
        "summary.json",
        "source-diff.patch",
        "build/runtime-closure.json",
        "preflight/reuse_off/stderr.log",
        "preflight/reuse_on/stderr.log",
        "cells/safety-reuse_on-r7/probe.json",
        "cells/01-reuse_off-r1/probe.json",
        "cells/12-reuse_off-r6/probe.json",
    }
    if len(entries) != INVENTORY_FILES or not required.issubset(entries):
        raise ValueError("E20c workflow inventory is incomplete")
    return {
        "hashed_files": len(entries),
        "sha256": sha256_file(inventory),
        "entries": entries,
    }


def retain(
    evidence: Path,
    contract: Path,
    root: Path,
    run_metadata: Path,
    artifact_metadata: Path,
) -> dict[str, Any]:
    replay = build_manifest(evidence, contract, root)
    replay_bytes = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    workflow_summary = evidence / "summary.json"
    if replay_bytes != workflow_summary.read_bytes():
        raise ValueError("E20c independent replay differs")
    run = load_object(run_metadata)
    artifacts = load_object(artifact_metadata).get("artifacts", [])
    selected = [item for item in artifacts if item.get("id") == ARTIFACT_ID]
    jobs = run.get("jobs", [])
    if (
        str(run.get("databaseId")) != str(RUN_ID)
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("headSha") != HEAD_SHA
        or len(jobs) != 1
        or jobs[0].get("databaseId") != JOB_ID
        or jobs[0].get("conclusion") != "success"
        or len(selected) != 1
        or selected[0].get("name") != ARTIFACT_NAME
        or selected[0].get("digest") != ARTIFACT_DIGEST
        or selected[0].get("expired") is not False
        or str(selected[0].get("workflow_run", {}).get("id")) != str(RUN_ID)
        or selected[0].get("workflow_run", {}).get("head_sha") != HEAD_SHA
        or replay.get("status") != "valid_guarded_repack_pair_reuse_no_win"
        or replay.get("hypothesis", {}).get("passed") is not False
        or replay.get("hypothesis", {}).get("quality_passed") is not True
        or replay.get("validation", {}).get(
            "candidate_full_service_safety_preflight_passed"
        )
        is not True
    ):
        raise ValueError("E20c retained identity or decision differs")
    inventory = validate_workflow_inventory(evidence)
    artifact = selected[0]
    return {
        **replay,
        "github": {
            "run_id": str(RUN_ID),
            "run_attempt": 1,
            "run_url": run["url"],
            "repository_commit": HEAD_SHA,
            "job_id": str(JOB_ID),
            "artifact_id": str(ARTIFACT_ID),
            "artifact_name": ARTIFACT_NAME,
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": ARTIFACT_DIGEST,
            "artifact_expires_at": artifact["expires_at"],
        },
        "campaign_decision": {
            "guarded_safety_success": True,
            "performance_win": False,
            "optimization_promoted": False,
            "selected_profile": "reuse_off",
            "ffn_pair_fusion_lane_closed": True,
            "e20b_failed_contract_rehabilitated": False,
        },
        "retention_validation": {
            "independent_replay_byte_identical": True,
            "workflow_summary_sha256": sha256_file(workflow_summary),
            "workflow_inventory_sha256": inventory["sha256"],
            "workflow_inventory_hashed_files": inventory["hashed_files"],
            "artifact_identity_bound": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        args.evidence_dir,
        args.contract,
        args.root,
        args.run_metadata,
        args.artifact_metadata,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
