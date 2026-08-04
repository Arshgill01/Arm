#!/usr/bin/env python3
"""Freeze the matched stock-quant service frontier from terminal E11a evidence."""

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


STATIC_INPUTS = {
    "plan": Path("experiments/e11b_plan.json"),
    "probe": Path("experiments/e11b_probe.py"),
    "cell": Path("experiments/e11b_cell.sh"),
    "test": Path("tests/test_e11b.py"),
    "freeze_test": Path("tests/test_e11b_freeze.py"),
    "e9a_contract": Path("experiments/e9a_contract.json"),
    "e9a_ingest": Path("experiments/e9a_ingest.py"),
    "ingest": Path("experiments/e11b_ingest.py"),
    "tasks": Path("experiments/e3_tasks.json"),
    "reference_manifest": Path("results/manifests/e3f-30656151957.json"),
    "models": Path("experiments/e3f_models.json"),
    "stock_contract": Path("experiments/e11a_successor_contract.json"),
    "freeze": Path("experiments/e11b_freeze.py"),
}


def require_true(value: dict[str, Any], names: tuple[str, ...], label: str) -> None:
    validation = value.get("validation")
    if not isinstance(validation, dict) or not all(
        validation.get(name) is True for name in names
    ):
        raise ValueError(f"{label} required validation differs")


