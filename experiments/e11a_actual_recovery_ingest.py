#!/usr/bin/env python3
"""Aggregate the terminal E11a stock ladder with explicit resource failures."""

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


VALID_STATUS = "valid_safe_sampled_stock_quant_cell"
RESOURCE_STATUS = "invalid_stock_quant_resource_gate_failure_with_valid_scoring"
REQUIRED_VALIDATIONS = (
    "native_arm64",
    "exact_e10f_safe_sampled_adapter",
    "same_frozen_workload",
    "tokenizer_parity",
    "synthetic_preflight",
    "all_raw_responses_retained_once",
    "all_sampled_tokens_safe_and_exact",
    "zero_request_failures",
)


def validate_artifacts(
    contract: dict[str, Any], metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    expected = {
        f"e11a-successor-{candidate}-{contract['source_run']['run_id']}-1"
        for candidate in contract["attempted_candidates"]
    }
    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, list):
        raise TypeError("E11a actual recovery artifact metadata differs")
    selected = [artifact for artifact in artifacts if artifact.get("name") in expected]
    if len(selected) != len(expected) or {item["name"] for item in selected} != expected:
        raise ValueError("E11a actual recovery artifact set differs")
    for artifact in selected:
        workflow_run = artifact.get("workflow_run", {})
        if (
            artifact.get("expired") is not False
            or not isinstance(artifact.get("id"), int)
            or not isinstance(artifact.get("size_in_bytes"), int)
            or artifact["size_in_bytes"] <= 0
            or re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest", ""))
            is None
            or str(workflow_run.get("id")) != contract["source_run"]["run_id"]
            or workflow_run.get("head_sha")
            != contract["source_run"]["repository_commit"]
        ):
            raise ValueError("E11a actual recovery artifact identity differs")
    return sorted(selected, key=lambda artifact: artifact["name"])


def validate_cell(
    cell: dict[str, Any], candidate: str, original: dict[str, Any], contract: dict[str, Any]
) -> None:
    validation = cell.get("validation", {})
    model = next(
        item for item in original["models"] if item["candidate"] == candidate
    )
    if (
        cell.get("status") != VALID_STATUS
        or cell.get("contract_sha256")
        != contract["inputs"]["original_contract_sha256"]
        or cell.get("prepared_sha256") != contract["prepared_sha256"]
        or cell.get("request_failures") != 0
        or cell.get("model") != model
        or not all(validation.get(name) is True for name in REQUIRED_VALIDATIONS)
    ):
        raise ValueError(f"E11a actual recovery cell differs for {candidate}")


def validate_resource_failure(
    failure: dict[str, Any], candidate: str, contract: dict[str, Any]
) -> None:
    decision = failure.get("decision", {})
    if (
        failure.get("status") != RESOURCE_STATUS
        or failure.get("model", {}).get("candidate") != candidate
        or failure.get("prepared_sha256") != contract["prepared_sha256"]
        or failure.get("scoring", {}).get("request_failures") != 0
        or failure.get("failure", {}).get("type")
        != "frozen_peak_rss_gate_exceeded"
        or failure.get("failure", {}).get("scoring_completed_before_rejection")
        is not True
        or decision.get("valid_scoring_may_be_retained_as_infeasible_point")
        is not True
        or decision.get("aggregate_successor_may_classify_resource_infeasible_point")
        is not True
    ):
        raise ValueError(f"E11a actual recovery resource failure differs for {candidate}")


