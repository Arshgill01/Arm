#!/usr/bin/env python3
"""Validate safe-sampled E12b generated-quant cells and frontier."""

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
    from experiments.e10f_ingest import validate_safe_probe
    from experiments.e11a_ingest import quality_coordinates
    from experiments.e12b_ingest import (
        candidate_from_contract,
        frontier,
        validate_contract_inputs,
        validate_e12a_prerequisite,
        validate_quantization,
    )
    from experiments.e12b_successor_freeze import INPUT_PATHS
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
    from e10f_ingest import validate_safe_probe
    from e11a_ingest import quality_coordinates
    from e12b_ingest import (
        candidate_from_contract,
        frontier,
        validate_contract_inputs,
        validate_e12a_prerequisite,
        validate_quantization,
    )
    from e12b_successor_freeze import INPUT_PATHS


SUCCESSOR_ARTIFACT_INPUTS = {
    "successor_wrapper": "successor-wrapper.py",
    "successor_freeze": "successor-freeze.py",
    "ingest": "successor-ingest.py",
    "test": "successor-test.py",
    "safe_contract": "e10f-contract.json",
    "safe_probe": "e10f-probe.py",
    "safe_ingest": "e10f-ingest.py",
    "base_ingest": "base-ingest.py",
    "base_freeze": "base-freeze.py",
    "base_test": "base-test.py",
    "safe_manifest": "e10f-retained-manifest.json",
    "e12a_resume_contract": "e12a-resume-contract.json",
    "e11a_successor_contract": "e11a-successor-contract.json",
}


