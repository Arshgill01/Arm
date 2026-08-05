#!/usr/bin/env python3
"""Retain E17c's terminal timing-schema failure without KV claims."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e17c_ingest import validate_inputs, validate_recipe
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure
    from e17c_ingest import validate_inputs, validate_recipe


RUN_ID = 30867998030
JOB_ID = 91863877220
ARTIFACT_ID = 8879497249
ARTIFACT_NAME = "e17c-shorter-context-density-30867998030-1"
ARTIFACT_DIGEST = (
    "sha256:069ba1b3e79f21c2609b8478cf9e91607523852e6aa5c3c1098f97361610eb31"
)
HEAD_SHA = "4021e21d0d656685559933781e3eedc266eb0e3d"
ARTIFACT_FILES = 144
LOCAL_FILES = {"artifact-metadata.json", "run-metadata.json"}
CELL_FILES = {
    "caller-exit.txt",
    "memory-before.txt",
    "process-limits-ready.txt",
    "process-smaps-ready.txt",
    "process-status-ready.txt",
    "readiness.json",
    "recipe.json",
    "server-pid.txt",
    "server-time.log",
    "server.stderr.log",
    "server.stdout.log",
}


def validate_artifact_inventory(evidence: Path) -> dict[str, Any]:
    files = [
        path
        for path in evidence.rglob("*")
        if path.is_file() and path.relative_to(evidence).as_posix() not in LOCAL_FILES
    ]
    relative = {path.relative_to(evidence).as_posix() for path in files}
    required = {
        "contract.json",
        "e9a-artifact.json",
        "e9a-workflow-summary.json",
        "frozen-inputs/experiments/e17c_ingest.py",
        "frozen-inputs/experiments/e17c_probe.py",
        "lscpu.txt",
        "model-sha256.txt",
        "runtime/runtime-closure.json",
        "runtime/runtime-files/bin/llama-server",
    }
    if len(files) != ARTIFACT_FILES or not required.issubset(relative):
        raise ValueError("E17c source artifact inventory is incomplete")
    rows = [
        f"{sha256_file(path)}  {path.relative_to(evidence).as_posix()}"
        for path in sorted(files, key=lambda item: item.relative_to(evidence).as_posix())
    ]
    data = ("\n".join(rows) + "\n").encode()
    return {
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "independent_inventory_sha256": hashlib.sha256(data).hexdigest(),
        "all_artifact_files_hashed": True,
    }


def validate_static_identity(
    evidence: Path, contract_path: Path, root: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_object(contract_path)
    if (
        contract.get("experiment_id") != "E17c"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E17c retained contract differs")
    validate_inputs(evidence, root, contract)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E17c retained platform is not Arm64")
    if load_object(evidence / "e9a-workflow-summary.json") != load_object(
        root / contract["inputs"]["e9a_manifest_path"]
    ):
        raise ValueError("E17c retained E9a summary differs")
    artifact = load_object(evidence / "e9a-artifact.json")
    expected_artifact = contract["runtime"]["artifact"]
    if (
        str(artifact.get("id")) != expected_artifact["id"]
        or artifact.get("name") != expected_artifact["name"]
        or artifact.get("digest") != expected_artifact["digest"]
        or artifact.get("size_in_bytes") != expected_artifact["size_bytes"]
    ):
        raise ValueError("E17c retained E9a artifact differs")
    closure = validate_runtime_closure(evidence / "runtime/runtime-closure.json")
    server = evidence / "runtime/runtime-files/bin/llama-server"
    model_digest = (evidence / "model-sha256.txt").read_text().split()
    if (
        sha256_file(server) != contract["runtime"]["server_sha256"]
        or len(model_digest) != 2
        or model_digest[0] != contract["selected"]["model_sha256"]
    ):
        raise ValueError("E17c retained runtime or model differs")
    return contract, platform, closure


def validate_failed_cells(
    evidence: Path, contract: dict[str, Any]
) -> list[dict[str, Any]]:
    cells = []
    for index, item in enumerate(contract["execution"]["cells"], start=1):
        name = (
            f"{index:02d}-{item['configuration']}-s{item['slots']}"
            f"-r{item['repetition']}"
        )
        path = evidence / "cells" / name
        names = {child.name for child in path.iterdir() if child.is_file()}
        recipe = load_object(path / "recipe.json")
        readiness = load_object(path / "readiness.json")
        validate_recipe(recipe, contract, **item)
        if (
            names != CELL_FILES
            or (path / "caller-exit.txt").read_text().strip() != "1"
            or (path / "probe.json").exists()
            or readiness.get("status") != "ok"
            or not isinstance(readiness.get("ready_ms"), (int, float))
        ):
            raise ValueError(f"E17c failed cell evidence differs for {name}")
        cells.append(
            {
                "configuration": item["configuration"],
                "slots": item["slots"],
                "repetition": item["repetition"],
                "caller_exit_status": 1,
                "readiness_written": True,
                "probe_written": False,
                "failure_class": "invalid_encode_ms_timing_schema",
                "recipe_sha256": sha256_file(path / "recipe.json"),
                "server_time_sha256": sha256_file(path / "server-time.log"),
                "server_stderr_sha256": sha256_file(path / "server.stderr.log"),
            }
        )
    return cells


def retain(
    *,
    evidence: Path,
    contract_path: Path,
    root: Path,
    run_metadata: Path,
    artifact_metadata: Path,
    failed_log: Path,
) -> dict[str, Any]:
    contract, platform, closure = validate_static_identity(
        evidence, contract_path, root
    )
    cells = validate_failed_cells(evidence, contract)
    failure_text = failed_log.read_text(errors="replace")
    if (
        failure_text.count("ValueError: invalid E17b encode_ms") != 9
        or failure_text.count("ValueError: E17c f16 four-slot control did not serve")
        != 1
    ):
        raise ValueError("E17c retained failure log differs")

    run = load_object(run_metadata)
    artifacts = load_object(artifact_metadata).get("artifacts", [])
    jobs = run.get("jobs", [])
    selected = [item for item in artifacts if item.get("id") == ARTIFACT_ID]
    if len(jobs) != 1 or len(selected) != 1:
        raise ValueError("E17c run or artifact count differs")
    job = jobs[0]
    artifact = selected[0]
    steps = {step.get("name"): step.get("conclusion") for step in job.get("steps", [])}
    if (
        str(run.get("databaseId")) != str(RUN_ID)
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("headSha") != HEAD_SHA
        or job.get("databaseId") != JOB_ID
        or job.get("conclusion") != "failure"
        or steps.get("Run all nine frozen shorter-context cells") != "success"
        or steps.get("Independently validate shorter-context density") != "failure"
        or steps.get("Upload complete E17c evidence") != "success"
        or artifact.get("name") != ARTIFACT_NAME
        or artifact.get("digest") != ARTIFACT_DIGEST
        or artifact.get("expired") is not False
        or str(artifact.get("workflow_run", {}).get("id")) != str(RUN_ID)
        or artifact.get("workflow_run", {}).get("head_sha") != HEAD_SHA
        or (evidence / "repository-commit.txt").read_text().strip() != HEAD_SHA
    ):
        raise ValueError("E17c retained GitHub identity differs")
    return {
        "schema_version": 1,
        "experiment_id": "E17c",
        "status": "invalid_8k_context_timing_schema_no_kv_claim",
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "selected": contract["selected"],
        "runtime": {
            "artifact": contract["runtime"]["artifact"],
            "closure": closure,
        },
        "cells": cells,
        "failure": {
            "failed_cells": 9,
            "repeated_exception": "ValueError: invalid E17b encode_ms",
            "final_ingester_exception": (
                "ValueError: E17c f16 four-slot control did not serve"
            ),
            "failure_log_sha256": sha256_file(failed_log),
            "completed_probe_files": 0,
        },
        "github": {
            "run_id": str(RUN_ID),
            "run_attempt": 1,
            "run_url": run["url"],
            "run_conclusion": "failure",
            "job_id": str(JOB_ID),
            "repository_commit": HEAD_SHA,
            "artifact_id": str(ARTIFACT_ID),
            "artifact_name": ARTIFACT_NAME,
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": ARTIFACT_DIGEST,
            "artifact_expires_at": artifact["expires_at"],
        },
        "artifact_validation": validate_artifact_inventory(evidence),
        "decision": {
            "quality_claim_allowed": False,
            "throughput_claim_allowed": False,
            "latency_claim_allowed": False,
            "cpu_claim_allowed": False,
            "kv_density_claim_allowed": False,
            "kv_configuration_promoted": False,
            "e17b_failed_contract_rehabilitated": False,
            "eight_k_lane_parked": True,
            "successor_or_rerun_authorized": False,
        },
        "validation": {
            "native_arm64": True,
            "exact_e9a_runtime_closure": True,
            "exact_selected_model": True,
            "all_frozen_inputs_match": True,
            "all_nine_cells_accounted_for": True,
            "all_nine_callers_failed": True,
            "no_completed_probe_output": True,
            "partial_server_logs_not_reinterpreted": True,
        },
        "claim_boundary": (
            "E17c establishes only that every frozen probe aborted because the "
            "retained response timing shape did not satisfy require_timings' "
            "encode_ms contract. It makes no answer-quality, throughput, latency, "
            "CPU, K/V density, 8K viability, energy, PMU, device, fleet, or cost claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--failed-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        root=args.root,
        run_metadata=args.run_metadata,
        artifact_metadata=args.artifact_metadata,
        failed_log=args.failed_log,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
