#!/usr/bin/env python3
"""Retain E16c's premeasurement executable-mode failure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e15a_failure_retain import inventory
    from experiments.e16a_ingest import validate_source_build
    from experiments.e16b_ingest import validate_construction
    from experiments.e16c_shared_arena_ingest import validate_inputs
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file
    from e15a_failure_retain import inventory
    from e16a_ingest import validate_source_build
    from e16b_ingest import validate_construction
    from e16c_shared_arena_ingest import validate_inputs


def retain(
    *,
    evidence: Path,
    contract_path: Path,
    root: Path,
    run_log: Path,
    run_metadata: Path,
    job_metadata: Path,
    artifact_metadata: Path,
) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    run = load_object(run_metadata)
    job = load_object(job_metadata)
    artifact = load_object(artifact_metadata)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if (
        platform["architecture"] != contract["acceptance"]["required_architecture"]
        or platform["logical_cpus"]
        != contract["acceptance"]["required_logical_cpus"]
        or platform["model_name"] != contract["acceptance"]["required_model_name"]
    ):
        raise ValueError("E16c failure host differs")
    source_build = validate_source_build(evidence, contract)
    identity = load_object(evidence / "sidecar-identity.json")
    construction = validate_construction(evidence, contract, identity)
    index = construction["sidecar_index"]
    final_verification = load_object(evidence / "final-sidecar-verification.json")
    cleanup = load_object(evidence / "sidecar-cleanup.json")
    if (
        final_verification.get("status") != "valid_sidecar"
        or final_verification.get("sidecar_sha256") != index["sidecar_sha256"]
        or cleanup.get("deleted_sidecar_bytes") != index["sidecar_size_bytes"]
        or cleanup.get("deleted_sidecar_sha256") != index["sidecar_sha256"]
        or cleanup.get("sidecar_cleanup_complete") is not True
    ):
        raise ValueError("E16c failure cleanup differs")
    cells_dir = evidence / "cells"
    if cells_dir.exists() and any(cells_dir.iterdir()):
        raise ValueError("E16c failure unexpectedly contains measured cells")
    log_text = run_log.read_text(errors="replace")
    required_log_fragments = (
        "experiments/e16c_shared_arena_group.sh: Permission denied",
        "Process completed with exit code 126",
        "No such file or directory",
        "cells/01-normal_repack_workers-r1/probe.json",
    )
    if not all(fragment in log_text for fragment in required_log_fragments):
        raise ValueError("E16c run log lacks the retained permission failure")
    github = load_object(evidence / "provenance.json")
    if (
        str(run.get("id")) != github.get("github_run_id")
        or run.get("run_attempt") != github.get("github_run_attempt")
        or run.get("head_sha") != github.get("git_commit")
        or run.get("conclusion") != "failure"
        or str(job.get("id")) != "91808453118"
        or job.get("conclusion") != "failure"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or str(artifact.get("id")) != "8870468109"
        or artifact.get("name") != "e16c-shared-repack-arena-30850318745-1"
        or artifact.get("digest")
        != "sha256:331a210f21c6f4c3b49b4fbeb3252e3989520a9859dadcf4e247bccb76073cd4"
    ):
        raise ValueError("E16c GitHub identity differs")
    files = inventory(evidence)
    return {
        "schema_version": 1,
        "experiment_id": "E16c",
        "status": "invalid_premeasurement_group_runner_permission_failure",
        "experiment_result_valid": False,
        "promotion_decision_permitted": False,
        "contract_sha256": sha256_file(contract_path),
        "failure": {
            "type": "executable_mode_missing",
            "message": "experiments/e16c_shared_arena_group.sh: Permission denied",
            "shell_exit_status": 126,
            "source_build_completed": True,
            "model_verified": True,
            "sidecar_constructed_and_verified": True,
            "measured_worker_processes_started": 0,
            "measured_requests_completed": 0,
            "pss_or_performance_observed": False,
        },
        "github": {
            "run_id": str(run["id"]),
            "run_attempt": run["run_attempt"],
            "job_id": str(job["id"]),
            "repository_commit": run["head_sha"],
            "conclusion": run["conclusion"],
            "run_url": run["html_url"],
            "run_log_sha256": sha256_file(run_log),
            "artifact_id": str(artifact["id"]),
            "artifact_name": artifact["name"],
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": artifact["digest"],
            "artifact_expires_at": artifact["expires_at"],
        },
        "platform": platform,
        "source_build": source_build,
        "sidecar_identity": identity,
        "construction": construction,
        "final_sidecar_verification": final_verification,
        "sidecar_cleanup": cleanup,
        "artifact_validation": files,
        "decision": {
            "e16c_promoted": False,
            "change_contract_or_gates": False,
            "exact_contract_retry_after_executable_mode_repair_allowed": True,
            "generated_sidecar_cleanup_complete": True,
        },
        "claim_boundary": (
            "The source, model, loader build, one-time sidecar construction, and "
            "bounded cleanup completed, but the first group runner could not execute. "
            "No measured worker launched and no quality, throughput, latency, CPU, "
            "RSS, or PSS result was observed. The failure supports only an exact "
            "contract retry after repairing the retained executable file mode."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--job-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        root=args.root,
        run_log=args.run_log,
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
