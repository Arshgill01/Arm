#!/usr/bin/env python3
"""Validate E12b against the actual recovered E11a and E12a prerequisites."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import experiments.e12b_successor_ingest as successor
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e10d_ingest import validate_inputs as validate_adapter_inputs
    from experiments.e12b_ingest import frontier
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    import e12b_successor_ingest as successor
    from e5b_ingest import load_object, sha256_file
    from e10d_ingest import validate_inputs as validate_adapter_inputs
    from e12b_ingest import frontier


ARTIFACT_INPUTS = {
    "plan": "plan.json",
    "adapter_contract": "adapter/contract.json",
    "cell_runner": "cell-runner.sh",
    "base_freeze": "freeze.py",
    "base_ingest": "base-ingest.py",
    "base_test": "base-test.py",
    "successor_wrapper": "successor-wrapper.py",
    "successor_freeze": "successor-freeze.py",
    "successor_ingest": "successor-ingest.py",
    "successor_test": "successor-test.py",
    "actual_wrapper": "actual-wrapper.py",
    "actual_freeze": "actual-freeze.py",
    "actual_ingest": "actual-ingest.py",
    "actual_test": "actual-test.py",
    "safe_contract": "e10f-contract.json",
    "safe_probe": "e10f-probe.py",
    "safe_ingest": "e10f-ingest.py",
    "safe_manifest": "e10f-retained-manifest.json",
    "e12a_metadata_contract": "e12a-metadata-contract.json",
    "e12a_metadata_manifest": "e12a-metadata-manifest.json",
    "e12a_workflow_summary": "e12a/summary.json",
    "e12a_resume_contract": "e12a-resume-contract.json",
    "e11a_successor_contract": "e11a-successor-contract.json",
    "e11a_recovery_contract": "e11a-recovery-contract.json",
    "e11a_recovery_summary": "e11a-recovery-summary.json",
}


def validate_actual_inputs(
    evidence: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E12b"
        or contract.get("campaign_variant") != "actual-recovered-prerequisites"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E12b actual contract differs")
    for name, artifact_name in ARTIFACT_INPUTS.items():
        source = root / contract["inputs"][f"{name}_path"]
        expected = contract["inputs"][f"{name}_sha256"]
        if (
            sha256_file(source) != expected
            or sha256_file(evidence / artifact_name) != expected
        ):
            raise ValueError(f"E12b actual input differs for {name}")
    adapter = validate_adapter_inputs(
        evidence / "adapter",
        root / contract["inputs"]["adapter_contract_path"],
        root,
    )
    if adapter != load_object(evidence / "adapter/contract.json"):
        raise ValueError("E12b actual adapter differs")
    safe = load_object(evidence / "e10f-retained-manifest.json")
    prerequisite = contract["prerequisites"]["e10f"]
    if (
        safe.get("status") != prerequisite["required_status"]
        or safe.get("contract_sha256") != prerequisite["contract_sha256"]
        or safe.get("prepared_sha256") != prerequisite["prepared_sha256"]
        or sha256_file(evidence / "e10f-retained-manifest.json")
        != prerequisite["summary_sha256"]
        or load_object(evidence / "e10f-contract.json")["scoring"]
        != contract["scoring"]
        or load_object(evidence / "e10f-contract.json")["safe_sampling"]
        != contract["safe_sampling"]
    ):
        raise ValueError("E12b actual safe-scoring prerequisite differs")
    return contract


def validate_actual_e12a(evidence: Path, contract: dict[str, Any]) -> dict[str, Any]:
    prerequisite = contract["prerequisites"]["e12a"]
    summary_path = evidence / "e12a/summary.json"
    imatrix_path = evidence / "e12a/imatrix.gguf"
    summary = load_object(summary_path)
    validation = summary.get("validation", {})
    if (
        sha256_file(summary_path) != prerequisite["summary_sha256"]
        or summary.get("status") != prerequisite["required_status"]
        or summary.get("contract_sha256") != prerequisite["contract_sha256"]
        or summary.get("imatrix", {}).get("sha256")
        != prerequisite["imatrix_sha256"]
        or summary.get("imatrix", {}).get("size_bytes")
        != prerequisite["imatrix_size_bytes"]
        or sha256_file(imatrix_path) != prerequisite["imatrix_sha256"]
        or imatrix_path.stat().st_size != prerequisite["imatrix_size_bytes"]
        or not all(
            validation.get(name) is True
            for name in (
                "native_arm64",
                "exact_retained_statistics",
                "exact_source_artifact_inventory",
                "matrix_bytes_unchanged",
                "ordered_dataset_metadata",
                "complete_chunk_count",
                "entry_names_match_checkpoint",
                "gguf_metadata_valid",
                "generated_quant_dispatch_allowed",
            )
        )
        or any(
            validation.get(name) is not False
            for name in ("matrix_recomputed", "native_tool_rebuilt", "model_downloaded")
        )
    ):
        raise ValueError("E12b actual E12a prerequisite differs")
    return summary


def cell_summary(
    evidence: Path, contract_path: Path, root: Path, candidate_name: str
) -> dict[str, Any]:
    old_inputs = successor.validate_successor_inputs
    old_e12a = successor.validate_e12a_prerequisite
    successor.validate_successor_inputs = validate_actual_inputs
    successor.validate_e12a_prerequisite = validate_actual_e12a
    try:
        result = successor.cell_summary(
            evidence, contract_path, root, candidate_name
        )
    finally:
        successor.validate_successor_inputs = old_inputs
        successor.validate_e12a_prerequisite = old_e12a
    result["campaign_variant"] = "actual-recovered-prerequisites"
    result["validation"].pop("exact_resumed_e12a_imatrix", None)
    result["validation"]["exact_e12a_metadata_recovery_imatrix"] = True
    return result


def aggregate_summary(
    contract_path: Path, cell_paths: list[Path], stock_path: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    expected = [item["candidate"] for item in contract["candidates"]]
    cells = [load_object(path) for path in cell_paths]
    by_name = {cell.get("model", {}).get("candidate"): cell for cell in cells}
    if (
        len(cells) != len(expected)
        or set(by_name) != set(expected)
        or any(
            cell.get("status")
            != "valid_safe_sampled_generated_quant_quality_cell"
            or cell.get("campaign_variant") != "actual-recovered-prerequisites"
            or cell.get("contract_sha256") != sha256_file(contract_path)
            or cell.get("request_failures") != 0
            for cell in cells
        )
        or len({cell.get("prepared_sha256") for cell in cells}) != 1
    ):
        raise ValueError("E12b actual generated cell set differs")
    generated = [by_name[name] for name in expected]

    stock = load_object(stock_path)
    prerequisite = contract["prerequisites"]["e11a"]
    stock_models = stock.get("deployable_models")
    validation = stock.get("validation", {})
    if (
        sha256_file(stock_path) != prerequisite["summary_sha256"]
        or stock.get("status") != prerequisite["required_status"]
        or stock.get("contract_sha256") != prerequisite["contract_sha256"]
        or stock.get("prepared_sha256") != generated[0]["prepared_sha256"]
        or not isinstance(stock_models, list)
        or len(stock_models) != prerequisite["deployable_models"]
        or len(stock.get("resource_infeasible_models", []))
        != prerequisite["resource_infeasible_models"]
        or not all(
            validation.get(name) is True
            for name in (
                "native_arm64",
                "same_frozen_workload",
                "all_valid_source_cells_complete",
                "two_complete_scoring_resource_failures_retained",
                "resource_failures_excluded_from_deployable_frontier",
                "exact_e10f_anchor_reused_without_rerun",
                "zero_scoring_request_failures",
                "per_sample_logs_retained_in_source_artifacts",
            )
        )
    ):
        raise ValueError("E12b actual stock prerequisite differs")

    combined = [*stock_models, *generated]
    if len({item["model"]["candidate"] for item in combined}) != len(combined):
        raise ValueError("E12b actual combined frontier names are not unique")
    paired = []
    for control_name, imatrix_name in contract["matched_pairs"]:
        control = by_name[control_name]
        imatrix = by_name[imatrix_name]
        paired.append(
            {
                "control": control_name,
                "imatrix": imatrix_name,
                "size_bytes_delta": (
                    imatrix["model"]["size_bytes"] - control["model"]["size_bytes"]
                ),
                "quality_coordinate_deltas": {
                    key: (
                        imatrix["quality_coordinates"][key]
                        - control["quality_coordinates"][key]
                    )
                    for key in control["quality_coordinates"]
                },
            }
        )
    return {
        "schema_version": 1,
        "experiment_id": "E12b",
        "campaign_variant": "actual-recovered-prerequisites",
        "status": "valid_safe_sampled_matched_mixed_quant_quality_frontier",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": generated[0]["prepared_sha256"],
        "generated_models": generated,
        "stock_deployable_models": stock_models,
        "stock_resource_infeasible_models": stock["resource_infeasible_models"],
        "matched_imatrix_deltas": paired,
        "quality_size_frontier": frontier(combined),
        "validation": {
            "native_arm64": True,
            "all_generated_candidates_complete": True,
            "exact_actual_e11a_stock_accounting": True,
            "resource_infeasible_stock_points_excluded": True,
            "same_frozen_workload": True,
            "matched_controls_complete": True,
            "zero_request_failures": True,
            "per_sample_logs_retained": True,
            "all_raw_responses_retained_once": True,
            "weighted_score_used": False,
            "minimum_quality_gate_used": False,
        },
        "decision": contract["decision"],
        "claim_boundary": contract["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    cell = subparsers.add_parser("cell")
    cell.add_argument("--evidence-dir", type=Path, required=True)
    cell.add_argument("--contract", type=Path, required=True)
    cell.add_argument("--root", type=Path, required=True)
    cell.add_argument("--candidate", required=True)
    cell.add_argument("--output", type=Path, required=True)
    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--contract", type=Path, required=True)
    aggregate.add_argument("--cell", type=Path, action="append", required=True)
    aggregate.add_argument("--stock", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "cell":
        result = cell_summary(
            args.evidence_dir, args.contract, args.root, args.candidate
        )
    else:
        result = aggregate_summary(args.contract, args.cell, args.stock)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
