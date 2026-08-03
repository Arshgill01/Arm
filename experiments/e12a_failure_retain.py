#!/usr/bin/env python3
"""Retain E12a's native timeout and last complete imatrix checkpoint."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e12a_ingest import ARTIFACT_INPUTS, validate_command
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file
    from e12a_ingest import ARTIFACT_INPUTS, validate_command


SUPPLEMENTAL_FILES = {
    "artifact-inventory-sha256.txt",
    "extracted-inventory-sha256.txt",
    "github-artifact.json",
    "github-run.json",
    "github-run.log",
    "imatrix-partial-metadata.json",
}


def parse_generation_log(value: str) -> dict[str, Any]:
    pass_match = re.search(r"([0-9.]+) seconds per pass - ETA (\d+) hours ([0-9.]+) minutes", value)
    chunks_match = re.search(r"computing over (\d+) chunks, n_ctx=(\d+)", value)
    if not pass_match or not chunks_match:
        raise ValueError("E12a generation log lacks its frozen ETA or chunk declaration")
    eta_seconds = int(pass_match.group(2)) * 3600 + float(pass_match.group(3)) * 60
    return {
        "seconds_per_pass": float(pass_match.group(1)),
        "estimated_generation_seconds": eta_seconds,
        "declared_chunks": int(chunks_match.group(1)),
        "context_tokens": int(chunks_match.group(2)),
    }


def validate_partial_metadata(
    metadata_dump: dict[str, Any], plan: dict[str, Any], corpus_path: str
) -> dict[str, Any]:
    metadata = metadata_dump.get("metadata")
    tensors = metadata_dump.get("tensors")
    if not isinstance(metadata, dict) or not isinstance(tensors, dict):
        raise TypeError("E12a partial GGUF dump is incomplete")

    def value(name: str) -> Any:
        field = metadata.get(name)
        return field.get("value") if isinstance(field, dict) else None

    sums = {
        name.removesuffix(".in_sum2") for name in tensors if name.endswith(".in_sum2")
    }
    counts = {
        name.removesuffix(".counts") for name in tensors if name.endswith(".counts")
    }
    checkpoint_chunks = value("imatrix.chunk_count")
    if (
        value("general.type") != "imatrix"
        or value("imatrix.datasets") != [corpus_path]
        or not isinstance(checkpoint_chunks, int)
        or checkpoint_chunks <= 0
        or checkpoint_chunks >= plan["imatrix"]["processed_chunks"]
        or checkpoint_chunks % 8 != 0
        or value("imatrix.chunk_size") != plan["imatrix"]["tokens_per_chunk"]
        or sums != counts
        or not sums
    ):
        raise ValueError("E12a partial GGUF checkpoint differs")
    return {
        "general_type": value("general.type"),
        "datasets": value("imatrix.datasets"),
        "chunk_count": checkpoint_chunks,
        "chunk_size": value("imatrix.chunk_size"),
        "entries": len(sums),
        "gguf_tensors": len(tensors),
    }


def artifact_inventory(evidence: Path) -> dict[str, Any]:
    entries: list[str] = []
    total_bytes = 0
    for path in sorted(item for item in evidence.rglob("*") if item.is_file()):
        relative = path.relative_to(evidence).as_posix()
        if relative in SUPPLEMENTAL_FILES:
            continue
        entries.append(f"{sha256_file(path)}  {relative}\n")
        total_bytes += path.stat().st_size
    retained = (evidence / "artifact-inventory-sha256.txt").read_text()
    if retained != "".join(entries):
        raise ValueError("E12a extracted artifact inventory differs")
    return {
        "file_count": len(entries),
        "total_regular_file_bytes": total_bytes,
        "inventory_sha256": sha256_file(evidence / "artifact-inventory-sha256.txt"),
        "all_extracted_regular_files_hashed": True,
    }


def build_manifest(evidence: Path, plan_path: Path, root: Path) -> dict[str, Any]:
    plan = load_object(plan_path)
    if plan.get("experiment_id") != "E12a" or load_object(evidence / "contract.json") != plan:
        raise ValueError("E12a failed artifact plan differs")
    for key, artifact_name in ARTIFACT_INPUTS.items():
        expected = plan["inputs"][f"{key}_sha256"]
        if (
            sha256_file(root / plan["inputs"][f"{key}_path"]) != expected
            or sha256_file(evidence / artifact_name) != expected
        ):
            raise ValueError(f"E12a failed artifact input differs for {key}")

    run = load_object(evidence / "github-run.json")
    artifact = load_object(evidence / "github-artifact.json")
    jobs = run.get("jobs")
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "cancelled"
        or run.get("headSha") != (evidence / "repository-commit.txt").read_text().strip()
        or not isinstance(jobs, list)
        or len(jobs) != 1
        or jobs[0].get("conclusion") != "cancelled"
        or artifact.get("name") != "e12a-imatrix-30822632328-1"
        or artifact.get("digest") != "sha256:120665a1ebc6e49f00f6f51136834a04e5b2ee3e8ffbe6c5c67f6d5480dec05d"
    ):
        raise ValueError("E12a GitHub timeout provenance differs")

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != plan["acceptance"]["required_architecture"]:
        raise ValueError("E12a timeout evidence is not native Arm64")
    command_object = load_object(evidence / "imatrix-command.json")
    command_argv = command_object.get("argv")
    if not isinstance(command_argv, list):
        raise TypeError("E12a failed artifact command is incomplete")
    corpus_path = command_argv[command_argv.index("--file") + 1]
    imatrix_path = command_argv[command_argv.index("--output-file") + 1]
    model_path = (evidence / "model-path.txt").read_text().strip()
    validate_command(
        command_object,
        plan,
        model_path=model_path,
        corpus_path=corpus_path,
        imatrix_path=imatrix_path,
    )
    checkpoint = validate_partial_metadata(
        load_object(evidence / "imatrix-partial-metadata.json"), plan, corpus_path
    )
    generation = parse_generation_log((evidence / "imatrix.log").read_text(errors="replace"))
    if (
        generation["declared_chunks"] != plan["imatrix"]["processed_chunks"]
        or generation["context_tokens"] != plan["imatrix"]["tokens_per_chunk"]
        or (evidence / "imatrix-time.log").stat().st_size != 0
        or (evidence / "summary.json").exists()
        or (evidence / "imatrix-sha256.txt").exists()
    ):
        raise ValueError("E12a timeout boundary differs")

    return {
        "schema_version": 1,
        "experiment_id": "E12a",
        "status": "invalid_native_timeout_with_resume_checkpoint",
        "experiment_result_valid": False,
        "promotion_decision_permitted": False,
        "contract_sha256": sha256_file(plan_path),
        "platform": platform,
        "source": plan["source"],
        "model": plan["model"],
        "corpus": plan["calibration"]["expected_corpus"],
        "generation": generation,
        "failure": {
            "type": "github_job_timeout",
            "job_timeout_minutes": 300,
            "generation_step_started_at": "2026-08-03T14:38:56Z",
            "generation_step_cancelled_at": "2026-08-03T19:25:51Z",
            "generation_step_elapsed_seconds": 17215,
            "message": "The operation was canceled.",
            "full_validation_reached": False,
        },
        "resume_checkpoint": {
            "path": "imatrix.gguf",
            "sha256": sha256_file(evidence / "imatrix.gguf"),
            "size_bytes": (evidence / "imatrix.gguf").stat().st_size,
            "metadata": checkpoint,
            "completed_fraction": checkpoint["chunk_count"] / plan["imatrix"]["processed_chunks"],
            "next_chunk": checkpoint["chunk_count"],
            "remaining_chunks": plan["imatrix"]["processed_chunks"] - checkpoint["chunk_count"],
            "activation_statistics_observed_before_resume_freeze": False,
        },
        "github": {
            "run_id": "30822632328",
            "run_attempt": 1,
            "run_url": run["url"],
            "job_id": str(jobs[0]["databaseId"]),
            "repository_commit": run["headSha"],
            "conclusion": run["conclusion"],
            "artifact_name": artifact["name"],
            "artifact_id": str(artifact["id"]),
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": artifact["digest"],
            "artifact_expires_at": artifact["expires_at"],
            "run_log_sha256": sha256_file(evidence / "github-run.log"),
        },
        "artifact_validation": artifact_inventory(evidence),
        "decision": {
            "application_imatrix_accepted": False,
            "original_e12b_dispatch_allowed": False,
            "timeout_retained": True,
            "separately_frozen_exact_checkpoint_resume_allowed": True,
            "resume_may_change_model_corpus_source_chunks_or_gates": False,
        },
        "claim_boundary": (
            "E12a produced a structurally valid 24-of-32-chunk periodic checkpoint "
            "before its native job timed out. It is not a complete importance matrix, "
            "quantized-model result, or quality/performance claim. Only a separately "
            "frozen exact continuation from chunk 24 may use it."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.plan, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
