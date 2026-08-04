#!/usr/bin/env python3
"""Bind E20a's valid no-measurement recovery to its GitHub artifact."""

from __future__ import annotations

import argparse
import copy
import json
import re
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


def validate_inventory(evidence: Path, run_id: str) -> dict[str, Any]:
    inventory = evidence / "file-inventory-sha256.txt"
    marker = f"/results/raw/e20a-ingestion-recovery-{run_id}-1/"
    entries: dict[str, str] = {}
    total = 0
    for line in inventory.read_text().splitlines():
        digest, archived = line.split("  ", 1)
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None or marker not in archived:
            raise ValueError("E20a recovery inventory line differs")
        relative = archived.split(marker, 1)[1]
        path = Path(relative)
        local = evidence / path
        if (
            path.is_absolute()
            or ".." in path.parts
            or relative in entries
            or not local.is_file()
            or sha256_file(local) != digest
        ):
            raise ValueError(f"E20a recovery inventory differs: {relative}")
        entries[relative] = digest
        total += local.stat().st_size
    required = {
        "contract.json",
        "corrected-ingester.py",
        "lscpu.txt",
        "metadata/source-artifacts.json",
        "metadata/source-job.json",
        "metadata/source-run.json",
        "python-version.txt",
        "recovered-summary.json",
        "source-failure-manifest.json",
        "summary.json",
        "uname.txt",
    }
    if set(entries) != required:
        raise ValueError("E20a recovery inventory file set differs")
    return {
        "file_count": len(entries),
        "total_inventoried_bytes": total,
        "inventory_sha256": sha256_file(inventory),
        "all_workflow_inventoried_files_verified": True,
    }


def retain(
    *,
    evidence: Path,
    root: Path,
    run_metadata: Path,
    job_metadata: Path,
    artifact_metadata: Path,
) -> dict[str, Any]:
    run = load_object(run_metadata)
    job = load_object(job_metadata)
    artifact = load_object(artifact_metadata)
    result = load_object(evidence / "summary.json")
    recovered = load_object(evidence / "recovered-summary.json")
    contract_path = root / "experiments/e20a_ingestion_recovery_contract.json"
    failure_path = (
        root / "results/manifests/e20a-ingestion-failure-30863505489.json"
    )
    contract = load_object(contract_path)
    run_id = str(run.get("databaseId"))
    expected = contract["expected_result"]
    quality = recovered.get("quality", {}).get("probe", {})
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or not run_id.isdigit()
        or str(job.get("run_id")) != run_id
        or job.get("conclusion") != "success"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or job.get("head_sha") != run.get("headSha")
        or artifact.get("name") != f"e20a-ingestion-recovery-{run_id}-1"
        or re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest", ""))
        is None
        or artifact.get("expired") is not False
        or str(artifact.get("workflow_run", {}).get("id")) != run_id
        or artifact.get("workflow_run", {}).get("head_sha") != run.get("headSha")
        or load_object(evidence / "contract.json") != contract
        or sha256_file(failure_path) != contract["inputs"]["failure_manifest_sha256"]
        or load_object(evidence / "source-failure-manifest.json")
        != load_object(failure_path)
        or sha256_file(evidence / "corrected-ingester.py")
        != contract["inputs"]["fixed_ingest_sha256"]
        or sha256_file(evidence / "recovered-summary.json")
        != expected["summary_sha256"]
        or recovered.get("status") != expected["status"]
        or recovered.get("selection") != expected["selection"]
        or {
            "correct": quality.get("correct"),
            "failures": quality.get("failures"),
            "reference_prediction_mismatches": quality.get(
                "reference_prediction_mismatches"
            ),
            "total": quality.get("total"),
        }
        != expected["quality"]
        or result.get("status")
        != "valid_cpu_node_profile_fusion_candidate_recovered_without_remeasurement"
        or result.get("recovered_result") != recovered
        or result.get("decision", {}).get("selected_family") != "ffn_gate_up"
        or result.get("decision", {}).get(
            "focused_fusion_feasibility_successor_allowed"
        )
        is not True
        or result.get("decision", {}).get("automatic_source_optimization_allowed")
        is not False
        or result.get("validation", {}).get(
            "benchmark_or_quality_measurement_repeated"
        )
        is not False
        or result.get("validation", {}).get("timed_results_used_for_performance_claim")
        is not False
        or result.get("recovery_github", {}).get("run_id") != run_id
        or result.get("recovery_github", {}).get("repository_commit")
        != run.get("headSha")
        or parse_lscpu((evidence / "lscpu.txt").read_text())["architecture"]
        != "aarch64"
        or (evidence / "python-version.txt").read_text().strip()
        != "Python 3.12.13"
    ):
        raise ValueError("E20a recovery identity or result differs")
    retained = copy.deepcopy(result)
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
        "recovered_summary_sha256": sha256_file(evidence / "recovered-summary.json"),
        "inventory": validate_inventory(evidence, run_id),
    }
    return retained


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--job-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        evidence=args.evidence_dir,
        root=args.root,
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
