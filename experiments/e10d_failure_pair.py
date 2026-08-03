#!/usr/bin/env python3
"""Aggregate two independently retained failed E10d model cells."""

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


def compact_cell(value: dict[str, Any], path: Path) -> dict[str, Any]:
    partial = value["partial_evidence"]
    return {
        "candidate": value["model"]["candidate"],
        "role": value["model"]["role"],
        "quantization": value["model"]["quantization"],
        "status": value["status"],
        "manifest_path": str(path),
        "manifest_sha256": sha256_file(path),
        "artifact": value["github"],
        "prepared_sha256": value["prepared_sha256"],
        "strict_ingest_error": value["strict_ingest_error"],
        "probe_result": partial["probe_result"],
        "errors": partial["errors"],
        "raw_inventory": partial["raw_inventory"],
        "completed_choice_records": partial["completed_choice_records"],
        "completed_token_records": partial["completed_token_records"],
        "referenced_raw_responses": partial["referenced_raw_responses"],
        "unreferenced_partial_raw_responses": partial[
            "unreferenced_partial_raw_responses"
        ],
        "received_response_count_including_unretained_failures": partial[
            "received_response_count_including_unretained_failures"
        ],
        "unattempted_frozen_token_requests": partial[
            "unattempted_frozen_token_requests"
        ],
        "preflight": value["preflight"],
        "server_process": value["server_process"],
    }


def build_pair(
    primary_path: Path,
    control_path: Path,
    contract_path: Path,
    primary_job_id: str,
    control_job_id: str,
) -> dict[str, Any]:
    primary = load_object(primary_path)
    control = load_object(control_path)
    contract = load_object(contract_path)
    cells = [primary, control]
    run_ids = {cell.get("github", {}).get("run_id") for cell in cells}
    attempts = {cell.get("github", {}).get("run_attempt") for cell in cells}
    expected_models = contract["models"]
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E10d"
        or len(run_ids) != 1
        or len(attempts) != 1
        or not all(
            cell.get("status") == "invalid_external_holdout_cell_retained"
            and cell.get("contract_sha256") == sha256_file(contract_path)
            and cell.get("decision", {}).get("negative_result_retained") is True
            and cell.get("decision", {}).get("metrics_comparable") is False
            and cell.get("platform", {}).get("architecture") == "aarch64"
            for cell in cells
        )
        or [cell.get("model") for cell in cells] != expected_models
        or not primary_job_id.isdigit()
        or not control_job_id.isdigit()
    ):
        raise ValueError("failed E10d pair differs from the frozen contract")
    if primary["prepared_sha256"] != control["prepared_sha256"]:
        raise ValueError("failed E10d cells used different prepared workloads")
    run_id = next(iter(run_ids))
    run_attempt = next(iter(attempts))
    compact = [compact_cell(primary, primary_path), compact_cell(control, control_path)]
    compact[0]["github_job_id"] = primary_job_id
    compact[1]["github_job_id"] = control_job_id
    return {
        "schema_version": 1,
        "experiment_id": "E10d",
        "status": "invalid_external_holdout_pair_retained",
        "contract_sha256": sha256_file(contract_path),
        "github": {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "conclusion": "failure",
            "aggregate_job_conclusion": "skipped",
        },
        "prepared_sha256": primary["prepared_sha256"],
        "platform": primary["platform"],
        "cells": compact,
        "failure_case_union": sorted(
            {
                (
                    error["task"],
                    error["sample_ordinal"],
                    error["source_index"],
                    error["failed_choice_index"],
                    error["failed_token_index"],
                    error["failed_target_token_id"],
                )
                for cell in compact
                for error in cell["errors"]
            }
        ),
        "validation": {
            "native_arm64": True,
            "same_frozen_workload": True,
            "both_artifacts_independently_ingested": True,
            "both_models_complete": False,
            "zero_request_failures": False,
            "paired_aggregate_valid": False,
            "partial_metrics_comparable": False,
            "per_sample_and_raw_logs_retained": True,
        },
        "decision": {
            "external_holdout_claim_accepted": False,
            "original_e11a_dispatch_allowed": False,
            "original_e12b_dispatch_allowed": False,
            "original_contract_rewrite_allowed": False,
            "bounded_compatibility_preflight_allowed": True,
            "negative_result_retained": True,
        },
        "claim_boundary": "E10d failed its frozen zero-request-failure gate in both model cells, so no paired model, task-quality, frontier, promotion, performance, energy, PMU, cost, cache, concurrency, or runtime-comparison claim is valid. Partial outcomes are descriptive only.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--primary-job-id", required=True)
    parser.add_argument("--control-job-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = build_pair(
        args.primary,
        args.control,
        args.contract,
        args.primary_job_id,
        args.control_job_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
