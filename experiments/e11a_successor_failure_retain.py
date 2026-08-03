#!/usr/bin/env python3
"""Retain the E11a successor's premeasurement provenance-check failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


EXPECTED_CANDIDATES = {
    "ministral3_3b_q3_k_s",
    "ministral3_3b_q3_k_m",
    "ministral3_3b_iq4_xs",
    "ministral3_3b_iq4_nl",
    "ministral3_3b_q4_k_s",
    "ministral3_3b_q5_k_m",
    "ministral3_3b_q6_k",
    "ministral3_3b_q8_0",
}


def git_blob(root: Path, commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def git_blob_sha256(root: Path, commit: str, relative: str) -> str:
    return hashlib.sha256(git_blob(root, commit, relative)).hexdigest()


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    run = load_object(evidence / "github-run.json")
    contract_bytes = git_blob(root, run["headSha"], contract_path.as_posix())
    contract = json.loads(contract_bytes)
    artifacts = load_object(evidence / "github-artifacts.json")
    jobs = run.get("jobs")
    if contract.get("experiment_id") != "E11a-successor" or not isinstance(jobs, list):
        raise ValueError("E11a successor failure inputs differ")
    evaluate = [job for job in jobs if "native safe-sampled stock holdout" in job.get("name", "")]
    aggregate = [job for job in jobs if job.get("name", "").startswith("Aggregate complete")]
    candidates = {
        job["name"].split(" native safe-sampled stock holdout", 1)[0]
        for job in evaluate
    }
    log = (evidence / "github-run.log").read_text(errors="replace")
    e10f = load_object(root / contract["inputs"]["e10f_contract_path"])
    expected_test_sha = e10f["inputs"]["test_sha256"]
    current_test_path = root / e10f["inputs"]["test_path"]
    historical_sha = git_blob_sha256(
        root,
        contract["prerequisite"]["repository_commit"],
        e10f["inputs"]["test_path"],
    )
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("headSha") != "27bda205ae63d15aba793d4fbef5f3b50c81c221"
        or len(evaluate) != 8
        or candidates != EXPECTED_CANDIDATES
        or any(job.get("conclusion") != "failure" for job in evaluate)
        or len(aggregate) != 1
        or aggregate[0].get("conclusion") != "skipped"
        or artifacts.get("total_count") != 0
        or artifacts.get("artifacts") != []
        or log.count("tests/test_e10f.py: FAILED") != 8
        or log.count("No files were found with the provided path") != 8
        or historical_sha != expected_test_sha
        or sha256_file(current_test_path) == expected_test_sha
    ):
        raise ValueError("E11a successor setup failure provenance differs")
    return {
        "schema_version": 1,
        "experiment_id": "E11a-successor",
        "status": "invalid_premeasurement_provenance_check_failure",
        "experiment_result_valid": False,
        "model_results_observed": False,
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "failure": {
            "stage": "shared prerequisite validation",
            "failed_cells": 8,
            "model_downloads_started": 0,
            "model_measurements_started": 0,
            "aggregate_conclusion": "skipped",
            "artifact_count": 0,
            "expected_historical_test_sha256": expected_test_sha,
            "historical_test_sha256_at_e10f_commit": historical_sha,
            "current_test_sha256": sha256_file(current_test_path),
            "cause": (
                "The successor rehashed every E10f source input in the current checkout. "
                "tests/test_e10f.py legitimately gained retained-result tests after E10f "
                "completed, so its current hash cannot equal E10f's historical frozen hash."
            ),
            "repair_boundary": (
                "A successor may validate E10f's retained artifact copies, exact historical "
                "commit blob and retained manifest instead of requiring unrelated later "
                "test additions to preserve a historical working-tree hash. Candidate "
                "models, scorer, workload, safe token, metrics and frontier policy may not change."
            ),
        },
        "github": {
            "run_id": "30846943310",
            "run_attempt": 1,
            "run_url": run["url"],
            "repository_commit": run["headSha"],
            "conclusion": run["conclusion"],
            "evaluate_job_ids": sorted(str(job["databaseId"]) for job in evaluate),
            "aggregate_job_id": str(aggregate[0]["databaseId"]),
            "run_log_sha256": sha256_file(evidence / "github-run.log"),
            "artifacts_api_sha256": sha256_file(evidence / "github-artifacts.json"),
        },
        "decision": {
            "stock_quant_frontier_accepted": False,
            "quality_or_model_claim_permitted": False,
            "negative_setup_result_retained": True,
            "separately_frozen_provenance_repair_allowed": True,
        },
        "claim_boundary": (
            "All eight cells stopped before model download or inference, so this run "
            "contains no stock-quant quality, size, performance, memory, or promotion result."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
