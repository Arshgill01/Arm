#!/usr/bin/env python3
"""Retain E20a's validator-only failure after complete profiling."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e20a_ingest import build_manifest
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file
    from e20a_ingest import build_manifest


RUN_ID = 30863505489
JOB_ID = 91850309924
HEAD_SHA = "ba0c43172f583ebbb488888873442d39364d1749"
ARTIFACT_ID = 8875743768
ARTIFACT_NAME = "e20a-cpu-node-timing-30863505489-1"
ARTIFACT_DIGEST = (
    "sha256:8b7da293603cb229e0d0aa1164c19d1d3521ab0f6353ae56f2a6a90524a53247"
)


def inventory(evidence: Path) -> dict[str, Any]:
    files = []
    total = 0
    for path in sorted(
        (item for item in evidence.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(evidence).as_posix(),
    ):
        size = path.stat().st_size
        files.append(
            {
                "path": path.relative_to(evidence).as_posix(),
                "size_bytes": size,
                "sha256": sha256_file(path),
            }
        )
        total += size
    return {
        "file_count": len(files),
        "total_regular_file_bytes": total,
        "all_extracted_regular_files_hashed": True,
        "files": files,
    }


def retain(
    *,
    evidence: Path,
    root: Path,
    run_metadata: Path,
    job_metadata: Path,
    artifact_metadata: Path,
    job_log: Path,
) -> dict[str, Any]:
    run = load_object(run_metadata)
    job = load_object(job_metadata)
    artifacts = load_object(artifact_metadata).get("artifacts", [])
    selected = [item for item in artifacts if item.get("id") == ARTIFACT_ID]
    failed = [step for step in job.get("steps", []) if step.get("conclusion") == "failure"]
    if (
        run.get("id") != RUN_ID
        or run.get("run_attempt") != 1
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("head_sha") != HEAD_SHA
        or job.get("id") != JOB_ID
        or job.get("run_id") != RUN_ID
        or job.get("status") != "completed"
        or job.get("conclusion") != "failure"
        or job.get("head_sha") != HEAD_SHA
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or len(failed) != 1
        or failed[0].get("name")
        != "Independently validate and select or reject a fusion family"
        or len(selected) != 1
        or selected[0].get("name") != ARTIFACT_NAME
        or selected[0].get("digest") != ARTIFACT_DIGEST
        or selected[0].get("expired") is not False
    ):
        raise ValueError("E20a GitHub identity differs")
    for name in (
        "Build exact instrumentable OpenSSL-off runtime",
        "Download exact selected model",
        "Run six frozen control and timed benchmark cases",
        "Prove exact selected quality with timing enabled",
        "Upload complete software-timing evidence",
    ):
        matches = [step for step in job["steps"] if step.get("name") == name]
        if len(matches) != 1 or matches[0].get("conclusion") != "success":
            raise ValueError(f"E20a completed boundary differs for {name}")

    contract_path = root / "experiments/e20a_contract.json"
    contract = load_object(contract_path)
    if (
        contract.get("experiment_id") != "E20a"
        or sha256_file(contract_path)
        != "93b78071c89edee24969dd3e4d66ae2eb63de2b782b5be0a6a3b25ffec002ed2"
        or load_object(evidence / "contract.json") != contract
        or (evidence / "summary.json").exists()
        or (evidence / "file-inventory-sha256.txt").exists()
    ):
        raise ValueError("E20a failure contract boundary differs")
    verified_inputs = 0
    for key, relative in contract["inputs"].items():
        if not key.endswith("_path"):
            continue
        name = key.removesuffix("_path")
        expected = contract["inputs"][f"{name}_sha256"]
        if sha256_file(evidence / "frozen-inputs" / relative) != expected:
            raise ValueError(f"E20a frozen input differs: {relative}")
        if name not in {"ingest", "test"} and sha256_file(root / relative) != expected:
            raise ValueError(f"E20a retained input differs: {relative}")
        verified_inputs += 1
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if (
        platform["architecture"] != "aarch64"
        or len(list((evidence / "bench").glob("*"))) != 6
        or not (evidence / "quality/probe.json").is_file()
        or not (evidence / "provenance.json").is_file()
    ):
        raise ValueError("E20a profiling evidence boundary differs")
    log = job_log.read_text(errors="replace")
    if (
        "ValueError: E20a benchmark result differs for pp512_control" not in log
        or "experiments/e20a_ingest.py" not in log
        or "Independently validate and select or reject a fusion family" not in log
    ):
        raise ValueError("E20a failure log differs")

    replay = build_manifest(
        evidence,
        contract_path,
        root,
        corrected_ingestion_recovery=True,
    )
    replay_bytes = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    selection = replay.get("selection", {})
    quality = replay.get("quality", {}).get("probe", {})
    if (
        replay.get("status") != "valid_cpu_node_profile_fusion_candidate"
        or selection.get("selected_family") != "ffn_gate_up"
        or selection.get("automatic_source_optimization_allowed") is not False
        or quality.get("correct") != 23
        or quality.get("failures") != 0
        or replay.get("validation", {}).get("timed_results_used_for_performance_claim")
        is not False
    ):
        raise ValueError("E20a corrected deterministic replay differs")
    artifact = selected[0]
    return {
        "schema_version": 1,
        "experiment_id": "E20a",
        "status": "invalid_post_profile_ingestion_failure_with_complete_replay",
        "experiment_result_valid": False,
        "fusion_successor_permitted": False,
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "validated_before_failure": {
            "native_arm64": True,
            "exact_contract": True,
            "frozen_inputs_verified": verified_inputs,
            "instrumented_runtime_built": True,
            "all_six_benchmark_cases_completed": True,
            "exact_quality_pass_completed": True,
        },
        "failure": {
            "stage": "independent post-profile ingestion",
            "type": "llama_bench_model_size_semantics_mismatch",
            "scientific_measurement_failure": False,
            "raw_profile_complete": True,
            "workflow_summary_written": False,
            "workflow_inventory_written": False,
            "reason": (
                "The validator compared llama-bench's reported tensor-data model "
                "size with the larger complete GGUF file size already verified by "
                "SHA-256 and stat."
            ),
            "additional_replay_bug": (
                "After correcting that metadata assumption, deterministic replay "
                "encountered a valid zero-work GET_ROWS node with one zero extent. "
                "The recovery parser accepts non-negative extents while retaining "
                "the frozen positive-record threshold."
            ),
        },
        "corrected_replay_preview": {
            "python_line": "3.12",
            "summary_sha256": hashlib.sha256(replay_bytes).hexdigest(),
            "status": replay["status"],
            "quality": {
                "correct": quality["correct"],
                "total": quality["total"],
                "failures": quality["failures"],
                "reference_prediction_mismatches": quality[
                    "reference_prediction_mismatches"
                ],
            },
            "selection": selection,
            "preview_is_fusion_authorization": False,
        },
        "github": {
            "run_id": RUN_ID,
            "run_attempt": 1,
            "run_url": run["html_url"],
            "job_id": JOB_ID,
            "repository_commit": HEAD_SHA,
            "artifact_id": str(ARTIFACT_ID),
            "artifact_name": ARTIFACT_NAME,
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": ARTIFACT_DIGEST,
            "artifact_expires_at": artifact["expires_at"],
            "job_log_sha256": sha256_file(job_log),
        },
        "artifact_validation": inventory(evidence),
        "decision": {
            "failed_workflow_rehabilitated": False,
            "inspection_only_native_recovery_allowed": True,
            "source_or_measurement_rerun_allowed": False,
            "fusion_implementation_allowed_before_recovery": False,
            "timed_traces_are_performance_claims": False,
        },
        "claim_boundary": (
            "This failed workflow makes no fusion-target or performance claim. A "
            "separately frozen inspection-only recovery may verify the exact artifact "
            "and run only the corrected selector. Timed traces remain diagnostic and "
            "cannot support service speed, PMU, cache-counter, energy, fleet, cost, "
            "or optimization-win claims."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--job-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--job-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        evidence=args.evidence_dir,
        root=args.root,
        run_metadata=args.run_metadata,
        job_metadata=args.job_metadata,
        artifact_metadata=args.artifact_metadata,
        job_log=args.job_log,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
