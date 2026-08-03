#!/usr/bin/env python3
"""Freeze the E10f full external-holdout successor after E10e passes."""

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
    "adapter_contract": Path("experiments/e10d_contract.json"),
    "e9a_contract": Path("experiments/e9a_contract.json"),
    "e9b_plan": Path("experiments/e9b_preflight_plan.json"),
    "models": Path("experiments/e3f_models.json"),
    "e10b_manifest": Path("results/manifests/e10b-30797568757.json"),
    "e10c_negative_manifest": Path("results/manifests/e10c-30812791972.json"),
    "sample_map": Path("experiments/e10d_sample_map.json"),
    "sample_generator": Path("experiments/e9b_samples.py"),
    "task_arc_easy": Path("experiments/e9b_tasks/e9b_arc_easy.yaml"),
    "task_hellaswag": Path("experiments/e9b_tasks/e9b_hellaswag.yaml"),
    "task_winogrande": Path("experiments/e9b_tasks/e9b_winogrande.yaml"),
    "task_utils": Path("experiments/e9b_tasks/e9b_utils.py"),
    "requirements": Path("experiments/e10d_requirements.txt"),
    "primitive_patch": Path(
        "patches/llama.cpp/b10216/0004-server-select-exact-token-probabilities.patch"
    ),
    "prepare": Path("experiments/e10d_prepare.py"),
    "preflight": Path("experiments/e10d_preflight.py"),
    "probe": Path("experiments/e10f_probe.py"),
    "ingest": Path("experiments/e10f_ingest.py"),
    "cell_runner": Path("experiments/e10f_cell.sh"),
    "freeze": Path("experiments/e10f_freeze.py"),
    "test": Path("tests/test_e10f.py"),
    "failure_ingest": Path("experiments/e10d_failure_ingest.py"),
    "failure_test": Path("tests/test_e10d_failure.py"),
    "e10d_pair_manifest": Path("results/manifests/e10d-30818303255.json"),
    "e10d_control_manifest": Path(
        "results/manifests/e10d-ministral3_3b_q4_0-30818303255.json"
    ),
    "e10e_plan": Path("experiments/e10e_probability_plan.json"),
    "e10e_manifest": Path("results/manifests/e10e-30827797407.json"),
}


def validate_prerequisites() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    adapter = load_object(STATIC_INPUTS["adapter_contract"])
    pair = load_object(STATIC_INPUTS["e10d_pair_manifest"])
    control = load_object(STATIC_INPUTS["e10d_control_manifest"])
    preflight = load_object(STATIC_INPUTS["e10e_manifest"])
    if (
        pair.get("status") != "invalid_external_holdout_pair_retained"
        or pair.get("decision", {}).get("original_contract_rewrite_allowed")
        is not False
        or pair.get("decision", {}).get("bounded_compatibility_preflight_allowed")
        is not True
        or control.get("status") != "invalid_external_holdout_cell_retained"
        or control.get("model") != adapter["models"][1]
        or control.get("prepared_sha256") != pair.get("prepared_sha256")
        or preflight.get("status")
        != "valid_probability_api_compatibility_preflight"
        or preflight.get("decision", {}).get("successor_dispatch_allowed") is not True
        or preflight.get("decision", {}).get("full_holdout_validated") is not False
        or preflight.get("comparison", {}).get(
            "maximum_original_vs_forced_safe_prefailure_logprob_delta"
        )
        > 0.000001
        or preflight.get("comparison", {}).get(
            "maximum_forced_safe_repeat_logprob_delta"
        )
        > 0.000001
    ):
        raise ValueError("E10f exact E10d/E10e prerequisites differ")
    return adapter, control, preflight


