#!/usr/bin/env python3
"""Bind a replayed E19a summary to its exact GitHub artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e19a_ingest import build_summary
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e19a_ingest import build_summary


RUN_ID = 30859673434
ARTIFACT_ID = 8874428293
ARTIFACT_NAME = "e19a-composed-cache-arena-30859673434-1"
ARTIFACT_DIGEST = (
    "sha256:233b45f5ad4f878a9abdb2f41fcceb88dbeabee8826d42aa7cf3f45403c0e0a2"
)
HEAD_SHA = "6d02f984efe83d5211f07512c944676f85f83745"


def retain(
    evidence: Path,
    contract: Path,
    root: Path,
    run_metadata: Path,
    artifact_metadata: Path,
) -> dict[str, Any]:
    replay = build_summary(evidence, contract, root)
    replay_bytes = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    if replay_bytes != (evidence / "summary.json").read_bytes():
        raise ValueError("E19a independent replay differs")
    run = load_object(run_metadata)
    artifacts = load_object(artifact_metadata).get("artifacts", [])
    selected = [item for item in artifacts if item.get("id") == ARTIFACT_ID]
    if (
        str(run.get("databaseId")) != str(RUN_ID)
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("headSha") != HEAD_SHA
        or len(selected) != 1
        or selected[0].get("name") != ARTIFACT_NAME
        or selected[0].get("digest") != ARTIFACT_DIGEST
        or selected[0].get("expired") is not False
        or replay.get("status") != "valid_composed_affinity_cache_arena_promoted"
        or replay.get("promoted") is not True
        or replay.get("failed_gates") != []
    ):
        raise ValueError("E19a retained identity differs")
    inventory = evidence / "file-inventory-sha256.txt"
    lines = [line for line in inventory.read_text().splitlines() if line]
    if len(lines) != 194 or not any(line.endswith("/summary.json") for line in lines):
        raise ValueError("E19a workflow inventory differs")
    artifact = selected[0]
    return {
        **replay,
        "github": {
            "run_id": RUN_ID,
            "run_attempt": 1,
            "run_url": run["url"],
            "repository_commit": HEAD_SHA,
            "job_id": str(run["jobs"][0]["databaseId"]),
            "artifact_id": str(ARTIFACT_ID),
            "artifact_name": ARTIFACT_NAME,
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": ARTIFACT_DIGEST,
            "artifact_expires_at": artifact["expires_at"],
        },
        "retention_validation": {
            "independent_replay_byte_identical": True,
            "workflow_summary_sha256": sha256_file(evidence / "summary.json"),
            "workflow_inventory_sha256": sha256_file(inventory),
            "workflow_inventory_hashed_files": len(lines),
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
