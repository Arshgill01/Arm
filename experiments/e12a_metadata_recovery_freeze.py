#!/usr/bin/env python3
"""Freeze metadata-only completion of E12a's exact inspected matrix."""

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
    "inspection_contract": Path("experiments/e12a_inspection_recovery_contract.json"),
    "failure_manifest": Path("results/manifests/e12a-inspection-recovery-30854613238.json"),
    "failure_retainer": Path("experiments/e12a_metadata_dependency_failure_retain.py"),
    "freeze": Path("experiments/e12a_metadata_recovery_freeze.py"),
    "ingest": Path("experiments/e12a_metadata_recovery_ingest.py"),
    "test": Path("tests/test_e12a_metadata_recovery.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    inspection = load_object(root / INPUT_PATHS["inspection_contract"])
    failure = load_object(root / INPUT_PATHS["failure_manifest"])
    if (
        inspection.get("experiment_id") != "E12a-inspection-recovery"
        or failure.get("status") != "invalid_postinspection_metadata_dependency_failure"
        or failure.get("matrix_compute_completed") is not True
        or failure.get("statistics_completed") is not True
        or failure.get("metadata_completed") is not False
        or failure.get("statistics", {}).get("tensor_count") != 182
        or failure.get("decision", {}).get("separately_frozen_metadata_only_recovery_allowed") is not True
        or failure.get("decision", {}).get("matrix_recomputation_allowed") is not False
        or failure.get("decision", {}).get("statistics_repetition_allowed") is not False
    ):
        raise ValueError("E12a metadata-recovery prerequisite differs")

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)

    return {
        "schema_version": 1,
        "experiment_id": "E12a-metadata-recovery",
        "title": "Metadata-only validation of exact completed E12a matrix",
        "state": (
            "frozen after retaining the successful statistics and PyYAML failure, "
            "before observing any completed metadata dump"
        ),
        "hypothesis": (
            "The exact read-only matrix that already passed the 182-tensor statistics "
            "gate also satisfies the original 32-chunk GGUF metadata gates."
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
            "matrix": failure["matrix"],
            "statistics": failure["statistics"],
        },
        "source": inspection["source"],
        "metadata": {
            "source_repository": inspection["source"]["repository"],
            "source_commit": inspection["source"]["commit"],
            "source_tag": inspection["source"]["tag"],
            "python": "3.10",
            "dependencies": ["numpy==2.2.6", "pyyaml==6.0.3"],
            "command_after_python": [
                "-m", "gguf.scripts.gguf_dump",
                "MATRIX_PATH",
                "--json",
                "--json-array",
            ],
            "matrix_recomputation_allowed": False,
            "matrix_mutation_allowed": False,
            "statistics_repetition_allowed": False,
            "native_tool_rebuild_allowed": False,
            "model_download_allowed": False,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "required_matrix_sha256": failure["matrix"]["sha256"],
            "required_matrix_size_bytes": failure["matrix"]["size_bytes"],
            "required_statistics_sha256": failure["statistics"]["sha256"],
            "required_statistics_tensors": failure["statistics"]["tensor_count"],
            "required_final_chunks": 32,
            "required_chunk_size": 512,
            "required_imatrix_entries": 182,
            "require_exact_source_artifact_inventory": True,
            "require_matrix_read_only_mode": True,
            "require_matrix_hash_unchanged": True,
            "require_ordered_dataset_metadata": True,
            "require_entry_names_match_checkpoint": True,
        },
        "decision": {
            "metadata_success_authorizes_generated_quant_successor": True,
            "failed_runs_rehabilitated": False,
            "failure_rule": (
                "Retain any artifact, inventory, source, dependency, matrix, statistics, "
                "metadata, dataset-order, chunk-count, entry-set, or post-dump hash failure."
            ),
        },
        "claim_boundary": (
            "A pass accepts the exact previously computed application-conditioned matrix "
            "without repeating computation or statistics. It is not a new calibration run "
            "and provides no generated quantization, quality, service, energy, PMU, local-"
            "device, fleet, or cost result."
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