def build_plan() -> dict[str, Any]:
    adapter, control, preflight = validate_prerequisites()
    e10e_plan = load_object(STATIC_INPUTS["e10e_plan"])
    inputs: dict[str, str] = {}
    for name, path in STATIC_INPUTS.items():
        inputs[f"{name}_path"] = str(path)
        inputs[f"{name}_sha256"] = sha256_file(path)
    safe = e10e_plan["safe_sampling"]
    runtime_files = control["runtime"]["runtime_closure"]["files"]
    server_files = [item for item in runtime_files if item["relative_path"] == "bin/llama-server"]
    if len(server_files) != 1:
        raise ValueError("E10f prerequisite server binary differs")
    return {
        "schema_version": 1,
        "experiment_id": "E10f",
        "title": "Safe-sampled successor to the failed pinned external holdout",
        "state": "frozen after E10e independently validates and before any E10f model outcome is observed",
        "hypothesis": "With the E10e-validated one-byte sampled token separating response serialization from target scoring, both exact E10d model cells will complete all 14,374 requested target probabilities and provide a valid supplemental external robustness comparison.",
        "inputs": inputs,
        "prerequisites": {
            "e10d": {
                "run_id": control["github"]["run_id"],
                "run_attempt": control["github"]["run_attempt"],
                "artifact_name": control["github"]["artifact_name"],
                "artifact_id": control["github"]["artifact_id"],
                "pair_manifest_sha256": inputs["e10d_pair_manifest_sha256"],
                "control_manifest_sha256": inputs["e10d_control_manifest_sha256"],
                "prepared_sha256": control["prepared_sha256"],
                "required_status": "invalid_external_holdout_pair_retained",
                "original_contract_rewritten": False,
            },
            "e10e": {
                "run_id": preflight["github"]["run_id"],
                "run_attempt": preflight["github"]["run_attempt"],
                "artifact_name": preflight["github"]["artifact_name"],
                "artifact_id": preflight["github"]["artifact_id"],
                "manifest_sha256": inputs["e10e_manifest_sha256"],
                "contract_sha256": preflight["contract_sha256"],
                "required_status": "valid_probability_api_compatibility_preflight",
                "successor_dispatch_allowed": True,
            },
            "binary_reuse": {
                "source_artifact": control["github"]["artifact_name"],
                "server_sha256": server_files[0]["sha256"],
                "server_size_bytes": server_files[0]["size_bytes"],
                "runtime_closure_file_count": control["runtime"]["runtime_closure"]["file_count"],
                "source_diff_sha256": adapter["service"]["source_diff_sha256"],
                "policy": "Download and independently re-ingest the exact retained E10d control artifact, then reuse its native Arm binary closure for both fresh E10f model processes. Do not rebuild or substitute another binary in this run.",
            },
        },
        "external_holdout": adapter["external_holdout"],
        "models": adapter["models"],
        "service": adapter["service"],
        "workload": {
            **adapter["workload"],
            "prepared_sha256": control["prepared_sha256"],
            "workload_reuse": "Reuse the byte-exact prepared.json from the retained E10d control artifact for both cells; do not redownload, regenerate, resample, or edit task data.",
        },
        "safe_sampling": {
            **safe,
            "validated_by_e10e_run": preflight["github"]["run_id"],
            "maximum_observed_prefailure_logprob_delta": preflight["comparison"][
                "maximum_original_vs_forced_safe_prefailure_logprob_delta"
            ],
            "maximum_observed_repeat_logprob_delta": preflight["comparison"][
                "maximum_forced_safe_repeat_logprob_delta"
            ],
        },
        "scoring": {
            "mechanism": "For every frozen candidate token, request that target ID from the raw pre-sampling softmax while forcing sampled token 1046 with logit bias +100.0. Append the actual target to the next explicit prompt; sampled output is never used for score or prefix construction.",
            "harness_relationship": adapter["scoring"]["harness_relationship"],
            "prediction_rule": adapter["scoring"]["prediction_rule"],
            "normalized_prediction_rule": adapter["scoring"]["normalized_prediction_rule"],
            "raw_response_retention": "Retain every HTTP response before status, schema, probability, token, or content parsing.",
            "request_timeout_seconds": 60.0,
            "probe_parameters": {
                "cache_prompt_policy": "false for the first token of every candidate; true only for later tokens of that candidate",
                "score_distribution": "raw pre-sampling selected token log probability",
                "sampled_output_used_for_score": False,
                "safe_sampled_token_id": safe["token_id"],
                "safe_sampled_token_text": safe["token_text"],
                "safe_sampled_token_logit_bias": safe["logit_bias"],
                "raw_response_retained_before_parsing": True,
                "requests_per_token": 1,
                "max_length": adapter["workload"]["max_length"],
                "fewshot": adapter["workload"]["fewshot"],
                "apply_chat_template": adapter["workload"]["apply_chat_template"],
                "seed": adapter["workload"]["seed"],
            },
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "matrix_models_run_in_separate_native_jobs": True,
            "fresh_server_per_model": True,
            "exact_prerequisite_binary_closure_reused": True,
            "exact_prepared_workload_reused": True,
            "per_sample_logs": True,
            "raw_http_responses": True,
            "aggregate_requires_both_cells": True,
        },
        "acceptance": {
            **adapter["acceptance"],
            "all_sampled_tokens_must_equal": safe["token_id"],
            "all_sampled_text_must_equal": safe["token_text"],
            "all_raw_responses_retained_once": True,
            "prepared_sha256": control["prepared_sha256"],
            "server_binary_sha256": server_files[0]["sha256"],
        },
        "decision": {
            "quality_gate_used": False,
            "original_30_task_admission_contract_rewrite_allowed": False,
            "original_e10d_rewrite_allowed": False,
            "poor_results_must_be_retained": True,
            "promotion_claim": "Supplemental robustness evidence only; E10f cannot replace the original 30-task admission contract or change E10d's failed status.",
            "frontier_authorization_rule": "A separately frozen successor stock or generated frontier may use E10f only if both cells and the aggregate validate with zero failures and all raw responses retained exactly once.",
        },
        "negative_result_rule": "Retain low accuracy, Q4_K_M regressions, task-specific disagreement, any missing probability, safe-token mismatch, score/schema failure, raw-response loss, binary/workload drift, process failure, or incomplete cell without changing tasks, samples, models, metrics, safe token, bias, scoring rule, or gates.",
        "claim_boundary": "E10f can provide supplemental external multiple-choice robustness for two exact Ministral quantizations on the three pinned E9b task subsets through the E10e-validated safe-sampled serial adapter and exact reused E10d binary/workload artifacts. It does not rewrite failed E10d or the original 30-task admission contract and makes no service-performance, energy, PMU, local-device, fleet, cost, concurrency, cache-policy, other-runtime, or causal claim.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = build_plan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
