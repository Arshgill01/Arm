#!/usr/bin/env python3
"""Freeze the stock-quant ladder on E10f's validated safe-sampled scorer."""

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
    "base_plan": Path("experiments/e11a_plan.json"),
    "models": Path("experiments/e11a_models.json"),
    "e10f_contract": Path("experiments/e10f_contract.json"),
    "e10f_manifest": Path("results/manifests/e10f-30829237582.json"),
    "cell_runner": Path("experiments/e10f_cell.sh"),
    "freeze": Path("experiments/e11a_successor_freeze.py"),
    "ingest": Path("experiments/e11a_successor_ingest.py"),
    "test": Path("tests/test_e11a_successor.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    base = load_object(root / INPUT_PATHS["base_plan"])
    universe = load_object(root / INPUT_PATHS["models"])
    e10f_contract = load_object(root / INPUT_PATHS["e10f_contract"])
    e10f = load_object(root / INPUT_PATHS["e10f_manifest"])
    validation = e10f.get("validation", {})
    if (
        base.get("experiment_id") != "E11a"
        or universe.get("experiment_id") != "E11a"
        or e10f.get("status") != "valid_safe_sampled_external_holdout"
        or e10f.get("contract_sha256") != sha256_file(root / INPUT_PATHS["e10f_contract"])
        or e10f.get("decision", {}).get("e10f_generated_quant_prerequisite_satisfied") is not True
        or not all(
            validation.get(key) is True
            for key in (
                "native_arm64",
                "same_frozen_workload",
                "both_models_complete",
                "zero_request_failures",
                "per_sample_logs_retained",
                "all_raw_responses_retained_once",
            )
        )
    ):
        raise ValueError("E11a safe-sampled prerequisite differs")

    by_name = {item["candidate"]: item for item in universe["variants"]}
    full_order = base["candidate_order"]
    if set(by_name) != set(full_order):
        raise ValueError("E11a stock candidate universe differs")
    anchor = e10f["models"][0]["model"]
    control = e10f["models"][1]["model"]
    if anchor["candidate"] != "ministral3_3b_q4_k_m" or control["candidate"] != "ministral3_3b_q4_0":
        raise ValueError("E11a safe-sampled anchor ordering differs")
    candidates = [
        {**by_name[name], "role": "new stock ladder candidate"}
        for name in full_order
        if name != anchor["candidate"]
    ]

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    return {
        "schema_version": 1,
        "experiment_id": "E11a-successor",
        "title": "Safe-sampled Arm stock-quant quality/size frontier",
        "state": (
            "frozen after E10f independently validated and before any of the eight "
            "previously unobserved stock-candidate outcomes are measured"
        ),
        "scope": (
            "Run all eight non-anchor stock formats from the original E11a universe "
            "through the unchanged E10f native safe-sampled holdout, then combine "
            "them with the exact retained Q4_K_M anchor."
        ),
        "hypothesis": base["hypothesis"],
        "inputs": inputs,
        "prerequisite": {
            "experiment": "E10f",
            "run_id": e10f["github"]["run_id"],
            "run_attempt": e10f["github"]["run_attempt"],
            "repository_commit": e10f["github"]["repository_commit"],
            "contract_sha256": e10f["contract_sha256"],
            "retained_manifest_sha256": sha256_file(root / INPUT_PATHS["e10f_manifest"]),
            "workflow_summary_sha256": e10f["artifact_validation"]["aggregate"]["workflow_summary_sha256"],
            "aggregate_artifact": e10f["github"]["artifacts"]["aggregate"],
            "prepared_sha256": e10f["prepared_sha256"],
            "required_status": e10f["status"],
            "anchor": anchor,
            "diagnostic_control": control,
        },
        "model_repository": {
            "repository": universe["repository"],
            "revision": universe["revision"],
            "license": universe["license"],
            "provenance": universe["provenance"],
        },
        "models": candidates,
        "full_candidate_order": full_order,
        "external_holdout": e10f_contract["external_holdout"],
        "scoring": e10f_contract["scoring"],
        "safe_sampling": e10f_contract["safe_sampling"],
        "service": e10f_contract["service"],
        "workload": e10f_contract["workload"],
        "runtime_prerequisites": e10f_contract["prerequisites"],
        "acceptance": e10f_contract["acceptance"],
        "frontier": {
            "coordinates": [
                "e9b_arc_easy.acc_norm",
                "e9b_hellaswag.acc_norm",
                "e9b_winogrande.acc",
                "model_size_bytes",
            ],
            "weighted_score": False,
            "dominance": base["exploratory_frontier_rule"]["dominance"],
            "shortlist": base["exploratory_frontier_rule"]["shortlist"],
            "candidate_outcomes_observed_before_freeze": False,
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "cell_timeout_minutes": 360,
            "aggregate_timeout_minutes": 30,
            "fresh_server_per_model": True,
            "matrix_models_run_in_separate_native_jobs": True,
            "all_eight_new_candidates_required": True,
            "exact_prepared_workload_reused": True,
            "exact_e10f_binary_closure_reused": True,
            "raw_http_responses": True,
            "per_sample_logs": True,
        },
        "decision": {
            "quality_result_can_promote_product": False,
            "matched_native_service_required": True,
            "sealed_confirmation_required": True,
            "original_30_task_admission_contract_rewrite_allowed": False,
            "original_e10d_rewrite_allowed": False,
            "negative_result_rule": base["negative_result_rule"],
        },
        "claim_boundary": (
            "E11a-successor can establish only an exploratory external quality/size "
            "frontier across nine exact stock Ministral quantizations using E10f's "
            "validated safe-sampled scorer on native Arm64. It does not establish "
            "end-product service performance, promote a model, rewrite prior contracts, "
            "or support energy, PMU, local-device, fleet, cost, mixed-quant, imatrix, "
            "pruning, causal-kernel, or other-runtime claims."
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
