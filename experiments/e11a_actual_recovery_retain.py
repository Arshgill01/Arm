#!/usr/bin/env python3
"""Bind independently replayed terminal E11a accounting to GitHub evidence."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e11a_actual_recovery_ingest import aggregate
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e11a_actual_recovery_ingest import aggregate


def validate_inventory(evidence: Path) -> dict[str, Any]:
    inventory = evidence / "file-inventory-sha256.txt"
    marker = "results/raw/e11a-actual-recovery/combined/"
    entries: dict[str, str] = {}
    total = 0
    for line in inventory.read_text().splitlines():
        digest, archived = line.split("  ", 1)
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None or marker not in archived:
            raise ValueError("E11a actual recovery inventory line differs")
        relative = archived.split(marker, 1)[1]
        path = evidence / relative
        if (
            relative in entries
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not path.is_file()
            or sha256_file(path) != digest
        ):
            raise ValueError(f"E11a actual recovery inventory differs for {relative}")
        entries[relative] = digest
        total += path.stat().st_size
    required = {
        "summary.json",
        "contract.json",
        "original-contract.json",
        "source-artifacts.json",
        "source-jobs-api.json",
        "source-run-api.json",
        "source-run-terminal.json",
        "q6-resource-failure-manifest.json",
        "q8-resource-failure-manifest.json",
        "anchor-retained-manifest.json",
        "anchor-workflow-summary.json",
    }
    if set(entries) != required:
        raise ValueError("E11a actual recovery inventory set differs")
    return {
        "file_count": len(entries),
        "total_inventoried_bytes": total,
        "inventory_sha256": sha256_file(inventory),
        "all_workflow_inventoried_files_verified": True,
    }


def retain(
    *,
    evidence: Path,
    contract_path: Path,
    original_contract_path: Path,
    cell_paths: list[Path],
    anchor_path: Path,
    failure_paths: list[Path],
    run_metadata: Path,
    job_metadata: Path,
    artifact_metadata: Path,
) -> dict[str, Any]:
    replay = aggregate(
        contract_path=contract_path,
        original_contract_path=original_contract_path,
        cell_paths=cell_paths,
        anchor_path=anchor_path,
        failure_paths=failure_paths,
        artifact_metadata_path=evidence / "source-artifacts.json",
    )
    expected = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    if expected != (evidence / "summary.json").read_bytes():
        raise ValueError("E11a actual recovery replay differs")
    if (
        load_object(evidence / "contract.json") != load_object(contract_path)
        or load_object(evidence / "original-contract.json")
        != load_object(original_contract_path)
        or load_object(evidence / "anchor-retained-manifest.json")
        != load_object(anchor_path)
        or load_object(evidence / "q6-resource-failure-manifest.json")
        != load_object(failure_paths[0])
        or load_object(evidence / "q8-resource-failure-manifest.json")
        != load_object(failure_paths[1])
    ):
        raise ValueError("E11a actual recovery compact inputs differ")

    run = load_object(run_metadata)
    job = load_object(job_metadata)
    artifact = load_object(artifact_metadata)
    run_id = str(run.get("databaseId"))
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("headSha") != job.get("head_sha")
        or str(job.get("run_id")) != run_id
        or job.get("run_attempt") != 1
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or job.get("conclusion") != "success"
        or artifact.get("name") != f"e11a-actual-recovery-{run_id}-1"
        or artifact.get("digest", "").startswith("sha256:") is not True
        or artifact.get("expired") is not False
        or str(artifact.get("workflow_run", {}).get("id")) != run_id
        or artifact.get("workflow_run", {}).get("head_sha") != run.get("headSha")
    ):
        raise ValueError("E11a actual recovery retained identity differs")
    retained = copy.deepcopy(replay)
    retained["github"] = {
        "run_id": run_id,
        "run_attempt": 1,
        "run_url": run["url"],
        "job_id": str(job["id"]),
        "repository_commit": run["headSha"],
        "artifact_name": artifact["name"],
        "artifact_id": str(artifact["id"]),
        "artifact_size_bytes": artifact["size_in_bytes"],
        "artifact_digest": artifact["digest"],
        "artifact_expires_at": artifact["expires_at"],
    }
    retained["artifact_validation"] = {
        "workflow_summary_sha256": sha256_file(evidence / "summary.json"),
        "independent_replay_byte_identical": True,
        "source_cell_summaries_replayed": len(cell_paths),
        "resource_failure_manifests_replayed": len(failure_paths),
        "inventory": validate_inventory(evidence),
    }
    return retained


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--original-contract", type=Path, required=True)
    parser.add_argument("--cell", type=Path, action="append", required=True)
    parser.add_argument("--anchor", type=Path, required=True)
    parser.add_argument("--failure", type=Path, action="append", required=True)
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--job-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        original_contract_path=args.original_contract,
        cell_paths=args.cell,
        anchor_path=args.anchor,
        failure_paths=args.failure,
        run_metadata=args.run_metadata,
        job_metadata=args.job_metadata,
        artifact_metadata=args.artifact_metadata,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