def validate_successor_inputs(
    evidence: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    contract = validate_contract_inputs(evidence, contract_path, root)
    if (
        contract.get("campaign_variant")
        != "safe-sampled-resumed-prerequisite-successor"
    ):
        raise ValueError("contract does not identify the E12b successor")
    for name, artifact_name in SUCCESSOR_ARTIFACT_INPUTS.items():
        relative = INPUT_PATHS[name]
        expected = contract["inputs"][f"{name}_sha256"]
        if (
            sha256_file(root / relative) != expected
            or sha256_file(evidence / artifact_name) != expected
        ):
            raise ValueError(f"E12b successor input differs for {name}")
    if (
        load_object(evidence / "e10f-contract.json")["scoring"] != contract["scoring"]
        or load_object(evidence / "e10f-contract.json")["safe_sampling"]
        != contract["safe_sampling"]
    ):
        raise ValueError("E12b successor safe-sampling contract differs")
    retained = load_object(evidence / "e10f-retained-manifest.json")
    prerequisite = contract["prerequisites"]["e10f"]
    if (
        retained.get("status") != prerequisite["required_status"]
        or retained.get("contract_sha256") != prerequisite["contract_sha256"]
        or retained.get("prepared_sha256") != prerequisite["prepared_sha256"]
        or sha256_file(evidence / "e10f-retained-manifest.json")
        != prerequisite["summary_sha256"]
    ):
        raise ValueError("E12b successor retained E10f prerequisite differs")
    return contract


def cell_summary(
    evidence: Path, contract_path: Path, root: Path, candidate_name: str
) -> dict[str, Any]:
    contract = validate_successor_inputs(evidence, contract_path, root)
    candidate = candidate_from_contract(contract, candidate_name)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E12b successor evidence is not native Arm64")
    e12a = validate_e12a_prerequisite(evidence, contract)
    adapter = load_object(evidence / "adapter/contract.json")
    runtime = validate_source_and_build(evidence, adapter)

    recipe = load_object(evidence / "recipe.json")
    model = recipe.get("model")
    if (
        not isinstance(model, dict)
        or model.get("candidate") != candidate_name
        or not isinstance(model.get("sha256"), str)
        or len(model["sha256"]) != 64
        or not isinstance(model.get("size_bytes"), int)
        or model["size_bytes"] <= 0
        or not isinstance(model.get("path"), str)
    ):
        raise ValueError("E12b successor generated model descriptor differs")
    validate_recipe(recipe, adapter, model)
    quantization = validate_quantization(evidence, contract, candidate, model)

    readiness = load_object(evidence / "readiness.json")
    ready_ms = finite(readiness.get("ready_ms"), nonnegative=True)
    if (
        readiness.get("status") != "ok"
        or ready_ms > contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError("E12b successor readiness differs")
    server_process = parse_time_output((evidence / "server-time.log").read_text())
    if (
        server_process["exit_status"]
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or server_process["maximum_rss_kib"] is None
        or server_process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
    ):
        raise ValueError("E12b successor server process differs")

    selected = load_object(evidence / "sample-map.json")
    prepared = validate_prepared(
        load_object(evidence / "prepared.json"), adapter, selected
    )
    prepared_sha = sha256_file(evidence / "prepared.json")
    if prepared_sha != contract["workload"]["prepared_sha256"]:
        raise ValueError("E12b successor prepared workload differs")
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
        "experiment_id": "E12b",
        "campaign_variant": contract["campaign_variant"],
        "status": "valid_safe_sampled_generated_quant_quality_cell",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": prepared_sha,
        "candidate_recipe": candidate,
        "model": model,
        "platform": platform,
        "e12a_imatrix": e12a["imatrix"],
        "runtime": runtime,
        "quantization": quantization,
        "readiness_ms": ready_ms,
        "server_process": server_process,
        "preflight": {
            "status": preflight["status"],
            "maximum_repeat_sum_logprob_delta": preflight[
                "maximum_repeat_sum_logprob_delta"
            ],
            "maximum_repeat_token_logprob_delta": preflight[
                "maximum_repeat_token_logprob_delta"
            ],
        },
        "quality_coordinates": quality_coordinates(probe["metrics"]),
        **probe,
        "validation": {
            "native_arm64": True,
            "exact_bf16_source": True,
            "exact_resumed_e12a_imatrix": True,
            "frozen_quantization_recipe": True,
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
            cell.get("status") != "valid_safe_sampled_generated_quant_quality_cell"
            or cell.get("contract_sha256") != sha256_file(contract_path)
            or cell.get("request_failures") != 0
            for cell in cells
        )
        or len({cell.get("prepared_sha256") for cell in cells}) != 1
    ):
        raise ValueError("E12b successor generated cell set differs")
    generated = [by_name[name] for name in expected]

    stock = load_object(stock_path)
    prerequisite = contract["prerequisites"]["e11a"]
    stock_models = stock.get("models")
    validation = stock.get("validation", {})
    if (
        sha256_file(stock_path) != prerequisite["summary_sha256"]
        or stock.get("status") != prerequisite["required_status"]
        or stock.get("contract_sha256") != prerequisite["contract_sha256"]
        or stock.get("prepared_sha256") != generated[0]["prepared_sha256"]
        or not isinstance(stock_models, list)
        or len(stock_models) != 9
        or not all(
            validation.get(key) is True
            for key in (
                "native_arm64",
                "same_frozen_workload",
                "all_candidates_complete",
                "exact_e10f_anchor_reused_without_rerun",
                "zero_request_failures",
                "per_sample_logs_retained",
                "all_raw_responses_retained_once",
            )
        )
    ):
        raise ValueError("E12b successor E11a stock prerequisite differs")

    combined = [*stock_models, *generated]
    if len({item["model"]["candidate"] for item in combined}) != len(combined):
        raise ValueError("E12b successor combined frontier names are not unique")
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
        "campaign_variant": contract["campaign_variant"],
        "status": "valid_safe_sampled_matched_mixed_quant_quality_frontier",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": generated[0]["prepared_sha256"],
        "generated_models": generated,
        "stock_models": stock_models,
        "matched_imatrix_deltas": paired,
        "quality_size_frontier": frontier(combined),
        "validation": {
            "native_arm64": True,
            "all_generated_candidates_complete": True,
            "exact_e11a_safe_sampled_stock_ladder": True,
            "same_frozen_workload": True,
            "matched_controls_complete": True,
            "zero_request_failures": True,
            "per_sample_logs_retained": True,
            "all_raw_responses_retained_once": True,
            "weighted_score_used": False,
            "minimum_quality_gate_used": False,
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
    cell.add_argument("--candidate", required=True)
    cell.add_argument("--output", type=Path, required=True)
    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--contract", type=Path, required=True)
    aggregate.add_argument("--cell", type=Path, action="append", required=True)
    aggregate.add_argument("--stock", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "cell":
        output = cell_summary(
            args.evidence_dir, args.contract, args.root, args.candidate
        )
    else:
        output = aggregate_summary(args.contract, args.cell, args.stock)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
