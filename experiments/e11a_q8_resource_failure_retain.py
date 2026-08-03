#!/usr/bin/env python3
"""Retain Q8_0's valid scoring output and frozen RSS-gate failure."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e10d_ingest import (
        finite,
        validate_preflight,
        validate_prepared,
        validate_recipe,
        validate_source_and_build,
    )
    from experiments.e10f_ingest import validate_safe_probe
    from experiments.e11a_ingest import quality_coordinates
    from experiments.e11a_successor_ingest import validate_inputs
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e10d_ingest import (
        finite,
        validate_preflight,
        validate_prepared,
        validate_recipe,
        validate_source_and_build,
    )
    from e10f_ingest import validate_safe_probe
    from e11a_ingest import quality_coordinates
    from e11a_successor_ingest import validate_inputs


def compact_inventory(directory: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        size = path.stat().st_size
        row = f"{sha256_file(path)}  {relative}\n".encode()
        digest.update(row)
        file_count += 1
        total_bytes += size
    if file_count == 0:
        raise ValueError("Q8_0 artifact is empty")
    return {
        "all_extracted_regular_files_hashed": True,
        "inventory_format": "sha256, two spaces, relative POSIX path, newline",
        "inventory_sha256": digest.hexdigest(),
        "file_count": file_count,
        "total_regular_file_bytes": total_bytes,
    }


def retain(
    *,
    evidence: Path,
    contract_path: Path,
    root: Path,
    job_log: Path,
    job_metadata: Path,
    artifact_metadata: Path,
) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    model = next(
        item
        for item in contract["models"]
        if item["candidate"] == "ministral3_3b_q8_0"
    )
    adapter = load_object(evidence / "e10d-contract.json")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("Q8_0 failure evidence is not native Arm64")
    runtime = validate_source_and_build(evidence, adapter)
    validate_recipe(load_object(evidence / "recipe.json"), adapter, model)
    readiness = load_object(evidence / "readiness.json")
    ready_ms = finite(readiness.get("ready_ms"), nonnegative=True)
    if (
        readiness.get("status") != "ok"
        or ready_ms > contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError("Q8_0 failure readiness differs")
    process = parse_time_output((evidence / "server-time.log").read_text())
    rss_limit = contract["acceptance"]["maximum_process_rss_kib"]
    if (
        process["exit_status"]
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"] <= rss_limit
    ):
        raise ValueError("Q8_0 failure is not the frozen RSS-gate exceedance")
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if len(model_line) != 2 or model_line[0] != model["sha256"]:
        raise ValueError("Q8_0 failure model identity differs")
    prepared = validate_prepared(
        load_object(evidence / "prepared.json"),
        adapter,
        load_object(evidence / "sample-map.json"),
    )
    if (
        sha256_file(evidence / "prepared.json")
        != contract["prerequisite"]["prepared_sha256"]
    ):
        raise ValueError("Q8_0 failure workload differs")
    preflight = validate_preflight(evidence, adapter)
    probe = validate_safe_probe(
        evidence,
        load_object(evidence / "probe.json"),
        prepared,
        model,
        contract,
        adapter,
    )
    if probe["request_failures"] != 0:
        raise ValueError("Q8_0 failure scoring contains request failures")
    log_text = job_log.read_text(errors="replace")
    required_log_fragments = (
        '"failures": 0',
        "E11a-successor server process differs",
        "Process completed with exit code 1",
    )
    if not all(fragment in log_text for fragment in required_log_fragments):
        raise ValueError("Q8_0 job log lacks the retained RSS failure")
    job = load_object(job_metadata)
    artifact = load_object(artifact_metadata)
    github = load_object(evidence / "github.json")
    if (
        str(job.get("id")) != "91799485529"
        or job.get("conclusion") != "failure"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or str(artifact.get("id")) != "8870637364"
        or artifact.get("name")
        != "e11a-successor-ministral3_3b_q8_0-30847559089-1"
        or artifact.get("digest")
        != "sha256:5b96094a6b4ff0d6046eef8ece4f3a87f313b113911049217623d4212b4e1395"
        or github.get("run_id") != "30847559089"
        or github.get("sha") != "f3321bde74570de141266b111af364e7ea3722af"
    ):
        raise ValueError("Q8_0 GitHub identity differs")
    return {
        "schema_version": 1,
        "experiment_id": "E11a-successor",
        "status": "invalid_stock_quant_resource_gate_failure_with_valid_scoring",
        "experiment_result_valid": False,
        "stock_frontier_cell_valid": False,
        "promotion_decision_permitted": False,
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": sha256_file(evidence / "prepared.json"),
        "model": model,
        "platform": platform,
        "runtime": runtime,
        "readiness_ms": ready_ms,
        "server_process": process,
        "failure": {
            "type": "frozen_peak_rss_gate_exceeded",
            "maximum_process_rss_kib": process["maximum_rss_kib"],
            "maximum_allowed_rss_kib": rss_limit,
            "excess_rss_kib": process["maximum_rss_kib"] - rss_limit,
            "rss_ratio_to_limit": process["maximum_rss_kib"] / rss_limit,
            "server_exit_status": process["exit_status"],
            "scoring_completed_before_rejection": True,
        },
        "preflight": {
            "status": preflight["status"],
            "maximum_repeat_sum_logprob_delta": preflight[
                "maximum_repeat_sum_logprob_delta"
            ],
            "maximum_repeat_token_logprob_delta": preflight[
                "maximum_repeat_token_logprob_delta"
            ],
        },
        "quality_coordinates": quality_coordinates(probe["metrics"]),
        "scoring": probe,
        "github": {
            "run_id": github["run_id"],
            "run_attempt": github["run_attempt"],
            "job_id": str(job["id"]),
            "repository_commit": github["sha"],
            "job_conclusion": job["conclusion"],
            "run_url": "https://github.com/Arshgill01/Arm/actions/runs/30847559089",
            "job_log_sha256": sha256_file(job_log),
            "artifact_id": str(artifact["id"]),
            "artifact_name": artifact["name"],
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": artifact["digest"],
            "artifact_expires_at": artifact["expires_at"],
        },
        "artifact_validation": compact_inventory(evidence),
        "decision": {
            "q8_0_deployable_frontier_eligible": False,
            "change_frozen_rss_gate_after_observation": False,
            "repeat_scoring_required": False,
            "valid_scoring_may_be_retained_as_infeasible_point": True,
            "aggregate_successor_may_classify_resource_infeasible_point": True,
        },
        "claim_boundary": (
            "The complete safe-sampled quality scoring is structurally valid and had "
            "zero request failures, but the server exceeded the frozen 8 GiB RSS "
            "ceiling. Q8_0 is not a valid deployable stock-frontier cell and cannot "
            "be admitted by raising the resource gate after observation. Its quality "
            "coordinates may be shown only as a resource-infeasible point."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--job-log", type=Path, required=True)
    parser.add_argument("--job-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        root=args.root,
        job_log=args.job_log,
        job_metadata=args.job_metadata,
        artifact_metadata=args.artifact_metadata,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "peak_rss_kib": result["server_process"]["maximum_rss_kib"],
                "request_failures": result["scoring"]["request_failures"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
