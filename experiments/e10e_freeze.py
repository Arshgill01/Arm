#!/usr/bin/env python3
"""Freeze E10e from the exact retained E10d probability-entry failure."""

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
    "e10d_contract": Path("experiments/e10d_contract.json"),
    "e9a_contract": Path("experiments/e9a_contract.json"),
    "models": Path("experiments/e3f_models.json"),
    "primitive_patch": Path(
        "patches/llama.cpp/b10216/0004-server-select-exact-token-probabilities.patch"
    ),
    "preflight": Path("experiments/e10e_probability_preflight.py"),
    "ingest": Path("experiments/e10e_probability_ingest.py"),
    "cell_runner": Path("experiments/e10e_cell.sh"),
    "freeze": Path("experiments/e10e_freeze.py"),
    "test": Path("tests/test_e10e.py"),
}


def select_prepared_case(
    prepared: dict[str, Any], failure: dict[str, Any]
) -> dict[str, Any]:
    tasks = [
        task for task in prepared["tasks"] if task["task"] == failure["task"]
    ]
    if len(tasks) != 1:
        raise ValueError("E10e failure task differs from E10d prepared workload")
    samples = [
        sample
        for sample in tasks[0]["samples"]
        if sample["sample_ordinal"] == failure["sample_ordinal"]
    ]
    if len(samples) != 1 or samples[0]["source_index"] != failure["source_index"]:
        raise ValueError("E10e failure sample differs from E10d prepared workload")
    requests = [
        request
        for request in samples[0]["requests"]
        if request["choice_index"] == failure["failed_choice_index"]
    ]
    if len(requests) != 1:
        raise ValueError("E10e failure choice differs from E10d prepared workload")
    request = requests[0]
    missing_index = failure["failed_token_index"]
    candidate = request["candidate_tokens"]
    if (
        len(candidate) != failure["candidate_token_count"]
        or not 0 <= missing_index < len(candidate)
        or candidate[missing_index] != failure["failed_target_token_id"]
        or failure["retained_partial_token_responses"] != missing_index
        or failure["failure_response_received_but_not_retained"] is not True
    ):
        raise ValueError("E10e failure token differs from E10d prepared workload")
    sample = samples[0]
    return {
        "task": failure["task"],
        "sample_ordinal": failure["sample_ordinal"],
        "source_index": failure["source_index"],
        "source_document_sha256": sample["source_document_sha256"],
        "choice_index": request["choice_index"],
        "prompt_sha256": request["prompt_sha256"],
        "candidate_sha256": request["candidate_sha256"],
        "prompt_tokens": request["prompt_tokens"],
        "candidate_tokens": candidate,
        "original_missing_token_index": missing_index,
        "original_missing_target_token_id": failure["failed_target_token_id"],
    }


def build_cases(
    failure_manifest: dict[str, Any], prepared: dict[str, Any]
) -> dict[str, Any]:
    partial = failure_manifest.get("partial_evidence")
    errors = partial.get("errors") if isinstance(partial, dict) else None
    if (
        failure_manifest.get("status")
        != "invalid_external_holdout_cell_retained"
        or failure_manifest.get("decision", {}).get("negative_result_retained")
        is not True
        or failure_manifest.get("decision", {}).get("metrics_comparable") is not False
        or not isinstance(errors, list)
        or len(errors) != 2
        or prepared.get("schema_version") != 1
        or prepared.get("experiment_id") != "E10d"
        or prepared.get("tokenizer_parity_checked") is not True
    ):
        raise ValueError("E10e exact retained E10d prerequisite differs")
    selected = [select_prepared_case(prepared, failure) for failure in errors]
    if len({(item["task"], item["sample_ordinal"]) for item in selected}) != 2:
        raise ValueError("E10e failure cases are not distinct")
    return {
        "schema_version": 1,
        "experiment_id": "E10e-failure-cases",
        "source_e10d_prepared_sha256": failure_manifest["prepared_sha256"],
        "source_e10d_run_id": failure_manifest["github"]["run_id"],
        "source_e10d_artifact_name": failure_manifest["github"]["artifact_name"],
        "cases": selected,
    }


