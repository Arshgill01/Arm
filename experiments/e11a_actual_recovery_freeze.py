#!/usr/bin/env python3
"""Freeze terminal E11a accounting with Q6 and Q8 resource failures."""

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


INPUT_PATHS = {
    "original_contract": Path("experiments/e11a_successor_contract.json"),
    "source_run": Path("results/manifests/e11a-source-run-30847559089.json"),
    "q6_failure_manifest": Path(
        "results/manifests/e11a-successor-q6-resource-failure-30847559089.json"
    ),
    "q8_failure_manifest": Path(
        "results/manifests/e11a-successor-q8-resource-failure-30847559089.json"
    ),
    "anchor_manifest": Path("results/manifests/e10f-30829237582.json"),
    "ingest": Path("experiments/e11a_actual_recovery_ingest.py"),
    "freeze": Path("experiments/e11a_actual_recovery_freeze.py"),
    "test": Path("tests/test_e11a_actual_recovery.py"),
}


def job_for_candidate(source_run: dict[str, Any], candidate: str) -> dict[str, Any]:
    matches = [
        job
        for job in source_run.get("jobs", [])
        if job.get("name", "").startswith(f"{candidate} ")
    ]
    if len(matches) != 1:
        raise ValueError(f"E11a source run job differs for {candidate}")
    return matches[0]


def build_contract(root: Path) -> dict[str, Any]:
    original = load_object(root / INPUT_PATHS["original_contract"])
    source_run = load_object(root / INPUT_PATHS["source_run"])
    q6 = load_object(root / INPUT_PATHS["q6_failure_manifest"])
    q8 = load_object(root / INPUT_PATHS["q8_failure_manifest"])
    anchor = load_object(root / INPUT_PATHS["anchor_manifest"])
    attempted = [model["candidate"] for model in original["models"]]
    resource = ["ministral3_3b_q6_k", "ministral3_3b_q8_0"]
    valid = [candidate for candidate in attempted if candidate not in resource]
    deployable = [
        candidate
        for candidate in original["full_candidate_order"]
        if candidate not in resource
    ]
    jobs = {candidate: job_for_candidate(source_run, candidate) for candidate in attempted}
    if (
        original.get("experiment_id") != "E11a-successor"
        or source_run.get("databaseId") != 30847559089
        or source_run.get("status") != "completed"
        or source_run.get("conclusion") != "failure"
        or source_run.get("headSha") != "f3321bde74570de141266b111af364e7ea3722af"
        or any(jobs[candidate].get("conclusion") != "success" for candidate in valid)
        or any(jobs[candidate].get("conclusion") != "failure" for candidate in resource)
        or any(jobs[candidate].get("status") != "completed" for candidate in attempted)
        or q6.get("status")
        != "invalid_stock_quant_resource_gate_failure_with_valid_scoring"
        or q8.get("status")
        != "invalid_stock_quant_resource_gate_failure_with_valid_scoring"
        or q6.get("model", {}).get("candidate") != resource[0]
        or q8.get("model", {}).get("candidate") != resource[1]
        or q6.get("prepared_sha256") != q8.get("prepared_sha256")
        or anchor.get("status") != "valid_safe_sampled_external_holdout"
        or anchor.get("prepared_sha256") != q6.get("prepared_sha256")
    ):
        raise ValueError("E11a actual recovery prerequisites differ")
    inputs: dict[str, str] = {}
    for name, path in INPUT_PATHS.items():
        inputs[f"{name}_path"] = path.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / path)
    return {
        "schema_version": 1,
        "experiment_id": "E11a-successor-actual-recovery",
        "title": "Terminal stock-quant accounting with Q6 and Q8 resource failures",
        "state": (
            "frozen after all eight source jobs reached terminal state and Q6_K and "
            "Q8_0 were independently retained as complete-scoring RSS failures"
        ),
        "inputs": inputs,
        "source_run": {
            "run_id": "30847559089",
            "run_attempt": 1,
            "repository_commit": source_run["headSha"],
            "workflow": "Arm E11a safe-sampled stock quant frontier",
            "runner": "ubuntu-24.04-arm",
            "conclusion": source_run["conclusion"],
            "terminal_metadata_sha256": sha256_file(root / INPUT_PATHS["source_run"]),
        },
        "prepared_sha256": q6["prepared_sha256"],
        "attempted_candidates": attempted,
        "valid_candidate_order": valid,
        "deployable_candidate_order": deployable,
        "resource_infeasible_candidate_order": resource,
        "resource_failure_inputs": {
            resource[0]: "q6_failure_manifest",
            resource[1]: "q8_failure_manifest",
        },
        "anchor_candidate": "ministral3_3b_q4_k_m",
        "diagnostic_candidate": "ministral3_3b_q4_0",
        "acceptance": {
            "exactly_six_valid_source_cell_summaries": True,
            "exactly_two_complete_scoring_resource_failures": True,
            "all_source_artifacts_exact_run_attempt_and_commit": True,
            "all_source_artifacts_unexpired_with_sha256_digest": True,
            "all_cell_gates_unchanged_from_original_contract": True,
            "all_eight_new_candidates_accounted_for": True,
            "resource_failure_request_failures": 0,
            "resource_failures_deployable_frontier_eligible": False,
        },
        "frontier": {
            **original["frontier"],
            "scope": "Six valid new cells plus the retained Q4_K_M anchor",
            "resource_infeasible_policy": (
                "Report Q6_K and Q8_0 quality coordinates and original RSS failures "
                "separately; never include them in deployable Pareto computation."
            ),
        },
        "decision": {
            "raise_original_rss_gate": False,
            "rerun_resource_failure_scoring": False,
            "silently_drop_resource_failures": False,
            "promote_model_from_quality_only": False,
            "advance_every_deployable_non_dominated_point_to_matched_service": True,
            "sealed_confirmation_required_before_promotion": True,
        },
        "negative_result_rule": (
            "If any terminal cell or artifact is absent, invalid, or has a status other "
            "than the exact six successes and two retained resource failures, fail "
            "closed without changing the source contract or RSS gate."
        ),
        "claim_boundary": (
            "This recovery can establish an exploratory quality-size frontier only "
            "for six valid stock candidates and the retained Q4_K_M anchor. Q6_K and "
            "Q8_0 remain scored but nondeployable. It cannot promote a model or support "
            "service-performance, energy, PMU, device, fleet, cost, generated-quant, "
            "pruning, causal-kernel, or runtime claims."
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
