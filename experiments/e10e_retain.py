#!/usr/bin/env python3
"""Retain independently reproduced E10e evidence with GitHub provenance."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


def raw_inventory(evidence: Path) -> dict[str, Any]:
    paths = sorted(evidence.glob("variants/*/raw/*.json.gz"))
    if not paths:
        raise ValueError("E10e artifact has no raw responses")
    inventory = hashlib.sha256()
    compressed_bytes = 0
    uncompressed_bytes = 0
    for path in paths:
        relative = path.relative_to(evidence).as_posix()
        compressed = path.read_bytes()
        raw = gzip.decompress(compressed)
        if not isinstance(json.loads(raw), dict):
            raise ValueError(f"E10e raw response is not an object: {relative}")
        digest = hashlib.sha256(compressed).hexdigest()
        inventory.update(f"{digest}  {relative}\n".encode())
        compressed_bytes += len(compressed)
        uncompressed_bytes += len(raw)
    return {
        "file_count": len(paths),
        "compressed_bytes": compressed_bytes,
        "uncompressed_bytes": uncompressed_bytes,
        "inventory_sha256": inventory.hexdigest(),
    }


def build_manifest(
    *,
    evidence: Path,
    plan_path: Path,
    independent_summary_path: Path,
    run_id: str,
    run_attempt: int,
    job_id: str,
    artifact_name: str,
    artifact_id: str,
    artifact_size_bytes: int,
) -> dict[str, Any]:
    summary_path = evidence / "summary.json"
    summary = load_object(summary_path)
    independent = load_object(independent_summary_path)
    github = load_object(evidence / "github.json")
    if (
        summary != independent
        or summary.get("status")
        != "valid_probability_api_compatibility_preflight"
        or summary.get("contract_sha256") != sha256_file(plan_path)
        or summary.get("decision", {}).get("successor_dispatch_allowed") is not True
        or summary.get("decision", {}).get("full_holdout_validated") is not False
        or github.get("run_id") != run_id
        or github.get("run_attempt") != run_attempt
        or not run_id.isdigit()
        or not job_id.isdigit()
        or not artifact_id.isdigit()
        or artifact_size_bytes <= 0
    ):
        raise ValueError("E10e retained summary or GitHub provenance differs")
    return {
        **summary,
        "github": {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "job_id": job_id,
            "repository_commit": github["sha"],
            "artifact_name": artifact_name,
            "artifact_id": artifact_id,
            "artifact_size_bytes": artifact_size_bytes,
        },
        "artifact_validation": {
            "workflow_summary_sha256": sha256_file(summary_path),
            "independent_summary_sha256": sha256_file(independent_summary_path),
            "independent_summary_byte_identical": True,
            "raw_inventory": raw_inventory(evidence),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--independent-summary", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact-size-bytes", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        evidence=args.evidence_dir,
        plan_path=args.plan,
        independent_summary_path=args.independent_summary,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        job_id=args.job_id,
        artifact_name=args.artifact_name,
        artifact_id=args.artifact_id,
        artifact_size_bytes=args.artifact_size_bytes,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
