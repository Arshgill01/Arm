#!/usr/bin/env python3
"""Validate E12b generated-quant quality cells and the combined frontier."""

from __future__ import annotations

import argparse
import json
import re
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
    from experiments.e11a_ingest import dominates, quality_coordinates
    from experiments.e7a_ingest import validate_runtime_closure
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
    from e11a_ingest import dominates, quality_coordinates
    from e7a_ingest import validate_runtime_closure


ARTIFACT_INPUTS = {
    "plan": "plan.json",
    "cell_runner": "cell-runner.sh",
    "freeze": "freeze.py",
    "adapter_contract": "adapter/contract.json",
}


def metadata_value(metadata: dict[str, Any], name: str) -> Any:
    field = metadata.get(name)
    return field.get("value") if isinstance(field, dict) else None


def validate_contract_inputs(
    evidence: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E12b":
        raise ValueError("contract does not identify E12b")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E12b contract")
    for key, artifact_name in ARTIFACT_INPUTS.items():
        source = root / contract["inputs"][f"{key}_path"]
        expected = contract["inputs"][f"{key}_sha256"]
        if (
            sha256_file(source) != expected
            or sha256_file(evidence / artifact_name) != expected
        ):
            raise ValueError(f"E12b input differs for {key}")
    for key in ("ingest", "test"):
        source = root / contract["inputs"][f"{key}_path"]
        if sha256_file(source) != contract["inputs"][f"{key}_sha256"]:
            raise ValueError(f"E12b implementation differs for {key}")
    adapter = validate_adapter_inputs(
        evidence / "adapter",
        root / contract["inputs"]["adapter_contract_path"],
        root,
    )
    if adapter != load_object(evidence / "adapter/contract.json"):
        raise ValueError("E12b adapter contract differs")
    return contract


def candidate_from_contract(
    contract: dict[str, Any], candidate_name: str
) -> dict[str, Any]:
    matches = [
        item for item in contract["candidates"] if item["candidate"] == candidate_name
    ]
    if len(matches) != 1:
        raise ValueError("E12b candidate is not frozen exactly once")
    return matches[0]


def validate_e12a_prerequisite(
    evidence: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    prerequisite = contract["prerequisites"]["e12a"]
    summary_path = evidence / "e12a/summary.json"
    imatrix_path = evidence / "e12a/imatrix.gguf"
    summary = load_object(summary_path)
    if (
        sha256_file(summary_path) != prerequisite["summary_sha256"]
        or summary.get("status") != prerequisite["required_status"]
        or summary.get("contract_sha256") != prerequisite["contract_sha256"]
        or summary.get("imatrix", {}).get("sha256") != prerequisite["imatrix_sha256"]
        or summary.get("imatrix", {}).get("size_bytes")
        != prerequisite["imatrix_size_bytes"]
        or sha256_file(imatrix_path) != prerequisite["imatrix_sha256"]
        or imatrix_path.stat().st_size != prerequisite["imatrix_size_bytes"]
        or not all(
            summary.get("validation", {}).get(key) is True
            for key in (
                "native_arm64",
                "exact_source_build_model",
                "deterministic_frozen_corpus",
                "holdouts_excluded",
                "complete_chunk_count",
                "gguf_metadata_valid",
                "statistics_retained",
            )
        )
    ):
        raise ValueError("E12b E12a prerequisite differs")
    return summary


def validate_quantization(
    evidence: Path,
    contract: dict[str, Any],
    candidate: dict[str, Any],
    model: dict[str, Any],
) -> dict[str, Any]:
    source = contract["source_model"]
    source_line = (evidence / "source-model-sha256.txt").read_text().split()
    if (
        len(source_line) != 2
        or source_line[0] != source["sha256"]
        or int((evidence / "source-model-size.txt").read_text())
        != source["size_bytes"]
    ):
        raise ValueError("E12b BF16 source identity differs")

    command = load_object(evidence / "quantize-command.json").get("argv")
    if not isinstance(command, list) or not command[0].endswith("/llama-quantize"):
        raise ValueError("E12b quantize command is incomplete")
    replacements = {
        "BF16_PATH": source_line[1],
        "OUTPUT_PATH": model["path"],
        "IMATRIX_PATH": str(evidence / "e12a/imatrix.gguf"),
    }
    expected = [command[0]] + [
        replacements.get(argument, argument)
        for argument in candidate["argv_after_binary"]
    ]
    if command != expected:
        raise ValueError("E12b quantize command differs from frozen recipe")

    process = parse_time_output((evidence / "quantize-time.log").read_text())
    if (
        process["exit_status"] != contract["acceptance"]["quantize_exit_status"]
        or process["maximum_rss_kib"] is None
    ):
        raise ValueError("E12b quantize process evidence differs")
    closure = validate_runtime_closure(
        evidence / "build/quantize-runtime-closure.json"
    )
    dependencies = sorted(
        {
            Path(item["resolved_path"]).name
            for item in closure["runtime_dependencies"]
        }
    )
    if {"libcrypto.so.3", "libssl.so.3"}.intersection(dependencies):
        raise ValueError("E12b quantizer unexpectedly retains OpenSSL")
    quantizer_line = (evidence / "build/quantize-sha256.txt").read_text().split()
    if len(quantizer_line) != 2 or len(quantizer_line[0]) != 64:
        raise ValueError("E12b quantizer identity evidence is incomplete")
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if (
        len(model_line) != 2
        or model_line[0] != model["sha256"]
        or model_line[1] != model["path"]
        or int((evidence / "model-size.txt").read_text()) != model["size_bytes"]
    ):
        raise ValueError("E12b generated model identity differs")

    dump = load_object(evidence / "model-metadata.json")
    metadata = dump.get("metadata")
    tensors = dump.get("tensors")
    if not isinstance(metadata, dict) or not isinstance(tensors, dict) or not tensors:
        raise ValueError("E12b generated GGUF dump is incomplete")
    imatrix_keys = {
        "quantize.imatrix.file",
        "quantize.imatrix.dataset",
        "quantize.imatrix.entries_count",
        "quantize.imatrix.chunks_count",
    }
    present = {key for key in imatrix_keys if key in metadata}
    if candidate["uses_imatrix"]:
        prerequisite = contract["prerequisites"]["e12a"]
        if (
            present != imatrix_keys
            or metadata_value(metadata, "quantize.imatrix.file")
            != str(evidence / "e12a/imatrix.gguf")
            or metadata_value(metadata, "quantize.imatrix.entries_count")
            != prerequisite["imatrix_entries"]
            or metadata_value(metadata, "quantize.imatrix.chunks_count")
            != prerequisite["imatrix_chunks"]
        ):
            raise ValueError("E12b imatrix metadata differs")
    elif present:
        raise ValueError("E12b control unexpectedly retains imatrix metadata")

    log = (evidence / "quantize.log").read_text(errors="replace")
    manual_overrides = log.count("applying manual override:")
    tensor_types = {
        name: value.get("type")
        for name, value in tensors.items()
        if isinstance(value, dict)
    }
    role = candidate["role"]
    if role == "predefined mixed-tensor candidate":
        expectation = candidate["override_validation"]
        if manual_overrides < expectation["minimum_manual_override_lines"]:
            raise ValueError("E12b mixed tensor override did not match")
        for name, expected_type in expectation.get("exact_tensor_types", {}).items():
            if tensor_types.get(name) != expected_type:
                raise ValueError(f"E12b tensor override differs for {name}")
        for item in expectation.get("tensor_type_patterns", []):
            pattern = re.compile(item["pattern"])
            matched = {
                name: tensor_type
                for name, tensor_type in tensor_types.items()
                if pattern.search(name)
            }
            if (
                len(matched) != item["expected_tensors"]
                or set(matched.values()) != {item["type"]}
            ):
                raise ValueError(
                    f"E12b tensor override pattern differs: {item['pattern']}"
                )
    return {
        "command": command,
        "process": process,
        "metadata_sha256": sha256_file(evidence / "model-metadata.json"),
        "gguf_tensor_count": len(tensors),
        "imatrix_metadata_keys": sorted(present),
        "manual_override_lines": manual_overrides,
        "quantizer_sha256": quantizer_line[0],
        "quantizer_runtime_closure": closure,
        "quantizer_dynamic_dependency_basenames": dependencies,
    }


def cell_summary(
    evidence: Path, contract_path: Path, root: Path, candidate_name: str
) -> dict[str, Any]:
    contract = validate_contract_inputs(evidence, contract_path, root)
    candidate = candidate_from_contract(contract, candidate_name)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E12b evidence is not native Arm64")
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
        raise ValueError("E12b generated model descriptor differs")
    validate_recipe(recipe, adapter, model)
    quantization = validate_quantization(evidence, contract, candidate, model)

    readiness = load_object(evidence / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not 0 <= ready_ms <= contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError("E12b readiness differs")
    server_process = parse_time_output((evidence / "server-time.log").read_text())
    if (
        server_process["exit_status"]
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or server_process["maximum_rss_kib"] is None
        or server_process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
    ):
        raise ValueError("E12b server process evidence differs")

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
        "experiment_id": "E12b",
        "status": "valid_generated_quant_quality_cell",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": sha256_file(evidence / "prepared.json"),
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
        "quality_coordinates": coordinates,
        **probe,
        "validation": {
            "native_arm64": True,
            "exact_bf16_source": True,
            "exact_e12a_imatrix": True,
            "frozen_quantization_recipe": True,
            "exact_e10d_adapter": True,
            "same_frozen_workload": True,
            "all_raw_responses_retained": True,
            "zero_request_failures": True,
            "minimum_quality_gate_used": False,
        },
        "claim_boundary": contract["claim_boundary"],
    }


def frontier(cells: list[dict[str, Any]]) -> list[str]:
    return [
        cell["model"]["candidate"]
        for cell in cells
        if not any(
            dominates(other, cell)
            for other in cells
            if other["model"]["candidate"] != cell["model"]["candidate"]
        )
    ]


def aggregate_summary(
    contract_path: Path, cell_paths: list[Path], stock_path: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    expected = [item["candidate"] for item in contract["candidates"]]
    loaded = [load_object(path) for path in cell_paths]
    by_name = {cell.get("model", {}).get("candidate"): cell for cell in loaded}
    if (
        len(loaded) != len(expected)
        or set(by_name) != set(expected)
        or any(
            cell.get("status") != "valid_generated_quant_quality_cell"
            or cell.get("contract_sha256") != sha256_file(contract_path)
            or cell.get("request_failures") != 0
            for cell in loaded
        )
        or len({cell.get("prepared_sha256") for cell in loaded}) != 1
    ):
        raise ValueError("E12b generated cell set differs")
    generated = [by_name[name] for name in expected]

    stock = load_object(stock_path)
    prerequisite = contract["prerequisites"]["e11a"]
    stock_models = stock.get("models")
    if (
        sha256_file(stock_path) != prerequisite["summary_sha256"]
        or stock.get("status") != prerequisite["required_status"]
        or stock.get("contract_sha256") != prerequisite["contract_sha256"]
        or stock.get("prepared_sha256") != generated[0]["prepared_sha256"]
        or not isinstance(stock_models, list)
        or len(stock_models) != 9
        or not all(
            stock.get("validation", {}).get(key) is True
            for key in (
                "native_arm64",
                "same_frozen_workload",
                "all_candidates_complete",
                "e10d_anchor_reused_without_rerun",
                "zero_request_failures",
                "per_sample_logs_retained",
            )
        )
    ):
        raise ValueError("E12b E11a stock prerequisite differs")
    combined = [*stock_models, *generated]
    if len({item["model"]["candidate"] for item in combined}) != len(combined):
        raise ValueError("E12b combined frontier names are not unique")
    paired = []
    for control_name, imatrix_name in contract["matched_pairs"]:
        control = by_name[control_name]
        imatrix = by_name[imatrix_name]
        paired.append(
            {
                "control": control_name,
                "imatrix": imatrix_name,
                "size_bytes_delta": imatrix["model"]["size_bytes"]
                - control["model"]["size_bytes"],
                "quality_coordinate_deltas": {
                    key: imatrix["quality_coordinates"][key]
                    - control["quality_coordinates"][key]
                    for key in control["quality_coordinates"]
                },
            }
        )
    return {
        "schema_version": 1,
        "experiment_id": "E12b",
        "status": "valid_matched_mixed_quant_quality_frontier",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": generated[0]["prepared_sha256"],
        "generated_models": generated,
        "stock_models": stock_models,
        "matched_imatrix_deltas": paired,
        "quality_size_frontier": frontier(combined),
        "validation": {
            "native_arm64": True,
            "all_generated_candidates_complete": True,
            "exact_e11a_stock_ladder": True,
            "same_frozen_workload": True,
            "matched_controls_complete": True,
            "zero_request_failures": True,
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
