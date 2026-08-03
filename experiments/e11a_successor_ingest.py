#!/usr/bin/env python3
"""Validate E11a's safe-sampled stock-quant successor and frontier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e10d_ingest import (
        finite,
        validate_preflight,
        validate_prepared,
        validate_recipe,
        validate_source_and_build,
    )
    from experiments.e10f_ingest import ARTIFACT_INPUTS as E10F_ARTIFACT_INPUTS
    from experiments.e10f_ingest import validate_safe_probe
    from experiments.e11a_ingest import pareto_frontier, quality_coordinates
    from experiments.e11a_successor_freeze import INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e10d_ingest import (
        finite,
        validate_preflight,
        validate_prepared,
        validate_recipe,
        validate_source_and_build,
    )
    from e10f_ingest import ARTIFACT_INPUTS as E10F_ARTIFACT_INPUTS
    from e10f_ingest import validate_safe_probe
    from e11a_ingest import pareto_frontier, quality_coordinates
    from e11a_successor_freeze import INPUT_PATHS


SUCCESSOR_ARTIFACT_INPUTS = {
    "base_plan": "base-plan.json",
    "models": "models.json",
    "e10f_contract": "e10f-contract.json",
    "cell_runner": "cell-runner.sh",
    "freeze": "successor-freeze.py",
    "ingest": "successor-ingest.py",
    "test": "successor-test.py",
}


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("experiment_id") != "E11a-successor" or load_object(evidence / "contract.json") != contract:
        raise ValueError("contract does not identify E11a-successor")
    for name, relative in INPUT_PATHS.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if sha256_file(root / relative) != expected:
            raise ValueError(f"E11a-successor input differs for {name}")
    for name, artifact_name in SUCCESSOR_ARTIFACT_INPUTS.items():
        if sha256_file(evidence / artifact_name) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E11a-successor artifact input differs for {name}")

    e10f_contract = load_object(root / contract["inputs"]["e10f_contract_path"])
    for key, artifact_name in E10F_ARTIFACT_INPUTS.items():
        expected = e10f_contract["inputs"][f"{key}_sha256"]
        if (
            sha256_file(root / e10f_contract["inputs"][f"{key}_path"]) != expected
            or sha256_file(evidence / artifact_name) != expected
        ):
            raise ValueError(f"E11a-successor E10f adapter input differs for {key}")
    return contract


def cell_summary(evidence: Path, contract_path: Path, root: Path, model_name: str) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    models = {model["candidate"]: model for model in contract["models"]}
    if model_name not in models:
        raise ValueError("E11a-successor model is not frozen")
    model = models[model_name]
    adapter = load_object(evidence / "e10d-contract.json")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E11a-successor evidence is not native Arm64")
    runtime = validate_source_and_build(evidence, adapter)
    validate_recipe(load_object(evidence / "recipe.json"), adapter, model)
    readiness = load_object(evidence / "readiness.json")
    ready_ms = finite(readiness.get("ready_ms"), nonnegative=True)
    if readiness.get("status") != "ok" or ready_ms > contract["acceptance"]["maximum_ready_ms"]:
        raise ValueError("E11a-successor readiness differs")
    process = parse_time_output((evidence / "server-time.log").read_text())
    if (
        process["exit_status"] not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"] > contract["acceptance"]["maximum_process_rss_kib"]
    ):
        raise ValueError("E11a-successor server process differs")
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if len(model_line) != 2 or model_line[0] != model["sha256"]:
        raise ValueError("E11a-successor model identity differs")
    prepared = validate_prepared(
        load_object(evidence / "prepared.json"),
        adapter,
        load_object(evidence / "sample-map.json"),
    )
    if sha256_file(evidence / "prepared.json") != contract["prerequisite"]["prepared_sha256"]:
        raise ValueError("E11a-successor prepared workload differs")
    preflight = validate_preflight(evidence, adapter)
    probe = validate_safe_probe(
        evidence,
        load_object(evidence / "probe.json"),
        prepared,
        model,
        contract,
        adapter,
    )
    return {
        "schema_version": 1,
        "experiment_id": "E11a-successor",
        "status": "valid_safe_sampled_stock_quant_cell",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": sha256_file(evidence / "prepared.json"),
        "model": model,
        "platform": platform,
        "runtime": runtime,
        "readiness_ms": ready_ms,
        "server_process": process,
        "preflight": {
            "status": preflight["status"],
            "maximum_repeat_sum_logprob_delta": preflight["maximum_repeat_sum_logprob_delta"],
            "maximum_repeat_token_logprob_delta": preflight["maximum_repeat_token_logprob_delta"],
        },
        "quality_coordinates": quality_coordinates(probe["metrics"]),
        **probe,
        "validation": {
            "native_arm64": True,
            "exact_e10f_safe_sampled_adapter": True,
            "same_frozen_workload": True,
            "tokenizer_parity": True,
            "synthetic_preflight": True,
            "all_raw_responses_retained_once": True,
            "all_sampled_tokens_safe_and_exact": True,
            "zero_request_failures": True,
            "minimum_quality_gate_used": False,
        },
        "claim_boundary": contract["claim_boundary"],
    }


def aggregate_summary(contract_path: Path, cell_paths: list[Path], anchor_path: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    expected = [model["candidate"] for model in contract["models"]]
    cells = [load_object(path) for path in cell_paths]
    by_name = {cell.get("model", {}).get("candidate"): cell for cell in cells}
    if (
        len(cells) != len(expected)
        or set(by_name) != set(expected)
        or any(
            cell.get("status") != "valid_safe_sampled_stock_quant_cell"
            or cell.get("contract_sha256") != sha256_file(contract_path)
            or cell.get("request_failures") != 0
            for cell in cells
        )
        or len({cell.get("prepared_sha256") for cell in cells}) != 1
    ):
        raise ValueError("E11a-successor cell set differs")

    retained = load_object(anchor_path)
    prerequisite = contract["prerequisite"]
    anchor_models = retained.get("models")
    validation = retained.get("validation", {})
    if (
        sha256_file(anchor_path) != prerequisite["retained_manifest_sha256"]
        or retained.get("status") != prerequisite["required_status"]
        or retained.get("contract_sha256") != prerequisite["contract_sha256"]
        or retained.get("prepared_sha256") != next(iter({cell["prepared_sha256"] for cell in cells}))
        or not isinstance(anchor_models, list)
        or len(anchor_models) != 2
        or anchor_models[0].get("model") != prerequisite["anchor"]
        or anchor_models[1].get("model") != prerequisite["diagnostic_control"]
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
        raise ValueError("E11a-successor E10f anchor differs")
    anchor = {
        **anchor_models[0],
        "quality_coordinates": quality_coordinates(anchor_models[0]["metrics"]),
    }
    full = {**by_name, anchor["model"]["candidate"]: anchor}
    if set(full) != set(contract["full_candidate_order"]):
        raise ValueError("E11a-successor full candidate set differs")
    ordered = [full[name] for name in contract["full_candidate_order"]]
    return {
        "schema_version": 1,
        "experiment_id": "E11a-successor",
        "status": "valid_safe_sampled_stock_quant_quality_ladder",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": ordered[0]["prepared_sha256"],
        "models": ordered,
        "q4_0_diagnostic_control": anchor_models[1],
        "quality_size_frontier": pareto_frontier(ordered),
        "validation": {
            "native_arm64": True,
            "same_frozen_workload": True,
            "all_candidates_complete": True,
            "exact_e10f_anchor_reused_without_rerun": True,
            "zero_request_failures": True,
            "per_sample_logs_retained": True,
            "all_raw_responses_retained_once": True,
            "minimum_quality_gate_used": False,
            "weighted_score_used": False,
        },
        "claim_boundary": contract["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    cell = subparsers.add_parser("cell")
    cell.add_argument("--evidence-dir", type=Path, required=True)
    cell.add_argument("--contract", type=Path, required=True)
    cell.add_argument("--root", type=Path, required=True)
    cell.add_argument("--model", required=True)
    cell.add_argument("--output", type=Path, required=True)
    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--contract", type=Path, required=True)
    aggregate.add_argument("--cell", type=Path, action="append", required=True)
    aggregate.add_argument("--anchor", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "cell":
        output = cell_summary(args.evidence_dir, args.contract, args.root, args.model)
    else:
        output = aggregate_summary(args.contract, args.cell, args.anchor)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
