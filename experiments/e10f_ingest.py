#!/usr/bin/env python3
"""Validate the safe-sampled E10f external-holdout successor."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e10d_ingest import (
        compare_models,
        finite,
        validate_preflight,
        validate_prepared,
        validate_probe,
        validate_raw_response,
        validate_recipe,
        validate_source_and_build,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e10d_ingest import (
        compare_models,
        finite,
        validate_preflight,
        validate_prepared,
        validate_probe,
        validate_raw_response,
        validate_recipe,
        validate_source_and_build,
    )


ARTIFACT_INPUTS = {
    "adapter_contract": "e10d-contract.json",
    "e9a_contract": "e9a-contract.json",
    "e9b_plan": "e9b-plan.json",
    "models": "models-manifest.json",
    "e10b_manifest": "e10b-manifest.json",
    "e10c_negative_manifest": "e10c-negative-manifest.json",
    "sample_map": "sample-map.json",
    "sample_generator": "e9b-samples.py",
    "task_arc_easy": "tasks/e9b_arc_easy.yaml",
    "task_hellaswag": "tasks/e9b_hellaswag.yaml",
    "task_winogrande": "tasks/e9b_winogrande.yaml",
    "task_utils": "tasks/e9b_utils.py",
    "requirements": "requirements.txt",
    "primitive_patch": "patches/0004-server-select-exact-token-probabilities.patch",
    "e10d_pair_manifest": "e10d-pair-manifest.json",
    "e10d_control_manifest": "e10d-control-manifest.json",
    "e10e_plan": "e10e-plan.json",
    "e10e_manifest": "e10e-manifest.json",
}


def validate_inputs(evidence: Path, plan_path: Path, root: Path) -> dict[str, Any]:
    plan = load_object(plan_path)
    if plan.get("schema_version") != 1 or plan.get("experiment_id") != "E10f":
        raise ValueError("plan does not identify E10f")
    if load_object(evidence / "contract.json") != plan:
        raise ValueError("artifact plan differs from frozen E10f")
    for key, value in plan["inputs"].items():
        if key.endswith("_path"):
            expected = plan["inputs"][f"{key[:-5]}_sha256"]
            if sha256_file(root / value) != expected:
                raise ValueError(f"E10f frozen input differs for {key}")
    for key, artifact in ARTIFACT_INPUTS.items():
        expected = plan["inputs"][f"{key}_sha256"]
        if sha256_file(evidence / artifact) != expected:
            raise ValueError(f"E10f artifact input differs for {key}")
    prerequisite = load_object(evidence / "e10e-manifest.json")
    if (
        prerequisite.get("status")
        != "valid_probability_api_compatibility_preflight"
        or prerequisite.get("decision", {}).get("successor_dispatch_allowed")
        is not True
        or prerequisite.get("contract_sha256")
        != plan["prerequisites"]["e10e"]["contract_sha256"]
    ):
        raise ValueError("E10f E10e prerequisite differs")
    return plan


def validate_safe_probe(
    evidence: Path,
    probe: dict[str, Any],
    prepared: dict[str, Any],
    model: dict[str, Any],
    plan: dict[str, Any],
    adapter_contract: dict[str, Any],
) -> dict[str, Any]:
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E10f"
        or probe.get("parameters") != plan["scoring"]["probe_parameters"]
    ):
        raise ValueError("E10f probe identity differs")
    adapted_probe = copy.deepcopy(probe)
    adapted_probe["experiment_id"] = "E10d"
    adapted_contract = copy.deepcopy(adapter_contract)
    adapted_contract["scoring"]["probe_parameters"] = plan["scoring"][
        "probe_parameters"
    ]
    summary = validate_probe(
        evidence,
        adapted_probe,
        prepared,
        model,
        adapted_contract,
    )
    safe = plan["safe_sampling"]
    raw_names = {path.name for path in (evidence / "raw").glob("*.json.gz")}
    referenced: set[str] = set()
    for task in probe["tasks"]:
        for sample in task["samples"]:
            for choice in sample["choices"]:
                candidate_count = choice["token_score_requests"]
                if choice["sampled_tokens"] != [safe["token_id"]] * candidate_count:
                    raise ValueError("E10f sampled token differs from frozen safe token")
                for record in choice["raw_responses"]:
                    path = record["path"]
                    if path in referenced:
                        raise ValueError("E10f raw response is referenced twice")
                    referenced.add(path)
                    raw = validate_raw_response(evidence / "raw", record)
                    if (
                        raw.get("tokens") != [safe["token_id"]]
                        or raw.get("content") != safe["token_text"]
                    ):
                        raise ValueError("E10f raw safe-token output differs")
    expected_raw = plan["workload"]["expected_summary"]["token_score_requests"]
    if referenced != raw_names or len(referenced) != expected_raw:
        raise ValueError("E10f raw response inventory differs")
    return {**summary, "raw_response_count": len(referenced)}


def cell_summary(
    evidence: Path, plan_path: Path, root: Path, model_name: str
) -> dict[str, Any]:
    plan = validate_inputs(evidence, plan_path, root)
    models = {model["candidate"]: model for model in plan["models"]}
    if model_name not in models:
        raise ValueError("E10f model is not frozen")
    model = models[model_name]
    adapter_contract = load_object(root / plan["inputs"]["adapter_contract_path"])
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != plan["acceptance"]["required_architecture"]:
        raise ValueError("E10f evidence is not native Arm64")
    source_build = validate_source_and_build(evidence, adapter_contract)
    validate_recipe(load_object(evidence / "recipe.json"), adapter_contract, model)
    readiness = load_object(evidence / "readiness.json")
    ready_ms = finite(readiness.get("ready_ms"), nonnegative=True)
    if (
        readiness.get("status") != "ok"
        or ready_ms > plan["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError("E10f readiness differs")
    process = parse_time_output((evidence / "server-time.log").read_text())
    if (
        process["exit_status"]
        not in plan["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"]
        > plan["acceptance"]["maximum_process_rss_kib"]
    ):
        raise ValueError("E10f server process evidence differs")
    model_line = (evidence / "model-sha256.txt").read_text().strip().split()
    if len(model_line) != 2 or model_line[0] != model["sha256"]:
        raise ValueError("E10f model file identity differs")
    prepared = validate_prepared(
        load_object(evidence / "prepared.json"),
        adapter_contract,
        load_object(evidence / "sample-map.json"),
    )
    if sha256_file(evidence / "prepared.json") != plan["workload"]["prepared_sha256"]:
        raise ValueError("E10f prepared workload hash differs")
    preflight = validate_preflight(evidence, adapter_contract)
    probe = validate_safe_probe(
        evidence,
        load_object(evidence / "probe.json"),
        prepared,
        model,
        plan,
        adapter_contract,
    )
    return {
        "schema_version": 1,
        "experiment_id": "E10f",
        "status": "valid_safe_sampled_external_holdout_cell",
        "contract_sha256": sha256_file(plan_path),
        "prepared_sha256": sha256_file(evidence / "prepared.json"),
        "model": model,
        "platform": platform,
        "runtime": source_build,
        "readiness_ms": ready_ms,
        "server_process": process,
        "preflight": {
            "status": preflight["status"],
            "maximum_repeat_sum_logprob_delta": preflight[
                "maximum_repeat_sum_logprob_delta"
            ],
            "maximum_repeat_token_logprob_delta": preflight[
                "maximum_repeat_token_logprob_delta"
            ],
        },
        **probe,
        "validation": {
            "native_arm64": True,
            "exact_e7c_service_plus_e10b_primitive": True,
            "tokenizer_parity": True,
            "synthetic_preflight": True,
            "all_raw_responses_retained_once": True,
            "all_sampled_tokens_safe_and_exact": True,
            "zero_request_failures": True,
            "minimum_quality_gate_used": False,
            "original_e10d_rewritten": False,
        },
        "claim_boundary": plan["claim_boundary"],
    }


def aggregate_summary(
    plan_path: Path, primary_path: Path, control_path: Path
) -> dict[str, Any]:
    plan = load_object(plan_path)
    primary = load_object(primary_path)
    control = load_object(control_path)
    expected = plan["models"]
    if (
        primary.get("status") != "valid_safe_sampled_external_holdout_cell"
        or control.get("status") != "valid_safe_sampled_external_holdout_cell"
        or primary.get("contract_sha256") != sha256_file(plan_path)
        or control.get("contract_sha256") != sha256_file(plan_path)
        or primary.get("prepared_sha256") != control.get("prepared_sha256")
        or primary.get("model") != expected[0]
        or control.get("model") != expected[1]
        or primary.get("request_failures") != 0
        or control.get("request_failures") != 0
    ):
        raise ValueError("E10f cells differ from frozen successor aggregate")
    return {
        "schema_version": 1,
        "experiment_id": "E10f",
        "status": "valid_safe_sampled_external_holdout",
        "contract_sha256": sha256_file(plan_path),
        "prepared_sha256": primary["prepared_sha256"],
        "models": [primary, control],
        "comparison": compare_models([primary, control]),
        "validation": {
            "native_arm64": True,
            "same_frozen_workload": True,
            "both_models_complete": True,
            "zero_request_failures": True,
            "per_sample_logs_retained": True,
            "all_raw_responses_retained_once": True,
            "minimum_quality_gate_used": False,
            "original_admission_contract_rewritten": False,
            "original_e10d_rewritten": False,
        },
        "claim_boundary": plan["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    cell = subparsers.add_parser("cell")
    cell.add_argument("--evidence-dir", type=Path, required=True)
    cell.add_argument("--plan", type=Path, required=True)
    cell.add_argument("--root", type=Path, required=True)
    cell.add_argument("--model", required=True)
    cell.add_argument("--output", type=Path, required=True)
    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--plan", type=Path, required=True)
    aggregate.add_argument("--primary", type=Path, required=True)
    aggregate.add_argument("--control", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "cell":
        output = cell_summary(args.evidence_dir, args.plan, args.root, args.model)
    else:
        output = aggregate_summary(args.plan, args.primary, args.control)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