def build_plan(
    *,
    failure_manifest_path: Path,
    failure_manifest: dict[str, Any],
    cases_path: Path,
    cases: dict[str, Any],
) -> dict[str, Any]:
    e10d_contract = load_object(STATIC_INPUTS["e10d_contract"])
    models = load_object(STATIC_INPUTS["models"])
    model = failure_manifest["model"]
    source = models["variants"][model["candidate"]]
    inputs: dict[str, str] = {
        "failure_manifest_path": str(failure_manifest_path),
        "failure_manifest_sha256": sha256_file(failure_manifest_path),
        "cases_path": str(cases_path),
        "cases_sha256": sha256_file(cases_path),
    }
    for name, path in STATIC_INPUTS.items():
        inputs[f"{name}_path"] = str(path)
        inputs[f"{name}_sha256"] = sha256_file(path)
    return {
        "schema_version": 1,
        "experiment_id": "E10e-preflight",
        "title": "Native probability serialization compatibility preflight",
        "state": "frozen after E10d failure retention and before native E10e results",
        "hypothesis": "Forcing the sampled output to an already native-verified one-byte punctuation token will prevent llama-server from dropping the one-token completion probability record while preserving the exact requested candidate's raw pre-sampling log probability.",
        "inputs": inputs,
        "prerequisite": {
            "experiment_id": "E10d",
            "run_id": failure_manifest["github"]["run_id"],
            "run_attempt": failure_manifest["github"]["run_attempt"],
            "artifact_name": failure_manifest["github"]["artifact_name"],
            "artifact_id": failure_manifest["github"]["artifact_id"],
            "required_status": "invalid_external_holdout_cell_retained",
            "prepared_sha256": failure_manifest["prepared_sha256"],
            "strict_ingest_error": failure_manifest["strict_ingest_error"],
            "negative_result_retained": True,
        },
        "model": model,
        "model_source": {
            "repository": source["repository"],
            "revision": source["revision"],
            "path": source["entrypoint"],
        },
        "service": e10d_contract["service"],
        "cases": cases["cases"],
        "safe_sampling": {
            "token_id": 1046,
            "token_text": ".",
            "token_bytes": [46],
            "logit_bias": 100.0,
            "selection_rule": "Choose the ASCII full-stop token already present in both failing continuations. Native E10d raw responses for this exact model encode token 1046 as one byte and a complete one-token probability record.",
            "sampled_output_used_for_score": False,
            "requested_probability_distribution": "raw pre-sampling model softmax",
        },
        "variant_order": ["original", "forced_safe_1", "forced_safe_2"],
        "variants": {
            "original": {
                "forced_safe_token_id": None,
                "forced_safe_logit_bias": None,
                "expected_outcome": "reproduce_original_missing_entry",
            },
            "forced_safe_1": {
                "forced_safe_token_id": 1046,
                "forced_safe_logit_bias": 100.0,
                "expected_outcome": "complete_all_selected_probabilities",
            },
            "forced_safe_2": {
                "forced_safe_token_id": 1046,
                "forced_safe_logit_bias": 100.0,
                "expected_outcome": "complete_all_selected_probabilities",
            },
        },
        "probe_parameters": {
            "seed": 424242,
            "timeout": 60.0,
            "cache_prompt_policy": "false for the first token of each case; true only for later tokens",
            "probability_distribution": "raw pre-sampling selected token log probability",
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "required_architecture": "aarch64",
            "fresh_server_per_variant": True,
            "variant_count": 3,
            "full_holdout_run": False,
            "raw_response_retention": "Every attempted response, including the reproduced missing-entry response, is gzip-compressed before parsing and retained with hashes and sizes.",
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "original_failures_must_reproduce_exactly": True,
            "forced_safe_runs_must_complete": True,
            "forced_sampled_token_must_equal": 1046,
            "maximum_prefailure_logprob_delta": 0.000001,
            "maximum_repeat_logprob_delta": 0.000001,
            "maximum_ready_ms": 15000.0,
            "maximum_process_rss_kib": 8388608,
            "accepted_server_shell_exit_statuses": [0, 130],
        },
        "decision": {
            "successor_dispatch_rule": "Freeze a separately named full external-holdout successor only if the native original failures reproduce, both forced-safe variants complete, every forced token is exact, and both log-probability equivalence gates pass.",
            "failure_rule": "Retain any mismatch, missing response, changed selected log probability, unsafe sampled token, source/build drift, or native execution failure and do not dispatch the successor.",
            "original_e10d_rewrite_allowed": False,
        },
        "negative_result_rule": "Retain every native compatibility outcome without changing the failure cases, safe token, bias, source, model, variant order, repeat count, or tolerances.",
        "claim_boundary": "E10e is a two-case native Arm64 API-compatibility preflight for the exact failed Q4_0 E10d cell. Passing can authorize a separately frozen successor, but does not validate a full holdout, model quality, model comparison, quantization frontier, service performance, energy, PMU, cost, concurrency, cache policy, or another runtime.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--failure-manifest", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--output-cases", type=Path, required=True)
    parser.add_argument("--output-plan", type=Path, required=True)
    args = parser.parse_args()
    failure_manifest = load_object(args.failure_manifest)
    prepared = load_object(args.prepared)
    if sha256_file(args.prepared) != failure_manifest.get("prepared_sha256"):
        raise ValueError("E10e prepared artifact hash differs from retained E10d")
    cases = build_cases(failure_manifest, prepared)
    args.output_cases.parent.mkdir(parents=True, exist_ok=True)
    args.output_cases.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n")
    plan = build_plan(
        failure_manifest_path=args.failure_manifest,
        failure_manifest=failure_manifest,
        cases_path=args.output_cases,
        cases=cases,
    )
    args.output_plan.parent.mkdir(parents=True, exist_ok=True)
    args.output_plan.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"plan_sha256": sha256_file(args.output_plan)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
