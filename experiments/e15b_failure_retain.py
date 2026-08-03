#!/usr/bin/env python3
"""Retain E15b's premeasurement executable-mode failure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e15a_failure_retain import inventory
    from experiments.e15a_split_scheduler_ingest import validate_runtime
    from experiments.e15b_affinity_ingest import validate_inputs
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file
    from e15a_failure_retain import inventory
    from e15a_split_scheduler_ingest import validate_runtime
    from e15b_affinity_ingest import validate_inputs


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
    runtime = validate_runtime(evidence, contract)
    run = load_object(run_metadata)
    job = load_object(job_metadata)
    artifact = load_object(artifact_metadata)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    host_affinity = load_object(evidence / "host-affinity.json")
    if (
        platform["architecture"] != contract["acceptance"]["required_architecture"]
        or platform["model_name"] != contract["acceptance"]["required_model_name"]
        or platform["logical_cpus"]
        < contract["acceptance"]["minimum_host_logical_cpus"]
        or host_affinity.get("available_cpu_ids") != [0, 1, 2, 3]
        or host_affinity.get("selected_cpu_ids") != [0, 1]
        or host_affinity.get("selected_cpu_list") != "0,1"
    ):
        raise ValueError("E15b failure host affinity differs")
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if (
        len(model_line) != 2
        or model_line[0] != contract["selected"]["model_sha256"]
        or int((evidence / "model-size.txt").read_text())
        != contract["selected"]["model_size_bytes"]
    ):
        raise ValueError("E15b failure model identity differs")
    cells_dir = evidence / "cells"
    if cells_dir.exists() and any(cells_dir.iterdir()):
        raise ValueError("E15b failure unexpectedly contains measured cells")
    log_text = run_log.read_text(errors="replace")
    required_log_fragments = (
        "experiments/e15b_affinity_cell.sh: Permission denied",
        "Process completed with exit code 126",
    )
    if not all(fragment in log_text for fragment in required_log_fragments):
        raise ValueError("E15b run log lacks the retained permission failure")
    github = load_object(evidence / "github.json")
    if (
        str(run.get("id")) != github.get("run_id")
        or run.get("run_attempt") != github.get("run_attempt")
        or run.get("head_sha") != github.get("sha")
        or run.get("conclusion") != "failure"
        or str(job.get("id")) != "91811407599"
        or job.get("conclusion") != "failure"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or str(artifact.get("id")) != "8870681540"
        or artifact.get("name")
        != "e15b-affinity-split-scheduler-30851213422-1"
        or artifact.get("digest")
        != "sha256:43533c5778be9c3924f99d94fb0a464258e2b5d7a3774aec3693a26e1ea4ed74"
    ):
        raise ValueError("E15b GitHub identity differs")
    return {
        "schema_version": 1,
        "experiment_id": "E15b",
        "status": "invalid_premeasurement_cell_runner_permission_failure",
        "experiment_result_valid": False,
        "promotion_decision_permitted": False,
        "contract_sha256": sha256_file(contract_path),
        "failure": {
            "type": "executable_mode_missing",
            "message": "experiments/e15b_affinity_cell.sh: Permission denied",
            "shell_exit_status": 126,
            "runtime_and_model_verified": True,
            "affinity_selection_frozen_and_recorded": True,
            "measured_server_processes_started": 0,
            "measured_requests_completed": 0,
            "scheduler_result_observed": False,
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
        "host_affinity": host_affinity,
        "runtime": runtime,
        "model": contract["selected"],
        "artifact_validation": inventory(evidence),
        "decision": {
            "e15b_promoted": False,
            "change_contract_or_gates": False,
            "exact_contract_retry_after_executable_mode_repair_allowed": True,
        },
        "claim_boundary": (
            "The exact E9a runtime, model, host, and lowest-two-CPU affinity selection "
            "were verified, but the first cell runner could not execute. No measured "
            "server started and no scheduler result was observed. The failure supports "
            "only an exact contract retry after repairing the retained file mode."
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
