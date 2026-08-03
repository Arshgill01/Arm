#!/usr/bin/env python3
"""Retain E12a resume's post-compute statistics invocation failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e12a_resume_ingest import validate_resume_command
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e12a_resume_ingest import validate_resume_command


RUN_ID = "30847557186"
JOB_ID = "91799481977"
ARTIFACT_ID = "8871558287"
ARTIFACT_NAME = "e12a-resume-30847557186-1"
ARTIFACT_DIGEST = "sha256:b5590336f79101eba00e18fa1d2bfd2c52173e437b9fc28a4d0ba2cc3394ffc2"
OUTPUT_SHA256 = "2338867f1b51341e02d0f63ca4d7281731a94b0738d80413476581ae991a1548"
OUTPUT_SIZE_BYTES = 3_010_048

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
        raise ValueError("E12a post-compute failure artifact inventory differs")
    return {
        "file_count": len(entries),
        "total_regular_file_bytes": total_bytes,
        "inventory_sha256": sha256_file(inventory),
        "all_extracted_regular_files_hashed": True,
    }


def option_value(argv: list[str], option: str) -> str:
    try:
        return argv[argv.index(option) + 1]
    except (ValueError, IndexError) as error:
        raise ValueError(f"E12a resume command lacks {option}") from error


def build_manifest(evidence: Path, contract_relative: str, root: Path) -> dict[str, Any]:
    run = load_object(evidence / "github-run.json")
    artifact = load_object(evidence / "github-artifact.json")
    jobs = run.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 1:
        raise ValueError("E12a post-compute failure job metadata differs")
    job = jobs[0]
    steps = job.get("steps")
    failed_steps = [step for step in steps or [] if step.get("conclusion") == "failure"]
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or str(job.get("databaseId")) != JOB_ID
        or job.get("conclusion") != "failure"
        or len(failed_steps) != 1
        or failed_steps[0].get("name") != "Resume chunks 24 through 31 and inspect complete matrix"
        or artifact.get("id") != int(ARTIFACT_ID)
        or artifact.get("name") != ARTIFACT_NAME
        or artifact.get("digest") != ARTIFACT_DIGEST
    ):
        raise ValueError("E12a post-compute failure provenance differs")

    contract_bytes = git_blob(root, run["headSha"], contract_relative)
    contract = json.loads(contract_bytes)
    if (
        contract.get("experiment_id") != "E12a-resume"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E12a post-compute failure contract differs")

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E12a post-compute failure is not native Arm64")

    command_object = load_object(evidence / "imatrix-command.json")
    argv = command_object.get("argv")
    if not isinstance(argv, list):
        raise TypeError("E12a resume command is incomplete")
    command = validate_resume_command(
        command_object,
        contract,
        model_path=(evidence / "model-path.txt").read_text().strip(),
        corpus_path=option_value(argv, "--file"),
        checkpoint_path=option_value(argv, "--in-file"),
        imatrix_path=option_value(argv, "--output-file"),
    )
    process = parse_time_output((evidence / "imatrix-time.log").read_text())
    output = evidence / "imatrix.gguf"
    retained_digest = (evidence / "imatrix-sha256.txt").read_text().split()
    log = (evidence / "imatrix.log").read_text(errors="replace")
    run_log = (evidence / "github-run.log").read_text(errors="replace")
    statistics = (evidence / "imatrix-statistics.log").read_text(errors="replace")
    if (
        process["exit_status"] != 0
        or process["maximum_rss_kib"] is None
        or output.stat().st_size != OUTPUT_SIZE_BYTES
        or sha256_file(output) != OUTPUT_SHA256
        or len(retained_digest) != 2
        or retained_digest[0] != OUTPUT_SHA256
        or f"loading imatrix from '{option_value(argv, '--in-file')}'" not in log
        or "removing initial 24 chunks (12288 tokens)" not in log
        or "computing over 8 chunks" not in log
    ):
        raise ValueError("E12a completed continuation evidence differs")
    if (
        statistics.strip() != "error: --model is required"
        or "error: --model is required" not in run_log
        or (evidence / "imatrix-metadata.json").exists()
        or (evidence / "summary.json").exists()
    ):
        raise ValueError("E12a post-compute inspection failure boundary differs")

    return {
        "schema_version": 1,
        "experiment_id": "E12a-resume",
        "status": "invalid_postcompute_statistics_invocation_failure",
        "experiment_result_valid": False,
        "matrix_compute_completed": True,
        "inspection_completed": False,
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "platform": platform,
        "completed_output": {
            "path": "imatrix.gguf",
            "sha256": OUTPUT_SHA256,
            "size_bytes": OUTPUT_SIZE_BYTES,
            "command": command,
            "process": process,
            "metadata_observed": False,
            "statistics_observed": False,
        },
        "failure": {
            "stage": "post-compute statistics inspection",
            "exception": "error: --model is required",
            "cause": (
                "The resumed matrix process exited successfully and wrote its final GGUF. "
                "The following llama-imatrix --show-statistics invocation omitted the "
                "required --model argument, so the step failed before statistics and "
                "metadata validation."
            ),
            "repair_boundary": (
                "A separately frozen successor may download the exact retained artifact, "
                "rebuild the exact native tool, download the exact BF16 model, add only "
                "the required --model argument to the statistics-only invocation, and "
                "dump metadata. It may not recompute or modify the matrix."
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
            "separately_frozen_inspection_only_recovery_allowed": True,
            "matrix_recomputation_allowed": False,
        },
        "claim_boundary": (
            "The retained bytes are a successfully computed candidate matrix, but the "
            "frozen experiment remains invalid until exact metadata and statistics gates "
            "pass. This run provides no generated quantization, quality, service, energy, "
            "PMU, device, cost, or performance result."
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
