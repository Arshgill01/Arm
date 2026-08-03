#!/usr/bin/env python3
"""Retain the independently reproduced E16c shared-arena result."""

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
    inventory_path = evidence / "file-inventory-sha256.txt"
    marker = f"/results/raw/e16c-{run_id}-{run_attempt}/"
    entries: dict[str, str] = {}
    for line in inventory_path.read_text(encoding="utf-8").splitlines():
        digest, absolute = line.split("  ", 1)
        if len(digest) != 64 or marker not in absolute:
            raise ValueError("E16c artifact inventory line is invalid")
        relative = absolute.split(marker, 1)[1]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in entries:
            raise ValueError("E16c artifact inventory path is unsafe or duplicate")
        local = evidence / path
        if not local.is_file() or sha256_file(local) != digest:
            raise ValueError(f"E16c artifact inventory differs for {relative}")
        entries[relative] = digest
    actual = {
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file()
        and path.name not in {"file-inventory-sha256.txt", *LOCAL_METADATA}
    }
    unlisted = actual - set(entries)
    if set(entries) - actual or unlisted != {"disk-after.txt"}:
        raise ValueError("E16c artifact inventory file set differs")
    generated = [
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file()
        and (path.suffix == ".gguf" or path.name == "pareto64-e16c-sidecar.bin")
    ]
    if generated:
        raise ValueError("E16c artifact retained a generated model or sidecar")
    return {
        "file_count": len(entries),
        "inventory_sha256": sha256_file(inventory_path),
        "files_outside_runner_regular_file_inventory": {
            "disk-after.txt": sha256_file(evidence / "disk-after.txt")
        },
        "generated_sidecar_or_model_retained": False,
        "all_retained_file_hashes_verified": True,
    }


def validate_github(
    *,
    provenance: dict[str, Any],
    job: dict[str, Any],
    artifact: dict[str, Any],
    run_id: str,
    run_attempt: int,
) -> None:
    expected_sha = "fef62442316adcb4ccc4ae05fa1c8504fa595040"
    if (
        provenance.get("github_run_id") != run_id
        or provenance.get("github_run_attempt") != run_attempt
        or provenance.get("git_commit") != expected_sha
        or str(job.get("run_id")) != run_id
        or str(job.get("id")) != "91812711643"
        or job.get("conclusion") != "success"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or job.get("head_sha") != expected_sha
        or str(artifact.get("id")) != "8871236545"
        or artifact.get("name") != f"e16c-shared-repack-arena-{run_id}-1"
        or artifact.get("digest")
        != "sha256:e29d3a4440dafd42364fb586f9d5f8adb2c6c69b3bd312a10ffd10761312db02"
        or artifact.get("workflow_run", {}).get("head_sha") != expected_sha
        or str(artifact.get("workflow_run", {}).get("id")) != run_id
    ):
        raise ValueError("E16c GitHub provenance differs")


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
    provenance = load_object(evidence / "provenance.json")
    job = load_object(job_path)
    artifact = load_object(artifact_path)
    groups = summary.get("groups", [])
    if (
        summary != independent
        or summary.get("status") != "valid_shared_sidecar_workers_promoted"
        or summary.get("promoted") is not True
        or summary.get("contract_sha256") != sha256_file(contract_path)
        or summary.get("failed_gates") != []
        or not all(summary.get("gates", {}).values())
        or summary.get("decision", {}).get("selected_configuration")
        != "shared_sidecar_workers"
        or summary.get("decision", {}).get(
            "multi_process_physical_sharing_claim_permitted"
        )
        is not True
        or summary.get("decision", {}).get("per_process_rss_reduction_claim_permitted")
        is not False
        or len(groups) != 8
        or any(len(group.get("workers", [])) != 2 for group in groups)
        or any(
            worker.get("probe", {}).get("failures") != 0
            or worker.get("probe", {}).get("reference_prediction_mismatches") != 0
            or worker.get("probe", {}).get("correct") != 23
            for group in groups
            for worker in group["workers"]
        )
        or summary.get("sidecar_cleanup", {}).get("sidecar_cleanup_complete")
        is not True
        or summary.get("final_sidecar_verification", {}).get("status")
        != "valid_sidecar"
        or summary.get("summed_post_workload_pss_saved_kib") != 2091714.0
        or "valid_shared_sidecar_workers_promoted"
        not in job_log_path.read_text(errors="replace")
    ):
        raise ValueError("E16c retained result differs")
    validate_github(
        provenance=provenance,
        job=job,
        artifact=artifact,
        run_id=run_id,
        run_attempt=run_attempt,
    )
    return {
        **summary,
        "github": {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "job_id": str(job["id"]),
            "repository_commit": provenance["git_commit"],
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
