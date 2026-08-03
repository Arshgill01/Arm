#!/usr/bin/env python3
"""Independently retain E17a's valid native compatibility preflight."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e17a_second_successor_ingest import build_manifest
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e17a_second_successor_ingest import build_manifest


RUN_ID = "30856539977"
RUN_ATTEMPT = 1
JOB_ID = "91828765128"
HEAD_SHA = "a8fa6c1c386bde7dc32c2c428ad077e3a1388381"
ARTIFACT_ID = 8872697322
ARTIFACT_NAME = "e17a-kv-v-cache-preflight-30856539977-1"
ARTIFACT_DIGEST = "sha256:a1aeb6c2748695c505a686306690c584c81fd0c4362a806d7d76559ba2a674bc"
ARTIFACT_SIZE_BYTES = 13_915_578


def validate_inventory(evidence: Path) -> dict[str, Any]:
    inventory = evidence / "file-inventory-sha256.txt"
    marker = f"/results/raw/e17a-{RUN_ID}-{RUN_ATTEMPT}/"
    total_bytes = 0
    paths: list[str] = []
    for line in inventory.read_text().splitlines():
        digest, archived_path = line.split("  ", 1)
        if marker not in archived_path:
            raise ValueError("E17a inventory contains a foreign runner path")
        relative = archived_path.split(marker, 1)[1]
        candidate = evidence / relative
        if not candidate.is_file() or sha256_file(candidate) != digest:
            raise ValueError(f"E17a inventory differs for {relative}")
        paths.append(relative)
        total_bytes += candidate.stat().st_size
    if len(paths) != len(set(paths)):
        raise ValueError("E17a inventory repeats a path")
    return {
        "workflow_inventoried_file_count": len(paths),
        "workflow_inventoried_bytes": total_bytes,
        "inventory_sha256": sha256_file(inventory),
        "all_workflow_inventoried_files_verified": True,
    }


def retain(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    run = load_object(evidence / "github-run.json")
    artifact = load_object(evidence / "github-artifact.json")
    jobs = run.get("jobs")
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("headSha") != HEAD_SHA
        or not isinstance(jobs, list)
        or len(jobs) != 1
        or jobs[0].get("databaseId") != int(JOB_ID)
        or jobs[0].get("conclusion") != "success"
        or any(step.get("conclusion") != "success" for step in jobs[0].get("steps", []))
    ):
        raise ValueError("E17a successful run provenance differs")
    if (
        artifact.get("id") != ARTIFACT_ID
        or artifact.get("name") != ARTIFACT_NAME
        or artifact.get("digest") != ARTIFACT_DIGEST
        or artifact.get("size_in_bytes") != ARTIFACT_SIZE_BYTES
        or artifact.get("expired") is not False
    ):
        raise ValueError("E17a successful artifact identity differs")

    replay = build_manifest(evidence, contract_path, root)
    workflow_summary = load_object(evidence / "summary.json")
    if replay != workflow_summary:
        raise ValueError("E17a successful workflow summary does not replay")
    if (
        replay.get("status") != "valid_quantized_v_compatibility_preflight"
        or replay.get("decision", {}).get("supported_quantized_configurations")
        != ["q8_0_q8_0", "q4_0_q4_0"]
        or replay.get("decision", {}).get("long_context_successor_allowed") is not True
    ):
        raise ValueError("E17a successful compatibility decision differs")

    retained = copy.deepcopy(replay)
    retained["workflow_summary_sha256"] = sha256_file(evidence / "summary.json")
    retained["github"] = {
        "run_id": RUN_ID,
        "run_attempt": RUN_ATTEMPT,
        "run_url": run["url"],
        "job_id": JOB_ID,
        "repository_commit": HEAD_SHA,
        "artifact_name": ARTIFACT_NAME,
        "artifact_id": str(ARTIFACT_ID),
        "artifact_size_bytes": ARTIFACT_SIZE_BYTES,
        "artifact_digest": ARTIFACT_DIGEST,
        "run_log_sha256": sha256_file(evidence / "github-run.log"),
    }
    retained["artifact_validation"] = validate_inventory(evidence)
    return retained


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("experiments/e17a_second_successor_contract.json"),
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
