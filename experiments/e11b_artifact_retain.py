#!/usr/bin/env python3
"""Bind the recovered E11b matrix to its failed source run and artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e11b_artifact_recovery import build_recovered_summary
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e11b_artifact_recovery import build_recovered_summary
    from e5b_ingest import load_object, sha256_file


RUN_ID = 30869286295
JOB_ID = 91867736992
ARTIFACT_ID = 8878168248
ARTIFACT_NAME = "e11b-stock-service-frontier-30869286295-1"
ARTIFACT_DIGEST = (
    "sha256:5761150e1f5bedad5206364a5bbed8b87429826922e47fe9fb4a57f1b7b90e3b"
)
HEAD_SHA = "7cac67ce6ac836aa3d78a9aa3c28ccb5ae8eeaee"
ARTIFACT_FILES = 566
LOCAL_FILES = {
    "artifact-metadata.json",
    "recovered-summary.json",
    "run-metadata.json",
}
CELL_FILES = {
    "health.json",
    "metrics.txt",
    "probe.json",
    "readiness.json",
    "recipe.json",
    "runner-state-after.txt",
    "runner-state-before.txt",
    "server-pid.txt",
    "server-shell-exit.txt",
    "server-time.log",
    "server.stderr.log",
    "server.stdout.log",
    "slots.json",
}


def validate_artifact_inventory(
    evidence: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    expected_cells = {
        Path("pairs")
        / candidate
        / f"{index:02d}-{item['role']}-r{item['repetition']}"
        for candidate in contract["candidate_order"]
        for index, item in enumerate(contract["execution"]["pair_order"], start=1)
    }
    observed_cells = {
        path.parent.relative_to(evidence)
        for path in evidence.glob("pairs/*/*/probe.json")
    }
    if observed_cells != expected_cells:
        raise ValueError("E11b retained cell set differs")
    for cell in expected_cells:
        names = {
            path.name for path in (evidence / cell).iterdir() if path.is_file()
        }
        if names != CELL_FILES:
            raise ValueError(f"E11b retained files differ for {cell}")

    files = [
        path
        for path in evidence.rglob("*")
        if path.is_file() and path.relative_to(evidence).as_posix() not in LOCAL_FILES
    ]
    required = {
        "build/runtime-closure.json",
        "contract.json",
        "frozen-inputs/experiments/e11b_ingest.py",
        "frozen-inputs/experiments/e11b_probe.py",
        "frozen-inputs/tests/test_e11b.py",
        "model-sha256.txt",
        "provenance.json",
        "source-diff.patch",
    }
    relative = {path.relative_to(evidence).as_posix() for path in files}
    if len(files) != ARTIFACT_FILES or not required.issubset(relative):
        raise ValueError("E11b source artifact inventory is incomplete")
    rows = [
        f"{sha256_file(path)}  {path.relative_to(evidence).as_posix()}"
        for path in sorted(files, key=lambda item: item.relative_to(evidence).as_posix())
    ]
    inventory_bytes = ("\n".join(rows) + "\n").encode()
    return {
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "independent_inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "fresh_process_cells": len(expected_cells),
        "cell_files": len(expected_cells) * len(CELL_FILES),
        "all_source_artifact_files_hashed": True,
    }


def retain(
    *,
    evidence: Path,
    contract_path: Path,
    root: Path,
    run_metadata: Path,
    artifact_metadata: Path,
) -> dict[str, Any]:
    replay = build_recovered_summary(evidence, contract_path, root)
    contract = load_object(contract_path)
    run = load_object(run_metadata)
    jobs = run.get("jobs", [])
    artifacts = load_object(artifact_metadata).get("artifacts", [])
    selected = [item for item in artifacts if item.get("id") == ARTIFACT_ID]
    if len(jobs) != 1 or len(selected) != 1:
        raise ValueError("E11b run or artifact count differs")
    job = jobs[0]
    artifact = selected[0]
    steps = {step.get("name"): step.get("conclusion") for step in job.get("steps", [])}
    if (
        str(run.get("databaseId")) != str(RUN_ID)
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("headSha") != HEAD_SHA
        or job.get("databaseId") != JOB_ID
        or job.get("conclusion") != "failure"
        or steps.get("Run every frozen same-job pair") != "success"
        or steps.get("Independently validate complete service frontier") != "failure"
        or steps.get("Upload complete E11b evidence") != "success"
        or artifact.get("name") != ARTIFACT_NAME
        or artifact.get("digest") != ARTIFACT_DIGEST
        or artifact.get("expired") is not False
        or str(artifact.get("workflow_run", {}).get("id")) != str(RUN_ID)
        or artifact.get("workflow_run", {}).get("head_sha") != HEAD_SHA
        or replay.get("status") != "valid_stock_quant_service_frontier"
        or len(replay.get("pairs", [])) != 5
        or len(replay.get("points", [])) != 6
    ):
        raise ValueError("E11b retained identity or recovery outcome differs")
    inventory = validate_artifact_inventory(evidence, contract)
    return {
        **replay,
        "github": {
            "source_run_id": str(RUN_ID),
            "source_run_attempt": 1,
            "source_run_url": run["url"],
            "source_run_conclusion": "failure",
            "source_job_id": str(JOB_ID),
            "repository_commit": HEAD_SHA,
            "artifact_id": str(ARTIFACT_ID),
            "artifact_name": ARTIFACT_NAME,
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": ARTIFACT_DIGEST,
            "artifact_expires_at": artifact["expires_at"],
        },
        "artifact_recovery": {
            "source_workflow_remains_failed": True,
            "source_failure": (
                "slots.json must contain a JSON object at "
                "e11b_ingest.py:220"
            ),
            "corrected_path": "slots.json",
            "accepted_shape": "JSON array of slot objects",
            "all_other_json_paths_remain_object_only": True,
            "source_python": "3.10.20",
            "replay_python": "3.10.20",
            "complete_retained_matrix_replayed": True,
            "native_measurements_added": 0,
            "native_rerun_required": False,
            "source_contract_or_gates_changed": False,
            "inventory": inventory,
        },
        "campaign_decision": {
            "product_promotion_made": False,
            "e11b_native_rerun_required": False,
            "terminal_model_decision_deferred_to_e12b_recovery": True,
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
        evidence=args.evidence_dir,
        contract_path=args.contract,
        root=args.root,
        run_metadata=args.run_metadata,
        artifact_metadata=args.artifact_metadata,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
