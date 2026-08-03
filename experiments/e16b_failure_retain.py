#!/usr/bin/env python3
"""Retain E16b's complete measurements and frozen ingestion-harness failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e16a_ingest import ARTIFACT_INPUTS
    from experiments.e16b_freeze import INPUT_PATHS
    from experiments.e16b_ingest import build_summary_from_contract
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e16a_ingest import ARTIFACT_INPUTS
    from e16b_freeze import INPUT_PATHS
    from e16b_ingest import build_summary_from_contract


def git_blob(root: Path, commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def extracted_inventory(evidence: Path) -> dict[str, Any]:
    entries: list[str] = []
    total_bytes = 0
    for path in sorted(item for item in evidence.rglob("*") if item.is_file()):
        relative = path.relative_to(evidence).as_posix()
        size = path.stat().st_size
        entries.append(f"{sha256_file(path)}  {relative}\n")
        total_bytes += size
    if not entries:
        raise ValueError("E16b artifact is empty")
    return {
        "file_count": len(entries),
        "total_regular_file_bytes": total_bytes,
        "inventory_sha256": hashlib.sha256("".join(entries).encode()).hexdigest(),
        "all_extracted_regular_files_hashed": True,
    }


def validate_frozen_inputs(
    evidence: Path, contract: dict[str, Any], root: Path, commit: str
) -> None:
    for name, relative in INPUT_PATHS.items():
        digest = hashlib.sha256(git_blob(root, commit, relative)).hexdigest()
        if digest != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E16b committed input differs for {name}")
    for name, artifact_name in ARTIFACT_INPUTS.items():
        if (
            sha256_file(evidence / artifact_name)
            != contract["inputs"][f"{name}_sha256"]
        ):
            raise ValueError(f"E16b artifact input differs for {name}")
    if (
        sha256_file(evidence / "e16a-prerequisite.json")
        != contract["inputs"]["e16a_result_sha256"]
    ):
        raise ValueError("E16b artifact prerequisite differs")


def build_manifest(
    *,
    evidence: Path,
    contract_path: Path,
    root: Path,
    run_id: str,
    run_attempt: int,
    job_id: str,
    artifact_name: str,
    artifact_id: str,
    artifact_size_bytes: int,
    artifact_digest: str,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("E16b artifact contract differs")
    provenance = load_object(evidence / "provenance.json")
    commit = provenance.get("git_commit")
    if not isinstance(commit, str) or len(commit) != 40:
        raise ValueError("E16b repository commit is invalid")
    validate_frozen_inputs(evidence, contract, root, commit)
    original_ingester = git_blob(root, commit, INPUT_PATHS["ingest"]).decode()
    if 'for case in probe["cases"]' not in original_ingester:
        raise ValueError("E16b committed ingester does not reproduce the blocker")

    diagnostic = build_summary_from_contract(
        evidence, contract, root, sha256_file(contract_path)
    )
    if (
        diagnostic.get("promoted") is not True
        or diagnostic.get("failed_gates")
        or not diagnostic.get("gates")
        or not all(diagnostic["gates"].values())
    ):
        raise ValueError("E16b descriptive replay does not clear the frozen gates")
    if (
        provenance.get("github_run_id") != run_id
        or provenance.get("github_run_attempt") != run_attempt
        or provenance.get("runner_arch") != "ARM64"
        or not all(value.isdigit() for value in (run_id, job_id, artifact_id))
        or artifact_size_bytes <= 0
        or not artifact_digest.startswith("sha256:")
        or len(artifact_digest.removeprefix("sha256:")) != 64
    ):
        raise ValueError("E16b GitHub or artifact provenance differs")
    return {
        "schema_version": 1,
        "experiment_id": "E16b",
        "status": "invalid_ingestion_harness_failure",
        "experiment_result_valid": False,
        "promotion_decision_permitted": False,
        "contract_sha256": sha256_file(contract_path),
        "completed_cells": len(diagnostic["cells"]),
        "completed_measured_requests": sum(
            len(cell["raw_cases"]) for cell in diagnostic["cells"]
        ),
        "descriptive_replay_only": {
            "all_frozen_gates_would_pass_with_the_repair": True,
            "gates": diagnostic["gates"],
            "ratios": diagnostic["ratios"],
            "performance": diagnostic["performance"],
            "construction": diagnostic["construction"],
        },
        "ingestion_failure": {
            "exception": "KeyError: 'cases'",
            "location": "summarize_configuration",
            "cause": (
                "The frozen ingester asked validate_probe's compact return value "
                "for raw cases instead of reading the already retained probe object."
            ),
            "repair_boundary": (
                "A successor may read raw cases from the validated cell while "
                "keeping model, source patch series, service, order, repetitions, "
                "requests, mechanisms, and every acceptance threshold unchanged."
            ),
        },
        "github": {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "job_id": job_id,
            "repository_commit": commit,
            "artifact_name": artifact_name,
            "artifact_id": artifact_id,
            "artifact_size_bytes": artifact_size_bytes,
            "artifact_digest": artifact_digest,
        },
        "artifact_validation": extracted_inventory(evidence),
        "claim_boundary": (
            "The complete measurements are descriptive failed-run evidence only. "
            "E16b cannot promote the loader because its frozen ingester failed; "
            "the separately frozen successor must repeat the native experiment."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact-size-bytes", type=int, required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        root=args.root,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        job_id=args.job_id,
        artifact_name=args.artifact_name,
        artifact_id=args.artifact_id,
        artifact_size_bytes=args.artifact_size_bytes,
        artifact_digest=args.artifact_digest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
