#!/usr/bin/env python3
"""Freeze E17b's focused 16K long-context serving-density experiment."""

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
    "e17a_manifest": Path("results/manifests/e17a-30856539977.json"),
    "e17a_contract": Path("experiments/e17a_second_successor_contract.json"),
    "e9a_manifest": Path("results/manifests/e9a-30764802071.json"),
    "tasks": Path("experiments/e17b_tasks.json"),
    "probe": Path("experiments/e17b_probe.py"),
    "cell": Path("experiments/e17b_cell.sh"),
    "freeze": Path("experiments/e17b_freeze.py"),
    "ingest": Path("experiments/e17b_ingest.py"),
    "test": Path("tests/test_e17b.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    e17a = load_object(root / INPUT_PATHS["e17a_manifest"])
    e9a = load_object(root / INPUT_PATHS["e9a_manifest"])
    tasks = load_object(root / INPUT_PATHS["tasks"])
    supported = e17a.get("decision", {}).get("supported_quantized_configurations")
    if (
        e17a.get("status") != "valid_quantized_v_compatibility_preflight"
        or e17a.get("decision", {}).get("long_context_successor_allowed") is not True
        or supported != ["q8_0_q8_0", "q4_0_q4_0"]
        or e9a.get("status") != "valid_final_service_win"
        or tasks.get("experiment_id") != "E17b"
        or tasks.get("license") != "Apache-2.0"
        or [task.get("answer") for task in tasks.get("tasks", [])]
        != ["A", "B", "C", "D", "A", "B", "C", "D"]
    ):
        raise ValueError("E17b prerequisite differs")

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)

    configurations = {
        "f16_f16": {"kv_cache_type_k": "f16", "kv_cache_type_v": "f16"},
        "q8_0_q8_0": {"kv_cache_type_k": "q8_0", "kv_cache_type_v": "q8_0"},
        "q4_0_q4_0": {"kv_cache_type_k": "q4_0", "kv_cache_type_v": "q4_0"},
    }
    cells = [
        {"configuration": "f16_f16", "slots": 4, "repetition": 1},
        {"configuration": "q8_0_q8_0", "slots": 4, "repetition": 1},
        {"configuration": "q4_0_q4_0", "slots": 4, "repetition": 1},
        {"configuration": "q4_0_q4_0", "slots": 4, "repetition": 2},
        {"configuration": "q8_0_q8_0", "slots": 4, "repetition": 2},
        {"configuration": "f16_f16", "slots": 4, "repetition": 2},
        {"configuration": "q4_0_q4_0", "slots": 8, "repetition": 1},
        {"configuration": "q8_0_q8_0", "slots": 8, "repetition": 1},
        {"configuration": "f16_f16", "slots": 8, "repetition": 1},
    ]
    return {
        "schema_version": 1,
        "experiment_id": "E17b",
        "title": "16K long-context quantized-K/V quality and density",
        "state": (
            "frozen after E17a structurally admitted q8/q8 and q4/q4, before "
            "observing any 16K prompt, four-slot, eight-slot, quality, latency, "
            "throughput, memory, or failure result"
        ),
        "hypothesis": (
            "At least one E17a-supported quantized K/V pair preserves the frozen "
            "16K retrieval answers and four-slot service SLO while admitting eight "
            "16K slots under the same 15 GiB process address-space ceiling."
        ),
        "inputs": inputs,
        "prerequisite": {
            "run_id": e17a["github"]["run_id"],
            "artifact_name": e17a["github"]["artifact_name"],
            "artifact_id": e17a["github"]["artifact_id"],
            "artifact_digest": e17a["github"]["artifact_digest"],
            "summary_sha256": sha256_file(root / INPUT_PATHS["e17a_manifest"]),
            "supported_quantized_configurations": supported,
            "selection_basis": "E17a structural API compatibility and allocation only",
        },
        "runtime": {
            "artifact": e17a["runtime"]["artifact"],
            "configuration": "e7c_final",
            "server_sha256": "e15e14bd5d4f86e09a79603862f52db841de758ecc21b2c476a2ba92cc8ee40e",
            "source_commit": "876a4321163249c43ca4e986818fab5ab081f282",
            "source_tag": "b10216",
            "openssl": "off",
        },
        "selected": e17a["selected"],
        "workload": {
            "context_tokens_per_slot": 16384,
            "measured_tasks": len(tasks["tasks"]),
            "client_requests_per_cell": len(tasks["tasks"]),
            "client_concurrency_equals_slots": True,
            "prompt_token_minimum": tasks["target_prompt_tokens"]["minimum"],
            "prompt_token_maximum": tasks["target_prompt_tokens"]["maximum"],
            "needle_fractions": [task["needle_fraction"] for task in tasks["tasks"]],
            "answers": {task["id"]: task["answer"] for task in tasks["tasks"]},
            "request_timeout_seconds": 600.0,
            "prompt_cache": False,
            "fresh_process_per_cell": True,
        },
        "scoring": {
            "grammar": "root ::= [ABCD]",
            "maximum_output_tokens": 1,
            "temperature": 1.0,
            "samplers": ["temperature"],
            "seed": 424242,
            "n_probs": 32,
            "prediction": "highest conditional A/B/C/D probability; alphabetical exact-tie break",
            "retain_sampled_output": True,
        },
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
        "acceptance": {
            "required_architecture": "aarch64",
            "all_nine_cells_attempted": True,
            "f16_four_slot_cells_must_serve": True,
            "successful_cell_requires_zero_request_failures": True,
            "successful_cell_requires_exact_allocation_log": True,
            "successful_cell_requires_all_prompt_cache_counts_zero": True,
            "minimum_quantized_four_slot_throughput_ratio": 0.90,
            "maximum_quantized_four_slot_p95_ratio": 1.15,
            "minimum_eight_to_four_slot_throughput_ratio": 0.90,
            "maximum_eight_to_four_slot_p95_ratio": 2.00,
            "maximum_q8_allocation_ratio": 0.60,
            "maximum_q4_allocation_ratio": 0.35,
            "quantized_promotion_requires_all_eight_exact_answers_in_all_three_cells": True,
            "at_least_one_quantized_eight_slot_cell_must_serve_for_density_win": True,
            "failed_eight_slot_launch_is_valid_resource_negative": True,
        },
        "decision": {
            "evaluate_both_e17a_supported_quantized_pairs": True,
            "promote_only_candidates_passing_quality_allocation_and_service_gates": True,
            "retain_f16_eight_slot_success_or_resource_failure": True,
            "four_slot_performance_uses_two_repetitions": True,
            "eight_slot_result_is_capacity_and_service_evidence_not_a_repeated_default_benchmark": True,
            "no_global_service_promotion_without_separate_general_quality_confirmation": True,
        },
        "negative_result_rule": (
            "Retain long-context answer drift, probability-support failure, timeout, "
            "allocation regression, process-limit failure, latency or throughput "
            "regression, and incomplete density without changing tasks, prompt length, "
            "slot counts, cache types, resource ceiling, order, or gates."
        ),
        "claim_boundary": (
            "E17b can establish only exact-runtime 16K synthetic retrieval quality, "
            "four-slot service behavior, and eight-slot capacity under a 15 GiB process "
            "address-space ceiling on a four-vCPU Neoverse-N2 GitHub Arm runner. It does "
            "not establish broad task quality, maximum model context, fleet scaling, "
            "energy, PMU, local-device, or cost claims."
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