def deployable_by_name(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    models = summary.get("deployable_models")
    if not isinstance(models, list):
        raise TypeError("E11a deployable model set differs")
    by_name = {item.get("model", {}).get("candidate"): item for item in models}
    if len(by_name) != len(models) or None in by_name:
        raise ValueError("E11a deployable model names differ")
    return by_name


def build_contract(
    root: Path,
    *,
    e11a_contract_path: Path,
    e11a_summary_path: Path,
    e11a_run_id: str,
    e11a_artifact: str,
) -> dict[str, Any]:
    plan = load_object(root / STATIC_INPUTS["plan"])
    e9a = load_object(root / STATIC_INPUTS["e9a_contract"])
    stock = load_object(root / STATIC_INPUTS["stock_contract"])
    recovery_contract = load_object(e11a_contract_path)
    summary = load_object(e11a_summary_path)
    if (
        plan.get("experiment_id") != "E11b-plan"
        or e9a.get("experiment_id") != "E9a"
        or stock.get("experiment_id") != "E11a-successor"
        or recovery_contract.get("experiment_id")
        != "E11a-successor-actual-recovery"
        or summary.get("status")
        != "valid_stock_quant_ladder_with_two_resource_infeasible_points"
        or summary.get("contract_sha256") != sha256_file(e11a_contract_path)
        or summary.get("prepared_sha256") != recovery_contract.get("prepared_sha256")
        or not e11a_run_id.isdigit()
        or not e11a_artifact
    ):
        raise ValueError("E11b prerequisite identity differs")
    require_true(
        summary,
        (
            "native_arm64",
            "same_frozen_workload",
            "all_valid_source_cells_complete",
            "two_complete_scoring_resource_failures_retained",
            "resource_failures_excluded_from_deployable_frontier",
            "exact_e10f_anchor_reused_without_rerun",
            "zero_scoring_request_failures",
            "per_sample_logs_retained_in_source_artifacts",
        ),
        "E11a actual recovery",
    )
    accounting = summary.get("accounting", {})
    if (
        accounting.get("new_candidates_attempted") != 8
        or accounting.get("valid_deployable_cells") != 6
        or accounting.get("resource_infeasible_cells_with_valid_scoring") != 2
        or accounting.get("all_attempted_candidates_accounted_for") is not True
    ):
        raise ValueError("E11b prerequisite accounting differs")

    anchor = plan["comparison"]["anchor"]
    by_name = deployable_by_name(summary)
    frontier = summary.get("deployable_quality_size_frontier")
    if (
        not isinstance(frontier, list)
        or anchor not in by_name
        or any(name not in by_name for name in frontier)
        or len(frontier) != len(set(frontier))
    ):
        raise ValueError("E11b prerequisite frontier differs")
    candidates = [name for name in frontier if name != anchor]
    if not candidates:
        raise ValueError("E11b empty shortlist must be retained without a service run")

    stock_models = {item["candidate"]: item for item in stock["models"]}
    e3f_models = load_object(root / STATIC_INPUTS["models"])["variants"]
    model_sources: dict[str, Any] = {}
    for name in [anchor, *candidates]:
        if name == anchor:
            variant = e3f_models[name]
            file = variant["files"][0]
            source = {
                "candidate": name,
                "repository": variant["repository"],
                "revision": variant["revision"],
                "path": file["path"],
                "sha256": file["sha256"],
                "size_bytes": file["size_bytes"],
            }
        else:
            source = stock_models.get(name)
            if not isinstance(source, dict):
                raise ValueError(f"E11b stock source differs for {name}")
            source = {
                **stock["model_repository"],
                **source,
            }
        observed = by_name[name]["model"]
        if any(
            source.get(field) != observed.get(field)
            for field in ("candidate", "sha256", "size_bytes")
        ):
            raise ValueError(f"E11b model identity differs for {name}")
        if "path" in observed and source.get("path") != observed.get("path"):
            raise ValueError(f"E11b model path differs for {name}")
        model_sources[name] = {
            **source,
            "quality_coordinates": by_name[name]["quality_coordinates"],
        }

    inputs: dict[str, str] = {}
    for name, relative in STATIC_INPUTS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    for name, path in (
        ("e11a_recovery_contract", e11a_contract_path),
        ("e11a_recovery_summary", e11a_summary_path),
    ):
        try:
            relative = path.relative_to(root)
        except ValueError as error:
            raise ValueError(f"E11b {name} must be retained under the repository") from error
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(path)

    profile = e9a["profiles"]["e7c_final"]
    return {
        "schema_version": 1,
        "experiment_id": "E11b",
        "title": "Matched native Arm stock-quant service frontier",
        "state": (
            "frozen from the mechanically selected terminal E11a deployable "
            "quality-size frontier before any shortlisted service result was observed"
        ),
        "inputs": inputs,
        "prerequisite": {
            "run_id": e11a_run_id,
            "run_attempt": 1,
            "artifact": e11a_artifact,
            "contract_sha256": summary["contract_sha256"],
            "summary_sha256": sha256_file(e11a_summary_path),
            "required_status": summary["status"],
            "quality_size_frontier": frontier,
            "resource_infeasible_candidates": recovery_contract[
                "resource_infeasible_candidate_order"
            ],
        },
        "anchor": anchor,
        "candidate_order": candidates,
        "models": model_sources,
        "runtime": {
            "source": profile["source"],
            "build": profile["build"],
            "service": profile["service"],
            "profile_name": "e7c_final",
        },
        "request": e9a["request"],
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "same_job_for_all_pairs": True,
            "fresh_process_per_cell": True,
            "pair_order": plan["comparison"]["pair_order"],
            "repetitions_per_model": plan["comparison"]["repetitions_per_model"],
            "total_pairs": len(candidates),
            "total_fresh_processes": len(candidates)
            * len(plan["comparison"]["pair_order"]),
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "http_status": 200,
            "termination_reason": "stop",
            "request_failures": 0,
            "minimum_cached_tokens_per_request": 1,
            "maximum_ready_ms": 15000.0,
            "maximum_process_rss_kib": 15728640,
            "maximum_throughput_coefficient_of_variation": 0.05,
            "accepted_server_shell_exit_statuses": [0, 130],
            "forbidden_dynamic_dependency_basenames": [
                "libcrypto.so.3",
                "libssl.so.3",
            ],
            "predictions_stable_across_repetitions": True,
        },
        "quality_policy": plan["quality_policy"],
        "frontier_policy": plan["frontier_policy"],
        "sealed_confirmation": plan["sealed_confirmation"],
        "decision": {
            "mechanical_shortlist_only": True,
            "no_post_result_candidate_cap": True,
            "service_result_can_promote_product": False,
            "sealed_e11c_confirmation_required": True,
        },
        "negative_result_rule": plan["negative_result_rule"],
        "claim_boundary": plan["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--e11a-contract", type=Path, required=True)
    parser.add_argument("--e11a-summary", type=Path, required=True)
    parser.add_argument("--e11a-run-id", required=True)
    parser.add_argument("--e11a-artifact", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    contract = build_contract(
        root,
        e11a_contract_path=(root / args.e11a_contract).resolve(),
        e11a_summary_path=(root / args.e11a_summary).resolve(),
        e11a_run_id=args.e11a_run_id,
        e11a_artifact=args.e11a_artifact,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
