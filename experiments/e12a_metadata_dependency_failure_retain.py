#!/usr/bin/env python3
"""Retain E12a's metadata-only PyYAML dependency failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file


RUN_ID = "30854613238"
JOB_ID = "91822569926"
ARTIFACT_ID = "8872135870"
ARTIFACT_NAME = "e12a-inspection-recovery-30854613238-1"
ARTIFACT_DIGEST = "sha256:8575c0714a93dcf808a9017d18319431835d38fddaa281527b4fc9e343da92b2"
MATRIX_SHA256 = "2338867f1b51341e02d0f63ca4d7281731a94b0738d80413476581ae991a1548"
STATISTICS_SHA256 = "64aa1fa92b333347fb22106fe484230ad6e01baf3b4978c32c358f2cbd39bc66"

SUPPLEMENTAL = {
    "artifact-inventory-sha256.txt",
    "github-artifact.json",
    "github-run.json",
    "github-run.log",
}


def git_blob(root: Path, commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def artifact_inventory(evidence: Path) -> dict[str, Any]:
    entries: list[str] = []
    total_bytes = 0
    files = (item for item in evidence.rglob("*") if item.is_file())
    for item in sorted(files, key=lambda value: value.relative_to(evidence).as_posix()):
        relative = item.relative_to(evidence).as_posix()
        if relative in SUPPLEMENTAL:
            continue
        entries.append(f"{sha256_file(item)}  {relative}\n")
        total_bytes += item.stat().st_size
    inventory = evidence / "artifact-inventory-sha256.txt"
    if inventory.read_text() != "".join(entries):
        raise ValueError("E12a metadata failure artifact inventory differs")
    return {
        "file_count": len(entries),
        "total_regular_file_bytes": total_bytes,
        "inventory_sha256": sha256_file(inventory),
        "all_extracted_regular_files_hashed": True,
    }


def digest_line(path: Path) -> str:
    fields = path.read_text().split()
    if len(fields) != 2:
        raise ValueError(f"invalid digest line: {path}")
    return fields[0]


def build_manifest(evidence: Path, contract_relative: str, root: Path) -> dict[str, Any]:
    run = load_object(evidence / "github-run.json")
    artifact = load_object(evidence / "github-artifact.json")
    jobs = run.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 1:
        raise ValueError("E12a metadata failure job metadata differs")
    job = jobs[0]
    failed_steps = [
        step for step in job.get("steps", []) if step.get("conclusion") == "failure"
    ]
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or str(job.get("databaseId")) != JOB_ID
        or len(failed_steps) != 1
        or failed_steps[0].get("name") != "Inspect exact matrix without recomputation"
        or artifact.get("id") != int(ARTIFACT_ID)
        or artifact.get("name") != ARTIFACT_NAME
        or artifact.get("digest") != ARTIFACT_DIGEST
    ):
        raise ValueError("E12a metadata failure provenance differs")

    contract_bytes = git_blob(root, run["headSha"], contract_relative)
    contract = json.loads(contract_bytes)
    if (
        contract.get("experiment_id") != "E12a-inspection-recovery"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E12a metadata failure contract differs")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E12a metadata failure is not native Arm64")

    inspection_process = parse_time_output((evidence / "inspection-time.log").read_text())
    statistics = (evidence / "imatrix-statistics.log").read_text(errors="replace")
    statistics_path = evidence / "imatrix-statistics.log"
    tensor_count = re.search(r"Computing statistics for .* \((\d+) tensors\)", statistics)
    run_log = (evidence / "github-run.log").read_text(errors="replace")
    matrix = evidence / "completed/imatrix.gguf"
    if (
        inspection_process["exit_status"] != 0
        or not tensor_count
        or int(tensor_count.group(1)) != 182
        or sha256_file(statistics_path) != STATISTICS_SHA256
        or matrix.stat().st_size != 3_010_048
        or sha256_file(matrix) != MATRIX_SHA256
        or digest_line(evidence / "matrix-before-sha256.txt") != MATRIX_SHA256
        or digest_line(evidence / "matrix-after-sha256.txt") != MATRIX_SHA256
    ):
        raise ValueError("E12a completed statistics evidence differs")
    if (
        "ModuleNotFoundError: No module named 'yaml'" not in run_log
        or (evidence / "imatrix-metadata.json").stat().st_size != 0
        or (evidence / "summary.json").exists()
    ):
        raise ValueError("E12a metadata dependency failure boundary differs")

    return {
        "schema_version": 1,
        "experiment_id": "E12a-inspection-recovery",
        "status": "invalid_postinspection_metadata_dependency_failure",
        "experiment_result_valid": False,
        "matrix_compute_completed": True,
        "statistics_completed": True,
        "metadata_completed": False,
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "platform": platform,
        "matrix": {
            "sha256": MATRIX_SHA256,
            "size_bytes": matrix.stat().st_size,
            "unchanged_before_and_after_inspection": True,
        },
        "statistics": {
            "sha256": sha256_file(statistics_path),
            "tensor_count": int(tensor_count.group(1)),
            "process": inspection_process,
        },
        "failure": {
            "stage": "post-statistics GGUF metadata dump",
            "exception": "ModuleNotFoundError: No module named 'yaml'",
            "cause": (
                "The inspection venv pinned NumPy but omitted PyYAML, which gguf-py's "
                "package import requires before the metadata dumper can start."
            ),
            "repair_boundary": (
                "A separately frozen metadata-only successor may download this exact "
                "artifact, check out the exact gguf-py source, install numpy==2.2.6 and "
                "pyyaml==6.0.3, and dump the exact read-only matrix. It may not rebuild "
                "the native tool, redownload the model, repeat statistics, recompute, or "
                "modify the matrix."
            ),
        },
        "github": {
            "run_id": RUN_ID,
            "run_attempt": 1,
            "run_url": run["url"],
            "job_id": JOB_ID,
            "repository_commit": run["headSha"],
            "artifact_name": ARTIFACT_NAME,
            "artifact_id": ARTIFACT_ID,
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": ARTIFACT_DIGEST,
            "run_log_sha256": sha256_file(evidence / "github-run.log"),
        },
        "artifact_validation": artifact_inventory(evidence),
        "decision": {
            "complete_imatrix_accepted": False,
            "generated_quant_dispatch_allowed": False,
            "failed_run_rehabilitated": False,
            "separately_frozen_metadata_only_recovery_allowed": True,
            "matrix_recomputation_allowed": False,
            "statistics_repetition_allowed": False,
        },
        "claim_boundary": (
            "The exact matrix and complete 182-tensor statistics are retained, but the "
            "original metadata gate remains unevaluated. This run provides no generated "
            "quantization, quality, service, energy, PMU, device, cost, or performance result."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument(
        "--contract-relative",
        default="experiments/e12a_inspection_recovery_contract.json",
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract_relative, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
