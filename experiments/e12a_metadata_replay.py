#!/usr/bin/env python3
"""Replay E12a metadata ingestion after archive path/mode rehydration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import experiments.e12a_metadata_recovery_ingest as ingest
    from experiments.e5b_ingest import load_object
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    import e12a_metadata_recovery_ingest as ingest
    from e5b_ingest import load_object


def build_manifest(evidence: Path, contract: Path, root: Path) -> dict:
    github = load_object(evidence / "github.json")
    command = load_object(evidence / "metadata-command.json")
    argv = command.get("argv")
    if not isinstance(argv, list) or len(argv) < 4:
        raise ValueError("E12a retained metadata command differs")
    run_id = github.get("run_id")
    run_attempt = github.get("run_attempt")
    expected_matrix = (
        f"/home/runner/work/Arm/Arm/results/raw/e12a-metadata-recovery-"
        f"{run_id}-{run_attempt}/source-artifact/completed/imatrix.gguf"
    )
    recorded_matrix = argv[3]
    if recorded_matrix != expected_matrix:
        raise ValueError("E12a retained runner matrix path differs")

    local_matrix = evidence / "source-artifact/completed/imatrix.gguf"
    local_matrix.chmod(0o444)
    original_validate = ingest.validate_command

    def validate_recorded(command_value, contract_value, *, matrix_path):
        if matrix_path != str(local_matrix):
            raise ValueError("E12a replay local matrix path differs")
        return original_validate(
            command_value,
            contract_value,
            matrix_path=recorded_matrix,
        )

    ingest.validate_command = validate_recorded
    try:
        return ingest.build_manifest(evidence, contract, root)
    finally:
        ingest.validate_command = original_validate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
