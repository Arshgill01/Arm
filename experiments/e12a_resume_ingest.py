#!/usr/bin/env python3
"""Validate the exact native continuation of E12a's periodic checkpoint."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e12a_resume_freeze import INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure
    from e12a_resume_freeze import INPUT_PATHS


BASE_ARTIFACT_INPUTS = {
    "application_tasks": "application-tasks.json",
    "sample_generator": "sample-generator.py",
    "sample_map": "sample-map.json",
    "corpus_generator": "corpus-generator.py",
    "task_utils": "task-utils.py",
    "requirements": "requirements.txt",
}

SUCCESSOR_ARTIFACT_INPUTS = {
    "freeze": "resume-freeze.py",
    "ingest": "resume-ingest.py",
    "test": "resume-test.py",
}


def metadata_parts(dump: dict[str, Any]) -> tuple[dict[str, Any], set[str], set[str]]:
    metadata = dump.get("metadata")
    tensors = dump.get("tensors")
    if not isinstance(metadata, dict) or not isinstance(tensors, dict):
        raise TypeError("E12a resume GGUF dump is incomplete")

    def value(name: str) -> Any:
        field = metadata.get(name)
        return field.get("value") if isinstance(field, dict) else None

    values = {
        "general_type": value("general.type"),
        "datasets": value("imatrix.datasets"),
        "chunk_count": value("imatrix.chunk_count"),
        "chunk_size": value("imatrix.chunk_size"),
        "gguf_tensors": len(tensors),
    }
    sums = {
        name.removesuffix(".in_sum2") for name in tensors if name.endswith(".in_sum2")
    }
    counts = {
        name.removesuffix(".counts") for name in tensors if name.endswith(".counts")
    }
    return values, sums, counts


def validate_metadata_pair(
    prior_dump: dict[str, Any],
    final_dump: dict[str, Any],
    contract: dict[str, Any],
    current_corpus_path: str,
) -> dict[str, Any]:
    prior, prior_sums, prior_counts = metadata_parts(prior_dump)
    final, final_sums, final_counts = metadata_parts(final_dump)
    prerequisite = contract["prerequisite"]["checkpoint"]
    expected_prior_dataset = prerequisite["metadata"]["datasets"][0]
    if (
        prior["general_type"] != "imatrix"
        or prior["datasets"] != [expected_prior_dataset]
        or prior["chunk_count"] != contract["acceptance"]["required_checkpoint_chunks"]
        or prior["chunk_size"] != contract["resume"]["tokens_per_chunk"]
        or prior_sums != prior_counts
        or len(prior_sums) != contract["acceptance"]["required_imatrix_entries"]
    ):
        raise ValueError("E12a resume prerequisite metadata differs")
    if (
        final["general_type"] != "imatrix"
        or final["datasets"] != [expected_prior_dataset, current_corpus_path]
        or final["chunk_count"] != contract["acceptance"]["required_final_chunks"]
        or final["chunk_size"] != contract["resume"]["tokens_per_chunk"]
        or final_sums != final_counts
        or final_sums != prior_sums
    ):
        raise ValueError("E12a resumed final metadata differs")
    return {**final, "entries": len(final_sums), "entry_names_match_checkpoint": True}


def validate_resume_command(
    command: dict[str, Any],
    contract: dict[str, Any],
    *,
    model_path: str,
    corpus_path: str,
    checkpoint_path: str,
    imatrix_path: str,
) -> list[str]:
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not argv[0].endswith("/llama-imatrix"):
        raise TypeError("E12a resume command is incomplete")
    replacements = {
        "MODEL_PATH": model_path,
        "CORPUS_PATH": corpus_path,
        "CHECKPOINT_PATH": checkpoint_path,
        "IMATRIX_PATH": imatrix_path,
    }
    expected = [argv[0]] + [
        replacements.get(argument, argument)
        for argument in contract["resume"]["argv_after_binary"]
    ]
    if argv != expected:
        raise ValueError("E12a resume command differs from the frozen continuation")
    return argv


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("experiment_id") != "E12a-resume" or load_object(evidence / "contract.json") != contract:
        raise ValueError("contract does not identify the E12a resume")
    for name, relative in INPUT_PATHS.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if sha256_file(root / relative) != expected:
            raise ValueError(f"E12a resume input differs for {name}")
    for name, artifact_name in SUCCESSOR_ARTIFACT_INPUTS.items():
        if sha256_file(evidence / artifact_name) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E12a resume artifact input differs for {name}")
    if sha256_file(evidence / "prerequisite-manifest.json") != contract["inputs"]["failure_manifest_sha256"]:
        raise ValueError("E12a resume prerequisite manifest differs")

    base = load_object(root / contract["inputs"]["base_plan_path"])
    if load_object(evidence / "base-contract.json") != base:
        raise ValueError("E12a resume base contract differs")
    for key, artifact_name in BASE_ARTIFACT_INPUTS.items():
        expected = base["inputs"][f"{key}_sha256"]
        if (
            sha256_file(root / base["inputs"][f"{key}_path"]) != expected
            or sha256_file(evidence / artifact_name) != expected
        ):
            raise ValueError(f"E12a resume base input differs for {key}")

    checkpoint_path = evidence / "prior/imatrix.gguf"
    prerequisite = contract["prerequisite"]
    if (
        sha256_file(checkpoint_path) != prerequisite["checkpoint"]["sha256"]
        or checkpoint_path.stat().st_size != prerequisite["checkpoint"]["size_bytes"]
        or load_object(evidence / "prior/base-contract.json") != base
    ):
        raise ValueError("E12a resume checkpoint identity differs")

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E12a resume evidence is not native Arm64")
    if load_object(evidence / "source.json") != contract["source"]:
        raise ValueError("E12a resume source identity differs")
    if sha256_file(evidence / "source-diff.patch") != contract["source"]["source_diff_sha256"]:
        raise ValueError("E12a resume source diff differs")
    configure = load_object(evidence / "build/configure-command.json")
    if configure.get("cmake_arguments") != contract["build"]["cmake_arguments"]:
        raise ValueError("E12a resume configure command differs")
    build_process = parse_time_output((evidence / "build/build-time.log").read_text())
    if build_process["exit_status"] != 0 or build_process["maximum_rss_kib"] is None:
        raise ValueError("E12a resume build process differs")
    closures = {}
    for tool in contract["build"]["targets"]:
        closure = validate_runtime_closure(evidence / f"build/{tool}-runtime-closure.json")
        dependency_names = sorted(
            {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
        )
        if set(contract["build"]["forbidden_dynamic_dependency_basenames"]).intersection(dependency_names):
            raise ValueError(f"E12a resume {tool} retains a forbidden dependency")
        closures[tool] = {"closure": closure, "dynamic_dependency_basenames": dependency_names}

    corpus = evidence / "calibration.txt"
    expected_corpus = contract["calibration"]["expected_corpus"]
    corpus_manifest = load_object(evidence / "corpus-manifest.json")
    if (
        any(corpus_manifest.get(key) != value for key, value in expected_corpus.items())
        or corpus.stat().st_size != expected_corpus["corpus_bytes"]
        or sha256_file(corpus) != expected_corpus["corpus_sha256"]
        or load_object(evidence / "generated-sample-map.json") != load_object(evidence / "sample-map.json")
    ):
        raise ValueError("E12a resume corpus differs")

    model_path = (evidence / "model-path.txt").read_text().strip()
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if len(model_line) != 2 or model_line[0] != contract["model"]["sha256"] or model_line[1] != model_path:
        raise ValueError("E12a resume BF16 model differs")
    imatrix_path = evidence / "imatrix.gguf"
    command = validate_resume_command(
        load_object(evidence / "imatrix-command.json"),
        contract,
        model_path=model_path,
        corpus_path=str(corpus),
        checkpoint_path=str(checkpoint_path),
        imatrix_path=str(imatrix_path),
    )
    process = parse_time_output((evidence / "imatrix-time.log").read_text())
    if process["exit_status"] != 0 or process["maximum_rss_kib"] is None:
        raise ValueError("E12a resume process differs")
    metadata = validate_metadata_pair(
        load_object(evidence / "prior-imatrix-metadata.json"),
        load_object(evidence / "imatrix-metadata.json"),
        contract,
        str(corpus),
    )
    log = (evidence / "imatrix.log").read_text(errors="replace")
    if (
        f"loading imatrix from '{checkpoint_path}'" not in log
        or f"removing initial {contract['resume']['from_chunk']} chunks" not in log
        or f"computing over {contract['resume']['new_chunks']} chunks" not in log
    ):
        raise ValueError("E12a resume mechanism log differs")
    statistics = (evidence / "imatrix-statistics.log").read_text(errors="replace")
    match = re.search(r"Computing statistics for .* \((\d+) tensors\)", statistics)
    if not match or int(match.group(1)) != metadata["entries"]:
        raise ValueError("E12a resume statistics differ")
    output_sha = sha256_file(imatrix_path)
    retained_line = (evidence / "imatrix-sha256.txt").read_text().split()
    if len(retained_line) != 2 or retained_line[0] != output_sha:
        raise ValueError("E12a resumed imatrix digest evidence differs")

    return {
        "schema_version": 1,
        "experiment_id": "E12a-resume",
        "status": "valid_resumed_application_conditioned_imatrix",
        "contract_sha256": sha256_file(contract_path),
        "base_contract_sha256": prerequisite["base_contract_sha256"],
        "platform": platform,
        "source": contract["source"],
        "build": {
            "configure_command": configure,
            "process": build_process,
            "imatrix_version": (evidence / "build/imatrix-version.txt").read_text(errors="replace").strip(),
            "quantize_sha256": (evidence / "build/quantize-sha256.txt").read_text().strip(),
            "runtime_closures": closures,
        },
        "model": contract["model"],
        "corpus": expected_corpus,
        "prerequisite_checkpoint": prerequisite["checkpoint"],
        "command": command,
        "process": process,
        "imatrix": {
            "path": "imatrix.gguf",
            "sha256": output_sha,
            "size_bytes": imatrix_path.stat().st_size,
            "metadata": metadata,
            "statistics_sha256": sha256_file(evidence / "imatrix-statistics.log"),
        },
        "validation": {
            "native_arm64": True,
            "exact_source_build_model": True,
            "exact_checkpoint_identity": True,
            "deterministic_frozen_corpus": True,
            "holdouts_excluded": True,
            "ordered_chunk_24_resume": True,
            "complete_chunk_count": True,
            "entry_names_match_checkpoint": True,
            "gguf_metadata_valid": True,
            "statistics_retained": True,
            "model_promoted": False,
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
