#!/usr/bin/env python3
"""Validate inspection-only recovery of E12a's exact completed matrix."""

from __future__ import annotations

import argparse
import json
import re
import stat
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e12a_inspection_recovery_freeze import INPUT_PATHS
    from experiments.e12a_resume_ingest import (
        validate_metadata_pair,
        validate_resume_command,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure
    from e12a_inspection_recovery_freeze import INPUT_PATHS
    from e12a_resume_ingest import validate_metadata_pair, validate_resume_command


def option_value(argv: list[str], option: str) -> str:
    try:
        return argv[argv.index(option) + 1]
    except (ValueError, IndexError) as error:
        raise ValueError(f"command lacks {option}") from error


def validate_inspection_command(
    command: dict[str, Any],
    contract: dict[str, Any],
    *,
    model_path: str,
    matrix_path: str,
) -> list[str]:
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not argv[0].endswith("/llama-imatrix"):
        raise TypeError("E12a inspection command is incomplete")
    replacements = {"MODEL_PATH": model_path, "MATRIX_PATH": matrix_path}
    expected = [argv[0]] + [
        replacements.get(argument, argument)
        for argument in contract["inspection"]["statistics_argv_after_binary"]
    ]
    if argv != expected:
        raise ValueError("E12a inspection command differs from the frozen contract")
    return argv


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
        "inventory_sha256": __import__("hashlib").sha256("".join(entries).encode()).hexdigest(),
        "all_extracted_regular_files_hashed": True,
    }


