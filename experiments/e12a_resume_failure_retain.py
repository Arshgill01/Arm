#!/usr/bin/env python3
"""Retain E12a resume's precompute Python-environment failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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
    paths = (item for item in evidence.rglob("*") if item.is_file())
    for path in sorted(paths, key=lambda item: item.relative_to(evidence).as_posix()):
        relative = path.relative_to(evidence).as_posix()
        if relative in SUPPLEMENTAL:
            continue
        entries.append(f"{sha256_file(path)}  {relative}\n")
        total_bytes += path.stat().st_size
    if (evidence / "artifact-inventory-sha256.txt").read_text() != "".join(entries):
        raise ValueError("E12a resume failure artifact inventory differs")
    return {
        "file_count": len(entries),
        "total_regular_file_bytes": total_bytes,
        "inventory_sha256": sha256_file(evidence / "artifact-inventory-sha256.txt"),
        "all_extracted_regular_files_hashed": True,
    }


def build_manifest(evidence: Path, contract_relative: str, root: Path) -> dict[str, Any]:
    run = load_object(evidence / "github-run.json")
    artifact = load_object(evidence / "github-artifact.json")
    jobs = run.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 1:
        raise ValueError("E12a resume failure job metadata differs")
    contract_bytes = git_blob(root, run["headSha"], contract_relative)
    contract = json.loads(contract_bytes)
    if (
        contract.get("experiment_id") != "E12a-resume"
        or load_object(evidence / "contract.json") != contract
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or jobs[0].get("conclusion") != "failure"
        or artifact.get("name") != "e12a-resume-30846528784-1"
        or artifact.get("digest") != "sha256:c055436c6d86bfccb3d535227d47df58bad126bfe17189720fe1d25fd68f5090"
    ):
        raise ValueError("E12a resume failure provenance differs")
    log = (evidence / "github-run.log").read_text(errors="replace")
    if (
        "ModuleNotFoundError: No module named 'numpy'" not in log
        or (evidence / "prior-imatrix-metadata.json").stat().st_size != 0
        or (evidence / "imatrix-command.json").exists()
        or (evidence / "imatrix.log").exists()
        or (evidence / "imatrix.gguf").exists()
        or sha256_file(evidence / "prior/imatrix.gguf") != contract["prerequisite"]["checkpoint"]["sha256"]
        or sha256_file(evidence / "calibration.txt") != contract["calibration"]["expected_corpus"]["corpus_sha256"]
    ):
        raise ValueError("E12a resume precompute failure boundary differs")
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if len(model_line) != 2 or model_line[0] != contract["model"]["sha256"]:
        raise ValueError("E12a resume downloaded model identity differs")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E12a resume failure is not native Arm64")
    return {
        "schema_version": 1,
        "experiment_id": "E12a-resume",
        "status": "invalid_premeasurement_python_environment_failure",
        "experiment_result_valid": False,
        "matrix_compute_started": False,
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "platform": platform,
        "validated_before_failure": {
            "exact_checkpoint_downloaded": True,
            "exact_contract_and_inputs": True,
            "exact_corpus_reproduced": True,
            "exact_native_tools_built": True,
            "exact_bf16_model_downloaded": True,
        },
        "failure": {
            "stage": "prerequisite GGUF metadata dump",
            "exception": "ModuleNotFoundError: No module named 'numpy'",
            "cause": (
                "The workflow invoked gguf-py's metadata dumper with the bare setup-python "
                "interpreter. NumPy was installed only in the already-created pinned corpus venv."
            ),
            "repair_boundary": (
                "A separately frozen successor may invoke both GGUF metadata dumps with "
                "the pinned corpus venv interpreter. Checkpoint, model, corpus, source, "
                "chunk range, command, statistics and every acceptance gate must remain unchanged."
            ),
        },
        "checkpoint": contract["prerequisite"]["checkpoint"],
        "github": {
            "run_id": "30846528784",
            "run_attempt": 1,
            "run_url": run["url"],
            "job_id": str(jobs[0]["databaseId"]),
            "repository_commit": run["headSha"],
            "artifact_name": artifact["name"],
            "artifact_id": str(artifact["id"]),
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": artifact["digest"],
            "run_log_sha256": sha256_file(evidence / "github-run.log"),
        },
        "artifact_validation": artifact_inventory(evidence),
        "decision": {
            "complete_imatrix_accepted": False,
            "generated_quant_dispatch_allowed": False,
            "first_resume_rehabilitated": False,
            "separately_frozen_interpreter_repair_allowed": True,
        },
        "claim_boundary": (
            "The resume stopped before its first matrix operation. It contains no "
            "completed-matrix statistics, generated quantization, quality, service, "
            "energy, PMU, device, cost, or performance result."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract-relative", default="experiments/e12a_resume_contract.json")
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
