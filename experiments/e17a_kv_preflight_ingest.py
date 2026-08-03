#!/usr/bin/env python3
"""Validate E17a's bounded quantized-V compatibility preflight."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e17a_kv_preflight_freeze import INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure
    from e17a_kv_preflight_freeze import INPUT_PATHS


KV_ALLOCATION = re.compile(r"CPU KV buffer size =\s+([0-9.]+) MiB")


def option_value(argv: list[str], option: str) -> str:
    try:
        return argv[argv.index(option) + 1]
    except (ValueError, IndexError) as error:
        raise ValueError(f"E17a recipe lacks {option}") from error


def expected_argv(recipe: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    config = contract["execution"]["configurations"][recipe["configuration"]]
    return [
        recipe["server_path"],
        "--model", recipe["model"]["path"],
        "--alias", contract["selected"]["candidate"],
        "--threads", "4",
        "--threads-batch", "4",
        "--ctx-size", str(config["context_size"]),
        "--cache-type-k", config["kv_cache_type_k"],
        "--cache-type-v", config["kv_cache_type_v"],
        "--flash-attn", config["flash_attention"],
        "--parallel", "1",
        "--cont-batching",
        "--host", "127.0.0.1",
        "--port", "18081",
        "--no-webui",
        "--metrics",
        "--slots",
        "--jinja",
        "--temp", "0.0",
        "--seed", "424242",
        "--log-colors", "off",
        "--log-verbosity", "4",
        "--batch-size", "1024",
        "--ubatch-size", "512",
    ]


def validate_recipe(recipe: dict[str, Any], contract: dict[str, Any]) -> None:
    configuration = recipe.get("configuration")
    if configuration not in contract["execution"]["configurations"]:
        raise ValueError("E17a recipe configuration differs")
    if (
        recipe.get("experiment_id") != "E17a"
        or recipe.get("service") != contract["execution"]["configurations"][configuration]
        or recipe.get("model", {}).get("sha256") != contract["selected"]["model_sha256"]
        or recipe.get("model", {}).get("size_bytes") != contract["selected"]["model_size_bytes"]
        or recipe.get("argv") != expected_argv(recipe, contract)
        or not recipe.get("server_path", "").endswith("/runtime-files/bin/llama-server")
    ):
        raise ValueError("E17a recipe differs from the frozen contract")


def validate_successful_cell(
    cell: Path,
    configuration: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    recipe = load_object(cell / "recipe.json")
    validate_recipe(recipe, contract)
    if recipe["configuration"] != configuration:
        raise ValueError("E17a cell configuration differs")
    readiness = load_object(cell / "readiness.json")
    probe = load_object(cell / "probe.json")
    shell_status = int((cell / "server-shell-exit.txt").read_text().strip())
    if shell_status not in {0, 130} or readiness.get("status") != "ok":
        raise ValueError("E17a successful cell process state differs")

    parameters = probe.get("parameters")
    result = probe.get("result")
    cases = probe.get("cases")
    expected_ids = contract["quality_preflight"]["task_ids"]
    if (
        probe.get("experiment_id") != "E17a"
        or not isinstance(parameters, dict)
        or not isinstance(result, dict)
        or not isinstance(cases, list)
        or parameters.get("configuration") != configuration
        or parameters.get("measured_tasks") != len(expected_ids)
        or parameters.get("prompt_cache") is not False
        or parameters.get("max_output_tokens") != 8
        or parameters.get("seed") != 424242
        or result.get("total") != len(expected_ids)
        or result.get("failures") != 0
        or result.get("status_counts") != {"200": len(expected_ids)}
        or [case.get("id") for case in cases] != expected_ids
        or any(case.get("predicted") not in {"A", "B", "C", "D"} for case in cases)
    ):
        raise ValueError("E17a quality preflight evidence differs")

    log = (cell / "server.stderr.log").read_text(errors="replace")
    allocations = KV_ALLOCATION.findall(log)
    if len(allocations) != 1 or "flash_attn" not in log:
        raise ValueError("E17a KV allocation mechanism proof differs")
    return {
        "supported": True,
        "kv_allocation_mib": float(allocations[0]),
        "readiness_ms": readiness["ready_ms"],
        "answers": {case["id"]: case["predicted"] for case in cases},
        "correct": result["correct"],
        "total": result["total"],
        "reference_prediction_mismatches": result["reference_prediction_mismatches"],
        "requests_per_second": result["requests_per_second"],
        "http_ms": result["http_ms"],
        "server_process_cpu": result["server_process_cpu"],
        "recipe_sha256": sha256_file(cell / "recipe.json"),
        "probe_sha256": sha256_file(cell / "probe.json"),
        "server_stderr_sha256": sha256_file(cell / "server.stderr.log"),
    }


def validate_failed_cell(
    cell: Path,
    configuration: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    recipe = load_object(cell / "recipe.json")
    validate_recipe(recipe, contract)
    if recipe["configuration"] != configuration:
        raise ValueError("E17a failed cell configuration differs")
    caller_status = int((cell / "caller-exit.txt").read_text().strip())
    stderr = cell / "server.stderr.log"
    if caller_status == 0 or not stderr.exists():
        raise ValueError("E17a failed-cell boundary differs")
    return {
        "supported": False,
        "caller_exit_status": caller_status,
        "failure_stage": "server launch, readiness, request, or shutdown preflight",
        "recipe_sha256": sha256_file(cell / "recipe.json"),
        "server_stderr_sha256": sha256_file(stderr),
        "server_stderr_tail": stderr.read_text(errors="replace")[-4000:],
    }


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("experiment_id") != "E17a" or load_object(evidence / "contract.json") != contract:
        raise ValueError("E17a contract differs")
    for name, relative in INPUT_PATHS.items():
        if sha256_file(root / relative) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E17a input differs for {name}")

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E17a evidence is not native Arm64")
    if load_object(evidence / "e9a-workflow-summary.json") != load_object(
        root / INPUT_PATHS["e9a_manifest"]
    ):
        raise ValueError("E17a E9a prerequisite differs")
    artifact = load_object(evidence / "e9a-artifact.json")
    provenance = contract["runtime"]["artifact"]
    if (
        str(artifact.get("id")) != provenance["id"]
        or artifact.get("name") != provenance["name"]
        or artifact.get("digest") != provenance["digest"]
        or artifact.get("size_in_bytes") != provenance["size_bytes"]
    ):
        raise ValueError("E17a runtime artifact identity differs")
    closure = validate_runtime_closure(evidence / "runtime/runtime-closure.json")
    server = evidence / "runtime/runtime-files/bin/llama-server"
    if sha256_file(server) != contract["runtime"]["server_sha256"]:
        raise ValueError("E17a server binary differs")
    model_digest = (evidence / "model-sha256.txt").read_text().split()
    if len(model_digest) != 2 or model_digest[0] != contract["selected"]["model_sha256"]:
        raise ValueError("E17a model differs")

    cells: dict[str, Any] = {}
    for index, configuration in enumerate(contract["execution"]["order"], start=1):
        cell = evidence / f"cells/{index:02d}-{configuration}"
        caller_status = int((cell / "caller-exit.txt").read_text().strip())
        cells[configuration] = (
            validate_successful_cell(cell, configuration, contract)
            if caller_status == 0
            else validate_failed_cell(cell, configuration, contract)
        )

    baseline = cells["f16_f16"]
    if not baseline["supported"]:
        raise ValueError("E17a f16/f16 control did not establish a valid API path")
    supported_quantized = [
        name for name in contract["execution"]["quantized_candidates"]
        if cells[name]["supported"]
    ]
    allocations = [cells[name]["kv_allocation_mib"] for name in supported_quantized]
    if any(value >= baseline["kv_allocation_mib"] for value in allocations):
        raise ValueError("E17a quantized KV allocation did not fall below f16/f16")
    if len(allocations) == 2 and not allocations[1] < allocations[0]:
        raise ValueError("E17a q4/q4 allocation did not fall below q8/q8")

    successor_allowed = bool(supported_quantized)
    return {
        "schema_version": 1,
        "experiment_id": "E17a",
        "status": (
            "valid_quantized_v_compatibility_preflight"
            if successor_allowed
            else "valid_no_quantized_v_compatibility"
        ),
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "runtime": {"artifact": provenance, "closure": closure},
        "selected": contract["selected"],
        "cells": cells,
        "decision": {
            "supported_quantized_configurations": supported_quantized,
            "long_context_successor_allowed": successor_allowed,
            "selection_basis": "structural API compatibility and KV allocation only",
            "quality_or_performance_promotion_made": False,
        },
        "validation": {
            "native_arm64": True,
            "exact_e9a_runtime_closure": True,
            "exact_selected_model": True,
            "fresh_process_per_configuration": True,
            "flash_attention_on_for_all_configurations": True,
            "request_cache_disabled": True,
            "all_answers_and_failures_retained": True,
        },
        "claim_boundary": contract["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"], "decision": manifest["decision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
