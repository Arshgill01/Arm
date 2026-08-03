#!/usr/bin/env python3
"""Validate E11a stock-quant external-quality cells and frontier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e10d_ingest import (
        validate_inputs as validate_adapter_inputs,
        validate_preflight,
        validate_prepared,
        validate_probe,
        validate_recipe,
        validate_source_and_build,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e10d_ingest import (
        validate_inputs as validate_adapter_inputs,
        validate_preflight,
        validate_prepared,
        validate_probe,
        validate_recipe,
        validate_source_and_build,
    )


ARTIFACT_INPUTS = {
    "plan": "plan.json",
    "models": "models.json",
    "cell_runner": "cell-runner.sh",
    "adapter_contract": "adapter/contract.json",
}


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E11a":
        raise ValueError("contract does not identify E11a")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E11a contract")
    for key, artifact_path in ARTIFACT_INPUTS.items():
        source = root / contract["inputs"][f"{key}_path"]
        expected = contract["inputs"][f"{key}_sha256"]
        if (
            sha256_file(source) != expected
            or sha256_file(evidence / artifact_path) != expected
        ):
            raise ValueError(f"E11a input hash differs for {key}")
    for key in ("ingest", "test"):
        if (
            sha256_file(root / contract["inputs"][f"{key}_path"])
            != contract["inputs"][f"{key}_sha256"]
        ):
            raise ValueError(f"E11a implementation hash differs for {key}")
    adapter_contract = validate_adapter_inputs(
        evidence / "adapter",
        root / contract["inputs"]["adapter_contract_path"],
        root,
    )
    if adapter_contract != load_object(evidence / "adapter/contract.json"):
        raise ValueError("E11a adapter contract differs")
    return contract


def quality_coordinates(metrics: dict[str, dict[str, float]]) -> dict[str, float]:
    coordinates = {
        "e9b_arc_easy.acc_norm": metrics["e9b_arc_easy"]["acc_norm"],
        "e9b_hellaswag.acc_norm": metrics["e9b_hellaswag"]["acc_norm"],
        "e9b_winogrande.acc": metrics["e9b_winogrande"]["acc"],
    }
    if any(not 0 <= value <= 1 for value in coordinates.values()):
        raise ValueError("E11a quality coordinate is out of range")
    return coordinates


def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_values = left["quality_coordinates"]
    right_values = right["quality_coordinates"]
    no_worse = left["model"]["size_bytes"] <= right["model"]["size_bytes"] and all(
        left_values[name] >= right_values[name] for name in left_values
    )
    strictly_better = left["model"]["size_bytes"] < right["model"]["size_bytes"] or any(
        left_values[name] > right_values[name] for name in left_values
    )
    return no_worse and strictly_better


def pareto_frontier(cells: list[dict[str, Any]]) -> list[str]:
    return [
        cell["model"]["candidate"]
        for cell in cells
        if not any(
            dominates(other, cell)
            for other in cells
            if other["model"]["candidate"] != cell["model"]["candidate"]
        )
    ]


def cell_summary(
    evidence: Path, contract_path: Path, root: Path, model_name: str
) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    models = {model["candidate"]: model for model in contract["models"]}
    if model_name not in models:
        raise ValueError("E11a model is not frozen")
    model = models[model_name]
    adapter = load_object(evidence / "adapter/contract.json")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E11a evidence is not native Arm64")
    runtime = validate_source_and_build(evidence, adapter)
    validate_recipe(load_object(evidence / "recipe.json"), adapter, model)
    readiness = load_object(evidence / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not 0 <= ready_ms <= contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError("E11a readiness differs")
    process = parse_time_output((evidence / "server-time.log").read_text())
    if (
        process["exit_status"]
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
    ):
        raise ValueError("E11a server process evidence differs")
    model_line = (evidence / "model-sha256.txt").read_text().strip().split()
    if len(model_line) != 2 or model_line[0] != model["sha256"]:
        raise ValueError("E11a model identity differs")
    selected = load_object(evidence / "sample-map.json")
    prepared = validate_prepared(
        load_object(evidence / "prepared.json"), adapter, selected
    )
    preflight = validate_preflight(evidence, adapter)
    probe = validate_probe(
        evidence,
        load_object(evidence / "probe.json"),
        prepared,
        model,
        adapter,
    )
    coordinates = quality_coordinates(probe["metrics"])
    return {
        "schema_version": 1,
        "experiment_id": "E11a",
        "status": "valid_stock_quant_quality_cell",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": sha256_file(evidence / "prepared.json"),
        "model": model,
        "platform": platform,
        "runtime": runtime,
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
        "quality_coordinates": coordinates,
        **probe,
        "validation": {
            "native_arm64": True,
            "exact_e10d_adapter": True,
            "same_frozen_workload": True,
            "tokenizer_parity": True,
            "synthetic_preflight": True,
            "all_raw_responses_retained": True,
            "zero_request_failures": True,
            "minimum_quality_gate_used": False,
        },
        "claim_boundary": contract["claim_boundary"],
    }


def aggregate_summary(
    contract_path: Path, cell_paths: list[Path], anchor_path: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    expected = [model["candidate"] for model in contract["models"]]
    loaded = [load_object(path) for path in cell_paths]
    by_name = {cell.get("model", {}).get("candidate"): cell for cell in loaded}
    if (
        len(by_name) != len(loaded)
        or set(by_name) != set(expected)
        or any(
            cell.get("status") != "valid_stock_quant_quality_cell" for cell in loaded
        )
        or any(
            cell.get("contract_sha256") != sha256_file(contract_path) for cell in loaded
        )
        or len({cell.get("prepared_sha256") for cell in loaded}) != 1
        or any(cell.get("request_failures") != 0 for cell in loaded)
    ):
        raise ValueError("E11a cell set differs from the frozen aggregate")
    new_cells = [by_name[name] for name in expected]
    anchor_aggregate = load_object(anchor_path)
    adapter_contract = load_object(Path(contract["inputs"]["adapter_contract_path"]))
    anchor_models = anchor_aggregate.get("models")
    if (
        anchor_aggregate.get("status") != "valid_external_holdout"
        or anchor_aggregate.get("contract_sha256")
        != contract["inputs"]["adapter_contract_sha256"]
        or not isinstance(anchor_models, list)
        or len(anchor_models) != 2
        or anchor_models[0].get("model", {}).get("candidate") != "ministral3_3b_q4_k_m"
        or anchor_models[1].get("model", {}).get("candidate") != "ministral3_3b_q4_0"
        or anchor_models[0].get("model") != contract["anchor_model"]
        or anchor_aggregate.get("prepared_sha256") != new_cells[0]["prepared_sha256"]
        or anchor_models[0].get("request_failures") != 0
        or anchor_models[1].get("request_failures") != 0
        or adapter_contract.get("experiment_id") != "E10d"
    ):
        raise ValueError("E11a E10d anchor differs from the frozen prerequisite")
    anchor = {
        **anchor_models[0],
        "quality_coordinates": quality_coordinates(anchor_models[0]["metrics"]),
    }
    full_by_name = {
        **by_name,
        anchor["model"]["candidate"]: anchor,
    }
    full_order = contract["full_candidate_order"]
    if set(full_by_name) != set(full_order):
        raise ValueError("E11a full candidate set differs")
    ordered = [full_by_name[name] for name in full_order]
    frontier = pareto_frontier(ordered)
    return {
        "schema_version": 1,
        "experiment_id": "E11a",
        "status": "valid_stock_quant_quality_ladder",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": ordered[0]["prepared_sha256"],
        "models": ordered,
        "q4_0_diagnostic_control": anchor_models[1],
        "quality_size_frontier": frontier,
        "validation": {
            "native_arm64": True,
            "same_frozen_workload": True,
            "all_candidates_complete": True,
            "e10d_anchor_reused_without_rerun": True,
            "zero_request_failures": True,
            "per_sample_logs_retained": True,
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