def aggregate(
    *,
    contract_path: Path,
    original_contract_path: Path,
    cell_paths: list[Path],
    anchor_path: Path,
    failure_paths: list[Path],
    artifact_metadata_path: Path,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    original = load_object(original_contract_path)
    if (
        contract.get("experiment_id") != "E11a-successor-actual-recovery"
        or sha256_file(original_contract_path)
        != contract["inputs"]["original_contract_sha256"]
        or original.get("experiment_id") != "E11a-successor"
    ):
        raise ValueError("E11a actual recovery contract differs")
    cells = [load_object(path) for path in cell_paths]
    by_candidate = {cell.get("model", {}).get("candidate"): cell for cell in cells}
    valid_candidates = contract["valid_candidate_order"]
    if len(cells) != len(valid_candidates) or set(by_candidate) != set(valid_candidates):
        raise ValueError("E11a actual recovery valid cell set differs")
    for candidate, cell in by_candidate.items():
        validate_cell(cell, candidate, original, contract)

    failures = [load_object(path) for path in failure_paths]
    failures_by_candidate = {
        failure.get("model", {}).get("candidate"): failure for failure in failures
    }
    resource_candidates = contract["resource_infeasible_candidate_order"]
    if len(failures) != len(resource_candidates) or set(failures_by_candidate) != set(
        resource_candidates
    ):
        raise ValueError("E11a actual recovery failure set differs")
    failure_input_names = contract["resource_failure_inputs"]
    for candidate, failure in failures_by_candidate.items():
        path = failure_paths[
            next(
                index
                for index, item in enumerate(failures)
                if item.get("model", {}).get("candidate") == candidate
            )
        ]
        input_name = failure_input_names[candidate]
        if sha256_file(path) != contract["inputs"][f"{input_name}_sha256"]:
            raise ValueError(f"E11a failure manifest hash differs for {candidate}")
        validate_resource_failure(failure, candidate, contract)

    anchor = load_object(anchor_path)
    anchor_models = anchor.get("models")
    validation = anchor.get("validation", {})
    if (
        sha256_file(anchor_path) != contract["inputs"]["anchor_manifest_sha256"]
        or anchor.get("status") != "valid_safe_sampled_external_holdout"
        or anchor.get("prepared_sha256") != contract["prepared_sha256"]
        or not isinstance(anchor_models, list)
        or len(anchor_models) != 2
        or anchor_models[0].get("model", {}).get("candidate")
        != contract["anchor_candidate"]
        or anchor_models[1].get("model", {}).get("candidate")
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
        raise ValueError("E11a actual recovery anchor differs")

    anchor_point = {
        **anchor_models[0],
        "quality_coordinates": quality_coordinates(anchor_models[0]["metrics"]),
    }
    deployable = {**by_candidate, contract["anchor_candidate"]: anchor_point}
    ordered = [deployable[name] for name in contract["deployable_candidate_order"]]
    artifacts = validate_artifacts(contract, load_object(artifact_metadata_path))
    resource_points = []
    for candidate in resource_candidates:
        failure = failures_by_candidate[candidate]
        artifact = next(item for item in artifacts if candidate in item["name"])
        if (
            str(artifact["id"]) != failure["github"]["artifact_id"]
            or artifact["digest"] != failure["github"]["artifact_digest"]
        ):
            raise ValueError(f"E11a resource artifact differs for {candidate}")
        resource_points.append(
            {
                "model": failure["model"],
                "quality_coordinates": failure["quality_coordinates"],
                "metrics": failure["scoring"]["metrics"],
                "readiness_ms": failure["readiness_ms"],
                "server_process": failure["server_process"],
                "failure": failure["failure"],
                "artifact": artifact,
                "deployable_frontier_eligible": False,
            }
        )
    return {
        "schema_version": 1,
        "experiment_id": "E11a-successor-actual-recovery",
        "status": "valid_stock_quant_ladder_with_two_resource_infeasible_points",
        "contract_sha256": sha256_file(contract_path),
        "original_contract_sha256": sha256_file(original_contract_path),
        "prepared_sha256": contract["prepared_sha256"],
        "deployable_models": ordered,
        "resource_infeasible_models": resource_points,
        "q4_0_diagnostic_control": anchor_models[1],
        "deployable_quality_size_frontier": pareto_frontier(ordered),
        "source_artifacts": artifacts,
        "accounting": {
            "new_candidates_attempted": len(contract["attempted_candidates"]),
            "valid_deployable_cells": len(valid_candidates),
            "resource_infeasible_cells_with_valid_scoring": len(resource_candidates),
            "retained_anchor_cells": 1,
            "diagnostic_controls": 1,
            "all_attempted_candidates_accounted_for": True,
        },
        "validation": {
            "native_arm64": True,
            "same_frozen_workload": True,
            "all_valid_source_cells_complete": True,
            "two_complete_scoring_resource_failures_retained": True,
            "resource_failures_excluded_from_deployable_frontier": True,
            "exact_e10f_anchor_reused_without_rerun": True,
            "zero_scoring_request_failures": True,
            "per_sample_logs_retained_in_source_artifacts": True,
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
    parser.add_argument("--failure", type=Path, action="append", required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(
        contract_path=args.contract,
        original_contract_path=args.original_contract,
        cell_paths=args.cell,
        anchor_path=args.anchor,
        failure_paths=args.failure,
        artifact_metadata_path=args.artifact_metadata,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
