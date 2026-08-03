#!/usr/bin/env python3
"""Freeze inspection-only recovery of E12a's completed matrix bytes."""

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


INPUT_PATHS = {
    "resume_contract": Path("experiments/e12a_resume_contract.json"),
    "failure_manifest": Path("results/manifests/e12a-resume-30847557186.json"),
    "failure_retainer": Path("experiments/e12a_resume_inspection_failure_retain.py"),
    "freeze": Path("experiments/e12a_inspection_recovery_freeze.py"),
    "ingest": Path("experiments/e12a_inspection_recovery_ingest.py"),
    "test": Path("tests/test_e12a_inspection_recovery.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    resume = load_object(root / INPUT_PATHS["resume_contract"])
    failure = load_object(root / INPUT_PATHS["failure_manifest"])
    completed = failure.get("completed_output")
    if (
        resume.get("experiment_id") != "E12a-resume"
        or failure.get("status") != "invalid_postcompute_statistics_invocation_failure"
        or failure.get("matrix_compute_completed") is not True
        or failure.get("inspection_completed") is not False
        or failure.get("decision", {}).get("separately_frozen_inspection_only_recovery_allowed") is not True
        or failure.get("decision", {}).get("matrix_recomputation_allowed") is not False
        or not isinstance(completed, dict)
        or completed.get("process", {}).get("exit_status") != 0
        or completed.get("metadata_observed") is not False
        or completed.get("statistics_observed") is not False
    ):
        raise ValueError("E12a inspection-recovery prerequisite differs")

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)

    return {
        "schema_version": 1,
        "experiment_id": "E12a-inspection-recovery",
        "title": "Inspection-only recovery of exact completed E12a matrix bytes",
        "state": (
            "frozen after the post-compute statistics failure was retained and before "
            "observing the completed matrix's metadata or statistics"
        ),
        "hypothesis": (
            "The exact hash-bound GGUF written by the successful 24-to-32 chunk "
            "continuation satisfies the original metadata and tensor-statistics gates."
        ),
        "inputs": inputs,
        "prerequisite": {
            "failure_manifest_sha256": sha256_file(root / INPUT_PATHS["failure_manifest"]),
            "run_id": failure["github"]["run_id"],
            "run_attempt": failure["github"]["run_attempt"],
            "job_id": failure["github"]["job_id"],
            "repository_commit": failure["github"]["repository_commit"],
            "artifact_name": failure["github"]["artifact_name"],
            "artifact_id": failure["github"]["artifact_id"],
            "artifact_digest": failure["github"]["artifact_digest"],
            "artifact_size_bytes": failure["github"]["artifact_size_bytes"],
            "artifact_validation": failure["artifact_validation"],
            "completed_output": completed,
        },
        "source": resume["source"],
        "build": resume["build"],
        "model": resume["model"],
        "inspection": {
            "matrix_recomputation_allowed": False,
            "matrix_mutation_allowed": False,
            "require_read_only_mode": True,
            "require_sha256_before_and_after": True,
            "statistics_argv_after_binary": [
                "--model", "MODEL_PATH",
                "--in-file", "MATRIX_PATH",
                "--show-statistics",
                "--ctx-size", "512",
                "--threads", "4",
            ],
            "metadata_dump": "gguf-py gguf_dump --json --json-array",
            "metadata_dump_python": "Python 3.10 with numpy==2.2.6",
        },
        "acceptance": {
            **resume["acceptance"],
            "required_final_sha256": completed["sha256"],
            "required_final_size_bytes": completed["size_bytes"],
            "required_final_chunks": 32,
            "required_imatrix_entries": 182,
            "require_original_command_and_successful_process": True,
            "require_exact_artifact_inventory": True,
            "require_statistics_tensor_count": True,
            "require_hash_unchanged_after_inspection": True,
        },
        "decision": {
            "inspection_success_authorizes_generated_quant_successor": True,
            "failed_run_rehabilitated": False,
            "failure_rule": (
                "Retain any artifact, hash, inventory, native platform, source, build, "
                "model, original-command, metadata, chunk-count, entry-set, statistics, "
                "or post-inspection hash failure. Never recompute the matrix in this lane."
            ),
        },
        "claim_boundary": (
            "A pass accepts only the exact already-computed application-conditioned "
            "importance matrix under the original gates. It is not a new calibration "
            "run and provides no generated quantization, model quality, service, energy, "
            "PMU, local-device, fleet, or cost result."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
