#!/usr/bin/env python3
"""Retain independently reproduced E16a sidecar-feasibility evidence."""

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


def validate_inventory(evidence: Path, run_id: str, run_attempt: int) -> dict[str, Any]:
    inventory_path = evidence / "file-inventory-sha256.txt"
    marker = f"/results/raw/e16a-{run_id}-{run_attempt}/"
    entries: dict[str, str] = {}
    for line in inventory_path.read_text(encoding="utf-8").splitlines():
        digest, absolute = line.split("  ", 1)
        if len(digest) != 64 or marker not in absolute:
            raise ValueError("E16a artifact inventory line is invalid")
        relative = absolute.split(marker, 1)[1]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in entries:
            raise ValueError("E16a artifact inventory path is unsafe or duplicate")
        local = evidence / path
        if not local.is_file() or sha256_file(local) != digest:
            raise ValueError(f"E16a artifact inventory differs for {relative}")
        entries[relative] = digest
    actual = {
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file()
        and path.name not in {"file-inventory-sha256.txt", "summary-local.json"}
    }
    if set(entries) - actual or actual - set(entries) != {"disk-after.txt"}:
        raise ValueError("E16a artifact inventory file set differs")
    generated_binaries = [
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file() and path.suffix in {".bin", ".gguf"}
    ]
    if generated_binaries:
        raise ValueError("E16a artifact retained a generated binary")
    return {
        "file_count": len(entries),
        "inventory_sha256": sha256_file(inventory_path),
        "files_outside_runner_regular_file_inventory": {
            "disk-after.txt": sha256_file(evidence / "disk-after.txt")
        },
        "generated_raw_tensor_or_sidecar_binaries_retained": False,
        "all_retained_file_hashes_verified": True,
    }


def build_manifest(
    *,
    evidence: Path,
    contract_path: Path,
    independent_summary_path: Path,
    run_id: str,
    run_attempt: int,
    job_id: str,
    artifact_name: str,
    artifact_id: str,
    artifact_size_bytes: int,
    artifact_digest: str,
) -> dict[str, Any]:
    summary_path = evidence / "summary.json"
    summary = load_object(summary_path)
    independent = load_object(independent_summary_path)
    provenance = load_object(evidence / "provenance.json")
    cleanup = [
        load_object(
            evidence / "cells" / f"{repetition:02d}-r{repetition}" / "cleanup.json"
        )
        for repetition in (1, 2)
    ]
    if (
        summary != independent
        or summary.get("status") != "valid_loader_feasibility"
        or summary.get("loader_successor_authorized") is not True
        or summary.get("contract_sha256") != sha256_file(contract_path)
        or not summary.get("gates")
        or not all(summary["gates"].values())
        or summary.get("failed_gates")
        or summary.get("decision", {}).get("performance_claim_permitted") is not False
        or summary.get("decision", {}).get("sidecar_published_as_deployable")
        is not False
        or any(
            item.get("generated_binary_cleanup_complete") is not True
            or item.get("deleted_raw_tensor_count") != 183
            or item.get("deleted_raw_tensor_bytes") != 2137964544
            or item.get("deleted_sidecar_bytes") != 2139013120
            for item in cleanup
        )
        or provenance.get("github_run_id") != run_id
        or provenance.get("github_run_attempt") != run_attempt
        or provenance.get("experiment_id") != "E16a"
        or not all(value.isdigit() for value in (run_id, job_id, artifact_id))
        or artifact_size_bytes <= 0
        or not artifact_digest.startswith("sha256:")
        or len(artifact_digest.removeprefix("sha256:")) != 64
    ):
        raise ValueError("E16a retained result or provenance differs")
    return {
        **summary,
        "decision": {
            **summary["decision"],
            "loader_experiment_authorized": True,
            "authorized_successor_boundary": (
                "A separately frozen native Arm experiment may implement a "
                "fail-closed read-only mmap loader for sidecar format version 1 "
                "and compare it with normal runtime repacking."
            ),
            "loader_implemented_or_benchmarked_by_e16a": False,
        },
        "github": {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "job_id": job_id,
            "repository_commit": provenance["git_commit"],
            "artifact_name": artifact_name,
            "artifact_id": artifact_id,
            "artifact_size_bytes": artifact_size_bytes,
            "artifact_digest": artifact_digest,
        },
        "artifact_validation": {
            "workflow_summary_sha256": sha256_file(summary_path),
            "independent_summary_sha256": sha256_file(independent_summary_path),
            "independent_summary_byte_identical": True,
            "inventory": validate_inventory(evidence, run_id, run_attempt),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--independent-summary", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact-size-bytes", type=int, required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        independent_summary_path=args.independent_summary,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        job_id=args.job_id,
        artifact_name=args.artifact_name,
        artifact_id=args.artifact_id,
        artifact_size_bytes=args.artifact_size_bytes,
        artifact_digest=args.artifact_digest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
