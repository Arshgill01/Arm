#!/usr/bin/env python3
"""Validate metadata-only completion of E12a's exact matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e12a_metadata_recovery_freeze import INPUT_PATHS
    from experiments.e12a_resume_ingest import validate_metadata_pair
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file
    from e12a_metadata_recovery_freeze import INPUT_PATHS
    from e12a_resume_ingest import validate_metadata_pair


STATISTICS_COUNT = re.compile(r"Computing statistics for .* \((\d+) tensors\)")


def option_value(argv: list[str], option: str) -> str:
    try:
        return argv[argv.index(option) + 1]
    except (ValueError, IndexError) as error:
        raise ValueError(f"E12a original command lacks {option}") from error


def artifact_inventory(evidence: Path) -> dict[str, Any]:
    entries: list[str] = []
    total_bytes = 0
    files = (item for item in evidence.rglob("*") if item.is_file())
    for item in sorted(files, key=lambda value: value.relative_to(evidence).as_posix()):
        relative = item.relative_to(evidence).as_posix()
        entries.append(f"{sha256_file(item)}  {relative}\n")
        total_bytes += item.stat().st_size
    return {
        "file_count": len(entries),
        "total_regular_file_bytes": total_bytes,
        "inventory_sha256": hashlib.sha256("".join(entries).encode()).hexdigest(),
        "all_extracted_regular_files_hashed": True,
    }


def digest_line(path: Path) -> str:
    fields = path.read_text().split()
    if len(fields) != 2:
        raise ValueError(f"invalid digest line: {path}")
    return fields[0]


def validate_command(
    command: dict[str, Any],
    contract: dict[str, Any],
    *,
    matrix_path: str,
) -> list[str]:
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not argv[0].endswith("/python"):
        raise TypeError("E12a metadata command is incomplete")
    replacements = {"MATRIX_PATH": matrix_path}
    expected = [argv[0]] + [
        replacements.get(argument, argument)
        for argument in contract["metadata"]["command_after_python"]
    ]
    if argv != expected:
        raise ValueError("E12a metadata command differs from the frozen contract")
    return argv


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("experiment_id") != "E12a-metadata-recovery"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E12a metadata-recovery contract differs")
    for name, relative in INPUT_PATHS.items():
        if sha256_file(root / relative) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E12a metadata-recovery input differs for {name}")
    if load_object(evidence / "failure-manifest.json") != load_object(
        root / INPUT_PATHS["failure_manifest"]
    ):
        raise ValueError("E12a metadata-recovery failure manifest differs")

    prerequisite = contract["prerequisite"]
    artifact = load_object(evidence / "source-artifact.json")
    source_artifact = evidence / "source-artifact"
    if (
        str(artifact.get("id")) != prerequisite["artifact_id"]
        or artifact.get("name") != prerequisite["artifact_name"]
        or artifact.get("digest") != prerequisite["artifact_digest"]
        or artifact.get("size_in_bytes") != prerequisite["artifact_size_bytes"]
        or artifact_inventory(source_artifact) != prerequisite["artifact_validation"]
    ):
        raise ValueError("E12a metadata-recovery source artifact differs")

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E12a metadata recovery is not native Arm64")
    gguf_source = load_object(evidence / "gguf-source.json")
    if (
        gguf_source.get("repository") != contract["metadata"]["source_repository"]
        or gguf_source.get("commit") != contract["metadata"]["source_commit"]
        or gguf_source.get("tag") != contract["metadata"]["source_tag"]
        or gguf_source.get("clean") is not True
    ):
        raise ValueError("E12a metadata parser source differs")
    installed = {
        line.strip().lower() for line in (evidence / "pip-freeze.txt").read_text().splitlines()
        if line.strip()
    }
    if installed != set(contract["metadata"]["dependencies"]):
        raise ValueError("E12a metadata parser dependencies differ")

    matrix = source_artifact / "completed/imatrix.gguf"
    expected_sha = contract["acceptance"]["required_matrix_sha256"]
    if (
        matrix.stat().st_size != contract["acceptance"]["required_matrix_size_bytes"]
        or sha256_file(matrix) != expected_sha
        or stat.S_IMODE(matrix.stat().st_mode) != 0o444
        or digest_line(evidence / "matrix-before-sha256.txt") != expected_sha
        or digest_line(evidence / "matrix-after-sha256.txt") != expected_sha
    ):
        raise ValueError("E12a metadata recovery changed or misidentified matrix bytes")

    statistics_path = source_artifact / "imatrix-statistics.log"
    statistics = statistics_path.read_text(errors="replace")
    count = STATISTICS_COUNT.search(statistics)
    if (
        sha256_file(statistics_path) != contract["acceptance"]["required_statistics_sha256"]
        or not count
        or int(count.group(1)) != contract["acceptance"]["required_statistics_tensors"]
    ):
        raise ValueError("E12a retained statistics differ")

    command = validate_command(
        load_object(evidence / "metadata-command.json"),
        contract,
        matrix_path=str(matrix),
    )
    completed = source_artifact / "completed"
    original_contract = load_object(completed / "contract.json")
    original_command = load_object(completed / "imatrix-command.json").get("argv")
    if not isinstance(original_command, list):
        raise TypeError("E12a original matrix command differs")
    metadata = validate_metadata_pair(
        load_object(completed / "prior-imatrix-metadata.json"),
        load_object(evidence / "imatrix-metadata.json"),
        original_contract,
        option_value(original_command, "--file"),
    )
    github = load_object(evidence / "github.json")
    if github.get("runner_arch") != "ARM64":
        raise ValueError("E12a metadata-recovery runner identity differs")

    return {
        "schema_version": 1,
        "experiment_id": "E12a-metadata-recovery",
        "status": "valid_application_conditioned_imatrix_metadata_recovery",
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "source_artifact": {
            "run_id": prerequisite["run_id"],
            "artifact_name": prerequisite["artifact_name"],
            "artifact_id": prerequisite["artifact_id"],
            "artifact_digest": prerequisite["artifact_digest"],
            "artifact_validation": prerequisite["artifact_validation"],
        },
        "metadata_parser": {
            "source": gguf_source,
            "dependencies": sorted(installed),
            "command": command,
        },
        "statistics": {
            "sha256": sha256_file(statistics_path),
            "tensor_count": int(count.group(1)),
            "repeated": False,
        },
        "imatrix": {
            "sha256": expected_sha,
            "size_bytes": matrix.stat().st_size,
            "metadata": metadata,
        },
        "github": github,
        "validation": {
            "native_arm64": True,
            "exact_source_artifact_inventory": True,
            "exact_retained_statistics": True,
            "statistics_repeated": False,
            "matrix_recomputed": False,
            "native_tool_rebuilt": False,
            "model_downloaded": False,
            "matrix_bytes_unchanged": True,
            "complete_chunk_count": True,
            "entry_names_match_checkpoint": True,
            "ordered_dataset_metadata": True,
            "gguf_metadata_valid": True,
            "generated_quant_dispatch_allowed": True,
            "failed_runs_rehabilitated": False,
        },
        "decision": contract["decision"],
        "claim_boundary": contract["claim_boundary"],
    }


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
    print(json.dumps({"status": manifest["status"], "imatrix": manifest["imatrix"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