def digest_line(path: Path) -> str:
    fields = path.read_text().split()
    if len(fields) != 2:
        raise ValueError(f"invalid digest line: {path}")
    return fields[0]


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("experiment_id") != "E12a-inspection-recovery"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E12a inspection-recovery contract differs")
    for name, relative in INPUT_PATHS.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if sha256_file(root / relative) != expected:
            raise ValueError(f"E12a inspection-recovery input differs for {name}")
    if load_object(evidence / "failure-manifest.json") != load_object(
        root / INPUT_PATHS["failure_manifest"]
    ):
        raise ValueError("E12a inspection-recovery failure manifest differs")

    original_artifact = load_object(evidence / "original-artifact.json")
    prerequisite = contract["prerequisite"]
    if (
        str(original_artifact.get("id")) != prerequisite["artifact_id"]
        or original_artifact.get("name") != prerequisite["artifact_name"]
        or original_artifact.get("digest") != prerequisite["artifact_digest"]
        or original_artifact.get("size_in_bytes") != prerequisite["artifact_size_bytes"]
        or artifact_inventory(evidence / "completed") != prerequisite["artifact_validation"]
    ):
        raise ValueError("E12a inspection-recovery source artifact differs")

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E12a inspection recovery is not native Arm64")
    if load_object(evidence / "source.json") != contract["source"]:
        raise ValueError("E12a inspection source identity differs")
    if sha256_file(evidence / "source-diff.patch") != contract["source"]["source_diff_sha256"]:
        raise ValueError("E12a inspection source diff differs")
    configure = load_object(evidence / "build/configure-command.json")
    if configure.get("cmake_arguments") != contract["build"]["cmake_arguments"]:
        raise ValueError("E12a inspection configure command differs")
    build_process = parse_time_output((evidence / "build/build-time.log").read_text())
    if build_process["exit_status"] != 0 or build_process["maximum_rss_kib"] is None:
        raise ValueError("E12a inspection native build differs")
    closure = validate_runtime_closure(evidence / "build/llama-imatrix-runtime-closure.json")
    dependency_names = sorted(
        {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
    )
    forbidden = set(contract["build"]["forbidden_dynamic_dependency_basenames"])
    if forbidden.intersection(dependency_names):
        raise ValueError("E12a inspection binary retains a forbidden dependency")

    model_path = (evidence / "model-path.txt").read_text().strip()
    model_digest = (evidence / "model-sha256.txt").read_text().split()
    if (
        len(model_digest) != 2
        or model_digest[0] != contract["model"]["sha256"]
        or model_digest[1] != model_path
    ):
        raise ValueError("E12a inspection BF16 model differs")

    completed = evidence / "completed"
    original_contract = load_object(completed / "contract.json")
    if original_contract != load_object(root / INPUT_PATHS["resume_contract"]):
        raise ValueError("E12a completed artifact contract differs")
    original_command_object = load_object(completed / "imatrix-command.json")
    original_argv = original_command_object.get("argv")
    if not isinstance(original_argv, list):
        raise TypeError("E12a completed artifact command differs")
    original_command = validate_resume_command(
        original_command_object,
        original_contract,
        model_path=(completed / "model-path.txt").read_text().strip(),
        corpus_path=option_value(original_argv, "--file"),
        checkpoint_path=option_value(original_argv, "--in-file"),
        imatrix_path=option_value(original_argv, "--output-file"),
    )
    original_process = parse_time_output((completed / "imatrix-time.log").read_text())
    if original_process["exit_status"] != 0 or original_process["maximum_rss_kib"] is None:
        raise ValueError("E12a completed matrix process differs")

    matrix = completed / "imatrix.gguf"
    expected_sha = contract["acceptance"]["required_final_sha256"]
    if (
        matrix.stat().st_size != contract["acceptance"]["required_final_size_bytes"]
        or sha256_file(matrix) != expected_sha
        or stat.S_IMODE(matrix.stat().st_mode) != 0o444
        or digest_line(evidence / "matrix-before-sha256.txt") != expected_sha
        or digest_line(evidence / "matrix-after-sha256.txt") != expected_sha
    ):
        raise ValueError("E12a inspection changed or misidentified matrix bytes")

    inspection_command = validate_inspection_command(
        load_object(evidence / "inspection-command.json"),
        contract,
        model_path=model_path,
        matrix_path=str(matrix),
    )
    inspection_process = parse_time_output((evidence / "inspection-time.log").read_text())
    statistics = (evidence / "imatrix-statistics.log").read_text(errors="replace")
    count_match = re.search(r"Computing statistics for .* \((\d+) tensors\)", statistics)
    if (
        inspection_process["exit_status"] != 0
        or inspection_process["maximum_rss_kib"] is None
        or not count_match
        or int(count_match.group(1)) != contract["acceptance"]["required_imatrix_entries"]
    ):
        raise ValueError("E12a inspection statistics differ")

    metadata = validate_metadata_pair(
        load_object(completed / "prior-imatrix-metadata.json"),
        load_object(evidence / "imatrix-metadata.json"),
        original_contract,
        option_value(original_argv, "--file"),
    )
    github = load_object(evidence / "github.json")
    if github.get("runner_arch") != "ARM64":
        raise ValueError("E12a inspection GitHub runner identity differs")

    return {
        "schema_version": 1,
        "experiment_id": "E12a-inspection-recovery",
        "status": "valid_application_conditioned_imatrix_inspection_recovery",
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "source": contract["source"],
        "build": {
            "configure_command": configure,
            "process": build_process,
            "runtime_closure": closure,
            "dynamic_dependency_basenames": dependency_names,
        },
        "model": contract["model"],
        "source_artifact": {
            "run_id": prerequisite["run_id"],
            "run_attempt": prerequisite["run_attempt"],
            "artifact_name": prerequisite["artifact_name"],
            "artifact_id": prerequisite["artifact_id"],
            "artifact_digest": prerequisite["artifact_digest"],
            "artifact_validation": prerequisite["artifact_validation"],
        },
        "original_compute": {
            "command": original_command,
            "process": original_process,
        },
        "inspection": {
            "command": inspection_command,
            "process": inspection_process,
            "matrix_sha256_before": expected_sha,
            "matrix_sha256_after": expected_sha,
            "matrix_read_only_mode": "0444",
            "statistics_sha256": sha256_file(evidence / "imatrix-statistics.log"),
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
            "original_compute_exit_zero": True,
            "matrix_recomputed": False,
            "matrix_bytes_unchanged": True,
            "exact_source_build_model": True,
            "complete_chunk_count": True,
            "entry_names_match_checkpoint": True,
            "gguf_metadata_valid": True,
            "statistics_retained": True,
            "generated_quant_dispatch_allowed": True,
            "failed_run_rehabilitated": False,
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
