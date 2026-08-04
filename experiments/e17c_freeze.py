#!/usr/bin/env python3
"""Freeze E17c's focused 8K-context serving-density successor."""

from __future__ import annotations

import argparse
import copy
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
    "predecessor_failure": Path(
        "results/manifests/e17b-30857705994-failure.json"
    ),
    "predecessor_contract": Path("experiments/e17b_contract.json"),
    "e17a_manifest": Path("results/manifests/e17a-30856539977.json"),
    "e9a_manifest": Path("results/manifests/e9a-30764802071.json"),
    "source_tasks": Path("experiments/e17b_tasks.json"),
    "tasks": Path("experiments/e17c_tasks.json"),
    "probe": Path("experiments/e17c_probe.py"),
    "cell": Path("experiments/e17c_cell.sh"),
    "freeze": Path("experiments/e17c_freeze.py"),
    "ingest": Path("experiments/e17c_ingest.py"),
    "test": Path("tests/test_e17c.py"),
}


def task_identity(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(task[key])
        for key in (
            "id",
            "seed",
            "needle_fraction",
            "retrieval_key",
            "answer",
            "options",
        )
    }


def build_contract(root: Path) -> dict[str, Any]:
    predecessor = load_object(root / INPUT_PATHS["predecessor_failure"])
    predecessor_contract = load_object(root / INPUT_PATHS["predecessor_contract"])
    e17a = load_object(root / INPUT_PATHS["e17a_manifest"])
    e9a = load_object(root / INPUT_PATHS["e9a_manifest"])
    source_tasks = load_object(root / INPUT_PATHS["source_tasks"])
    tasks = load_object(root / INPUT_PATHS["tasks"])
    supported = e17a.get("decision", {}).get("supported_quantized_configurations")
    if (
        predecessor.get("status")
        != "invalid_frozen_16k_service_timeout_and_f16_density_resource_failure"
        or predecessor.get("decision", {}).get(
            "separately_frozen_shorter_context_successor_allowed"
        )
        is not True
        or predecessor.get("decision", {}).get("sixteen_k_claim_allowed") is not False
        or predecessor_contract.get("experiment_id") != "E17b"
        or e17a.get("status") != "valid_quantized_v_compatibility_preflight"
        or supported != ["q8_0_q8_0", "q4_0_q4_0"]
        or e9a.get("status") != "valid_final_service_win"
        or tasks.get("experiment_id") != "E17c"
        or tasks.get("license") != "Apache-2.0"
        or tasks.get("target_prompt_tokens") != {"minimum": 4500, "maximum": 5000}
        or tasks.get("system_instruction") != source_tasks.get("system_instruction")
        or [task_identity(item) for item in tasks.get("tasks", [])]
        != [task_identity(item) for item in source_tasks.get("tasks", [])]
    ):
        raise ValueError("E17c prerequisite or task identity differs")

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)

    configurations = copy.deepcopy(predecessor_contract["execution"]["configurations"])
    cells = copy.deepcopy(predecessor_contract["execution"]["cells"])
    return {
        "schema_version": 1,
        "experiment_id": "E17c",
        "title": "8K-context quantized-K/V quality and density successor",
        "state": (
            "separately frozen after retaining E17b's terminal 16K timeout and "
            "f16 allocation failure, before observing any E17c prompt, answer, "
            "allocation, readiness, latency, throughput, memory, or failure result"
        ),
        "hypothesis": (
            "At least one E17a-supported quantized K/V pair preserves all eight "
            "predeclared retrieval answers at 4.5K-5K prompt length and the "
            "four-slot service SLO while admitting eight 8K-context slots under "
            "the unchanged 15 GiB process address-space ceiling."
        ),
        "inputs": inputs,
        "predecessor": {
            "experiment_id": "E17b",
            "run_id": predecessor["github"]["run_id"],
            "status": predecessor["status"],
            "summary_sha256": inputs["predecessor_failure_sha256"],
            "timeout_cells": predecessor["failure_summary"][
                "long_context_request_timeout_cells"
            ],
            "f16_eight_slot_attempted_allocation_mib": predecessor["cells"][8][
                "attempted_allocation_mib"
            ],
            "failed_contract_rehabilitated": False,
            "scientific_changes": {
                "context_tokens_per_slot": {"from": 16384, "to": 8192},
                "prompt_token_interval": {
                    "from": [14500, 15000],
                    "to": [4500, 5000],
                },
            },
        },
        "prerequisite": {
            "run_id": e17a["github"]["run_id"],
            "artifact_name": e17a["github"]["artifact_name"],
            "artifact_id": e17a["github"]["artifact_id"],
            "artifact_digest": e17a["github"]["artifact_digest"],
            "summary_sha256": inputs["e17a_manifest_sha256"],
            "supported_quantized_configurations": supported,
            "selection_basis": "E17a structural API compatibility and allocation only",
        },
        "runtime": copy.deepcopy(predecessor_contract["runtime"]),
        "selected": copy.deepcopy(predecessor_contract["selected"]),
        "workload": {
            "context_tokens_per_slot": 8192,
            "measured_tasks": len(tasks["tasks"]),
            "client_requests_per_cell": len(tasks["tasks"]),
            "client_concurrency_equals_slots": True,
            "prompt_token_minimum": tasks["target_prompt_tokens"]["minimum"],
            "prompt_token_maximum": tasks["target_prompt_tokens"]["maximum"],
            "needle_fractions": [item["needle_fraction"] for item in tasks["tasks"]],
            "answers": {item["id"]: item["answer"] for item in tasks["tasks"]},
            "request_timeout_seconds": 600.0,
            "prompt_cache": False,
            "fresh_process_per_cell": True,
            "task_identities_inherited_before_observation": True,
        },
        "scoring": copy.deepcopy(predecessor_contract["scoring"]),
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "logical_cpus": 4,
            "threads": 4,
            "threads_batch": 4,
            "batch_size": 1024,
            "micro_batch_size": 512,
            "flash_attention": "on",
            "continuous_batching": True,
            "process_address_space_limit_bytes": 16_106_127_360,
            "configurations": configurations,
            "quantized_candidates": supported,
            "cells": cells,
            "four_slot_order_is_reverse_balanced": True,
            "eight_slot_order_places_resource_risk_last": True,
        },
        "acceptance": copy.deepcopy(predecessor_contract["acceptance"]),
        "decision": {
            **copy.deepcopy(predecessor_contract["decision"]),
            "e17b_failed_contract_rehabilitated": False,
            "eight_k_context_claim_only": True,
            "sixteen_k_claim_allowed": False,
        },
        "negative_result_rule": (
            "Retain E17c answer drift, probability-support failure, timeout, "
            "allocation regression, process-limit failure, latency or throughput "
            "regression, and incomplete density without changing tasks, prompt "
            "length, slot counts, cache types, resource ceiling, order, or gates."
        ),
        "claim_boundary": (
            "E17c can establish only exact-runtime 4.5K-5K synthetic retrieval "
            "quality and four/eight-slot behavior with 8K configured context per "
            "slot under a 15 GiB address-space ceiling on one four-vCPU GitHub "
            "Arm runner. It cannot rehabilitate E17b or establish 16K retrieval, "
            "broad quality, maximum context, fleet scaling, energy, PMU, local-"
            "device, or cost claims."
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
