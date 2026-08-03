#!/usr/bin/env python3
"""Aggregate E11a after one complete cell failed only its frozen RSS gate."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e11a_ingest import pareto_frontier, quality_coordinates
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e11a_ingest import pareto_frontier, quality_coordinates


VALID_CELL_STATUS = "valid_safe_sampled_stock_quant_cell"
Q8_FAILURE_STATUS = "invalid_stock_quant_resource_gate_failure_with_valid_scoring"


def require_true(value: dict[str, Any], names: tuple[str, ...], label: str) -> None:
    validation = value.get("validation")
    if not isinstance(validation, dict) or not all(
        validation.get(name) is True for name in names
    ):
        raise ValueError(f"{label} validation differs")


def validate_artifacts(
    contract: dict[str, Any], metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    expected = {
        f"e11a-successor-{candidate}-{contract['source_run']['run_id']}-1"
        for candidate in contract["attempted_candidates"]
    }
    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, list):
        raise TypeError("E11a recovery artifact metadata differs")
    selected = [artifact for artifact in artifacts if artifact.get("name") in expected]
    if (
        len(selected) != len(expected)
        or {artifact["name"] for artifact in selected} != expected
    ):
        raise ValueError("E11a recovery artifact set differs")
    for artifact in selected:
        workflow_run = artifact.get("workflow_run", {})
        if (
            artifact.get("expired") is not False
            or not isinstance(artifact.get("id"), int)
            or not isinstance(artifact.get("size_in_bytes"), int)
            or artifact["size_in_bytes"] <= 0
            or re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest", "")) is None
            or str(workflow_run.get("id")) != contract["source_run"]["run_id"]
            or workflow_run.get("head_sha")
            != contract["source_run"]["repository_commit"]
        ):
            raise ValueError("E11a recovery artifact identity differs")
    return sorted(selected, key=lambda artifact: artifact["name"])


def aggregate(
    *,
    contract_path: Path,
    original_contract_path: Path,
    cell_paths: list[Path],
    anchor_path: Path,
    q8_failure_path: Path,
    artifact_metadata_path: Path,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    original = load_object(original_contract_path)
    if (
        contract.get("experiment_id") != "E11a-successor-recovery"
        or sha256_file(original_contract_path)
        != contract["inputs"]["original_contract_sha256"]
        or original.get("experiment_id") != "E11a-successor"
    ):
        raise ValueError("E11a recovery contract differs")

    expected_cells = contract["valid_candidate_order"]
    cells = [load_object(path) for path in cell_paths]
    by_name = {cell.get("model", {}).get("candidate"): cell for cell in cells}
    if len(cells) != len(expected_cells) or set(by_name) != set(expected_cells):
        raise ValueError("E11a recovery valid cell set differs")
    for candidate, cell in by_name.items():
        if (
            cell.get("status") != VALID_CELL_STATUS
            or cell.get("contract_sha256")
            != contract["inputs"]["original_contract_sha256"]
            or cell.get("request_failures") != 0
            or cell.get("model")
            != next(
                model for model in original["models"] if model["candidate"] == candidate
            )
        ):
            raise ValueError(f"E11a recovery cell differs for {candidate}")
        require_true(
            cell,
            (
                "native_arm64",
                "exact_e10f_safe_sampled_adapter",
                "same_frozen_workload",
                "tokenizer_parity",
                "synthetic_preflight",
                "all_raw_responses_retained_once",
                "all_sampled_tokens_safe_and_exact",
                "zero_request_failures",
            ),
            candidate,
        )
    prepared = {cell.get("prepared_sha256") for cell in cells}
    if prepared != {contract["prepared_sha256"]}:
        raise ValueError("E11a recovery prepared workload differs")

    q8 = load_object(q8_failure_path)
    if (
        sha256_file(q8_failure_path) != contract["inputs"]["q8_failure_manifest_sha256"]
        or q8.get("status") != Q8_FAILURE_STATUS
        or q8.get("model", {}).get("candidate")
        != contract["resource_infeasible_candidate"]
        or q8.get("prepared_sha256") != contract["prepared_sha256"]
        or q8.get("scoring", {}).get("request_failures") != 0
        or q8.get("decision", {}).get("q8_0_deployable_frontier_eligible") is not False
        or q8.get("failure", {}).get("type") != "frozen_peak_rss_gate_exceeded"
    ):
        raise ValueError("E11a recovery Q8 resource failure differs")

    anchor = load_object(anchor_path)
    models = anchor.get("models")
    validation = anchor.get("validation", {})
    if (
        sha256_file(anchor_path) != contract["inputs"]["anchor_manifest_sha256"]
        or anchor.get("status") != "valid_safe_sampled_external_holdout"
        or anchor.get("prepared_sha256") != contract["prepared_sha256"]
        or not isinstance(models, list)
        or len(models) != 2
        or models[0].get("model", {}).get("candidate") != contract["anchor_candidate"]
        or models[1].get("model", {}).get("candidate")
        != contract["diagnostic_candidate"]
        or not all(
            validation.get(name) is True
            for name in (
                "native_arm64",
                "same_frozen_workload",
                "both_models_complete",
                "zero_request_failures",
                "per_sample_logs_retained",
                "all_raw_responses_retained_once",
            )
        )
    ):
        raise ValueError("E11a recovery retained anchor differs")

    anchor_point = {
        **models[0],
        "quality_coordinates": quality_coordinates(models[0]["metrics"]),
    }
    deployable = {**by_name, contract["anchor_candidate"]: anchor_point}
    if set(deployable) != set(contract["deployable_candidate_order"]):
        raise ValueError("E11a recovery deployable set differs")
    ordered = [
        deployable[candidate] for candidate in contract["deployable_candidate_order"]
    ]
    artifacts = validate_artifacts(contract, load_object(artifact_metadata_path))
    q8_artifact = next(
        item
        for item in artifacts
        if contract["resource_infeasible_candidate"] in item["name"]
    )
    if (
        str(q8_artifact["id"]) != q8["github"]["artifact_id"]
        or q8_artifact["digest"] != q8["github"]["artifact_digest"]
    ):
        raise ValueError("E11a recovery Q8 artifact differs")

    return {
        "schema_version": 1,
        "experiment_id": "E11a-successor-recovery",
        "status": "valid_stock_quant_ladder_with_resource_infeasible_q8",
        "contract_sha256": sha256_file(contract_path),
        "original_contract_sha256": sha256_file(original_contract_path),
        "prepared_sha256": contract["prepared_sha256"],
        "deployable_models": ordered,
        "resource_infeasible_models": [
            {
                "model": q8["model"],
                "quality_coordinates": q8["quality_coordinates"],
                "metrics": q8["scoring"]["metrics"],
                "readiness_ms": q8["readiness_ms"],
                "server_process": q8["server_process"],
                "failure": q8["failure"],
                "artifact": q8_artifact,
                "deployable_frontier_eligible": False,
            }
        ],
        "q4_0_diagnostic_control": models[1],
        "deployable_quality_size_frontier": pareto_frontier(ordered),
        "source_artifacts": artifacts,
        "accounting": {
            "new_candidates_attempted": 8,
            "valid_deployable_cells": 7,
            "resource_infeasible_cells_with_valid_scoring": 1,
            "retained_anchor_cells": 1,
            "diagnostic_controls": 1,
            "all_attempted_candidates_accounted_for": True,
        },
        "validation": {
            "native_arm64": True,
            "same_frozen_workload": True,
            "seven_deployable_candidates_complete": True,
            "q8_complete_scoring_retained_as_resource_infeasible": True,
            "q8_excluded_from_deployable_frontier": True,
            "exact_e10f_anchor_reused_without_rerun": True,
            "zero_scoring_request_failures": True,
            "per_sample_logs_retained_in_source_artifacts": True,
            "all_raw_responses_retained_once_in_source_artifacts": True,
            "minimum_quality_gate_used": False,
            "weighted_score_used": False,
            "post_observation_resource_gate_change": False,
        },
        "decision": contract["decision"],
        "claim_boundary": contract["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--original-contract", type=Path, required=True)
    parser.add_argument("--cell", type=Path, action="append", required=True)
    parser.add_argument("--anchor", type=Path, required=True)
    parser.add_argument("--q8-failure", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(
        contract_path=args.contract,
        original_contract_path=args.original_contract,
        cell_paths=args.cell,
        anchor_path=args.anchor,
        q8_failure_path=args.q8_failure,
        artifact_metadata_path=args.artifact_metadata,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
