#!/usr/bin/env python3
"""Freeze the fail-closed E11a aggregate recovery before seven cells finish."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


INPUT_PATHS = {
    "original_contract": Path("experiments/e11a_successor_contract.json"),
    "q8_failure_manifest": Path(
        "results/manifests/e11a-successor-q8-resource-failure-30847559089.json"
    ),
    "anchor_manifest": Path("results/manifests/e10f-30829237582.json"),
    "ingest": Path("experiments/e11a_recovery_ingest.py"),
    "freeze": Path("experiments/e11a_recovery_freeze.py"),
    "test": Path("tests/test_e11a_recovery.py"),
}


def build_contract(root: Path) -> dict[str, object]:
    original = load_object(root / INPUT_PATHS["original_contract"])
    q8 = load_object(root / INPUT_PATHS["q8_failure_manifest"])
    anchor = load_object(root / INPUT_PATHS["anchor_manifest"])
    attempted = [model["candidate"] for model in original["models"]]
    resource_infeasible = "ministral3_3b_q8_0"
    valid = [candidate for candidate in attempted if candidate != resource_infeasible]
    deployable = [
        candidate
        for candidate in original["full_candidate_order"]
        if candidate != resource_infeasible
    ]
    if (
        original.get("experiment_id") != "E11a-successor"
        or len(attempted) != 8
        or attempted[-1] != resource_infeasible
        or q8.get("status")
        != "invalid_stock_quant_resource_gate_failure_with_valid_scoring"
        or q8.get("decision", {}).get(
            "aggregate_successor_may_classify_resource_infeasible_point"
        )
        is not True
        or anchor.get("status") != "valid_safe_sampled_external_holdout"
        or q8.get("prepared_sha256") != anchor.get("prepared_sha256")
    ):
        raise ValueError("E11a recovery prerequisites differ")
    inputs: dict[str, str] = {}
    for name, path in INPUT_PATHS.items():
        inputs[f"{name}_path"] = path.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / path)
    return {
        "schema_version": 1,
        "experiment_id": "E11a-successor-recovery",
        "title": "Fail-closed stock-quant aggregation with resource-infeasible Q8",
        "state": (
            "frozen after Q8_0 completed scoring and failed the original RSS gate, "
            "while all seven other source-run cells were still scoring and before "
            "any of their model outcomes were observed"
        ),
        "inputs": inputs,
        "source_run": {
            "run_id": "30847559089",
            "run_attempt": 1,
            "repository_commit": "f3321bde74570de141266b111af364e7ea3722af",
            "workflow": "Arm E11a safe-sampled stock quant frontier",
            "runner": "ubuntu-24.04-arm",
            "expected_overall_conclusion": "failure because Q8_0 failed a frozen resource gate",
        },
        "prepared_sha256": q8["prepared_sha256"],
        "attempted_candidates": attempted,
        "valid_candidate_order": valid,
        "deployable_candidate_order": deployable,
        "resource_infeasible_candidate": resource_infeasible,
        "anchor_candidate": "ministral3_3b_q4_k_m",
        "diagnostic_candidate": "ministral3_3b_q4_0",
        "acceptance": {
            "exactly_seven_valid_source_cell_summaries": True,
            "all_source_artifacts_exact_run_attempt_and_commit": True,
            "all_source_artifacts_unexpired_with_sha256_digest": True,
            "all_cell_gates_unchanged_from_original_contract": True,
            "q8_failure_manifest_exact_hash": True,
            "q8_scoring_request_failures": 0,
            "q8_deployable_frontier_eligible": False,
            "all_eight_new_candidates_accounted_for": True,
        },
        "frontier": {
            **original["frontier"],
            "scope": "Seven valid new cells plus the retained Q4_K_M anchor only",
            "resource_infeasible_policy": (
                "Report Q8_0's completed quality coordinates and original RSS failure "
                "separately; never include it in the deployable Pareto computation."
            ),
        },
        "decision": {
            "raise_original_rss_gate": False,
            "rerun_q8_scoring": False,
            "silently_drop_q8": False,
            "promote_model_from_quality_only": False,
            "advance_every_deployable_non_dominated_point_to_matched_service": True,
            "sealed_confirmation_required_before_promotion": True,
        },
        "negative_result_rule": (
            "If any remaining cell is absent, invalid, resource-infeasible, or fails "
            "independent validation, this recovery fails closed and a new separately "
            "frozen accounting decision is required; do not edit this contract."
        ),
        "claim_boundary": (
            "This recovery can establish an exploratory quality-size frontier only "
            "for the seven valid stock candidates and retained Q4_K_M anchor. Q8_0 is "
            "shown only as a resource-infeasible completed-scoring point. It cannot "
            "promote a model or support service-performance, energy, PMU, device, "
            "fleet, cost, generated-quant, pruning, causal-kernel, or runtime claims."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
