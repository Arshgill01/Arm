#!/usr/bin/env python3
"""Retain independently reproduced E12a metadata recovery evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


LOCAL_METADATA = {"artifact.json", "job.json", "job.log", "summary-local.json"}


def validate_inventory(evidence: Path, run_id: str, run_attempt: int) -> dict[str, Any]:
    inventory = evidence / "file-inventory-sha256.txt"
    marker = f"/results/raw/e12a-metadata-recovery-{run_id}-{run_attempt}/"
    entries: dict[str, str] = {}
    for line in inventory.read_text().splitlines():
        digest, absolute = line.split("  ", 1)
        if len(digest) != 64 or marker not in absolute:
            raise ValueError("E12a metadata artifact inventory line is invalid")
        relative = absolute.split(marker, 1)[1]
        item = Path(relative)
        if item.is_absolute() or ".." in item.parts or relative in entries:
            raise ValueError("E12a metadata artifact inventory path is unsafe or duplicate")
        local = evidence / item
        if not local.is_file() or sha256_file(local) != digest:
            raise ValueError(f"E12a metadata artifact inventory differs for {relative}")
        entries[relative] = digest
    actual = {
        item.relative_to(evidence).as_posix()
        for item in evidence.rglob("*")
        if item.is_file()
        and item.relative_to(evidence).as_posix()
        not in {"file-inventory-sha256.txt", *LOCAL_METADATA}
    }
    unlisted = actual - set(entries)
    if set(entries) - actual or unlisted != {"memory-after.txt", "disk-after.txt"}:
        raise ValueError("E12a metadata artifact inventory file set differs")
    return {
        "file_count": len(entries),
        "inventory_sha256": sha256_file(inventory),
        "files_outside_runner_inventory": {
            name: sha256_file(evidence / name) for name in sorted(unlisted)
        },
        "archive_matrix_mode_rehydrated_to_read_only_for_replay": True,
        "all_retained_file_hashes_verified": True,
    }


def build_manifest(
    *,
    evidence: Path,
    contract_path: Path,
    independent_summary_path: Path,
    job_path: Path,
    artifact_path: Path,
    job_log_path: Path,
    run_id: str,
    run_attempt: int,
) -> dict[str, Any]:
    summary_path = evidence / "summary.json"
    summary = load_object(summary_path)
    independent = load_object(independent_summary_path)
    job = load_object(job_path)
    artifact = load_object(artifact_path)
    expected_sha = "e1abafe2779f4366140ca31372be484b7178b7af"
    if (
        summary != independent
        or summary.get("status") != "valid_application_conditioned_imatrix_metadata_recovery"
        or summary.get("contract_sha256") != sha256_file(contract_path)
        or summary.get("imatrix", {}).get("sha256")
        != "2338867f1b51341e02d0f63ca4d7281731a94b0738d80413476581ae991a1548"
        or summary.get("imatrix", {}).get("metadata", {}).get("chunk_count") != 32
        or summary.get("imatrix", {}).get("metadata", {}).get("entries") != 182
        or summary.get("statistics", {}).get("tensor_count") != 182
        or summary.get("statistics", {}).get("repeated") is not False
        or summary.get("validation", {}).get("generated_quant_dispatch_allowed") is not True
        or str(job.get("run_id")) != run_id
        or str(job.get("id")) != "91825608565"
        or job.get("conclusion") != "success"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or job.get("head_sha") != expected_sha
        or str(artifact.get("id")) != "8872307191"
        or artifact.get("name") != f"e12a-metadata-recovery-{run_id}-1"
        or artifact.get("digest")
        != "sha256:876755a44b4345df3de742aea44692edd2d5946c449c8cd11f3e42161c288c22"
        or artifact.get("workflow_run", {}).get("head_sha") != expected_sha
        or str(artifact.get("workflow_run", {}).get("id")) != run_id
        or "valid_application_conditioned_imatrix_metadata_recovery"
        not in job_log_path.read_text(errors="replace")
    ):
        raise ValueError("E12a metadata retained result differs")
    return {
        **summary,
        "github": {
            **summary["github"],
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "job_id": str(job["id"]),
            "artifact_name": artifact["name"],
            "artifact_id": str(artifact["id"]),
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": artifact["digest"],
            "artifact_expires_at": artifact["expires_at"],
        },
        "artifact_validation": {
            "workflow_summary_sha256": sha256_file(summary_path),
            "independent_summary_sha256": sha256_file(independent_summary_path),
            "independent_summary_byte_identical": True,
            "job_log_sha256": sha256_file(job_log_path),
            "inventory": validate_inventory(evidence, run_id, run_attempt),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--independent-summary", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--job-log", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        independent_summary_path=args.independent_summary,
        job_path=args.job,
        artifact_path=args.artifact,
        job_log_path=args.job_log,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
