#!/usr/bin/env python3
"""Freeze a bounded quantized-V server compatibility preflight."""

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
    "tasks": Path("experiments/e17a_tasks.json"),
    "source_tasks": Path("experiments/e3_tasks.json"),
    "models": Path("experiments/e3f_models.json"),
    "selected_manifest": Path("results/manifests/e3f-30656151957.json"),
    "e9a_manifest": Path("results/manifests/e9a-30764802071.json"),
    "probe": Path("experiments/e5b_inference_probe.py"),
    "cell": Path("experiments/e17a_kv_preflight_cell.sh"),
    "freeze": Path("experiments/e17a_kv_preflight_freeze.py"),
    "ingest": Path("experiments/e17a_kv_preflight_ingest.py"),
    "test": Path("tests/test_e17a.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    tasks = load_object(root / INPUT_PATHS["tasks"])
    source_tasks = load_object(root / INPUT_PATHS["source_tasks"])
    models = load_object(root / INPUT_PATHS["models"])
    selected_manifest = load_object(root / INPUT_PATHS["selected_manifest"])
    e9a = load_object(root / INPUT_PATHS["e9a_manifest"])
    task_ids = ["arithmetic-02", "logic-01", "systems-04"]
    source_by_id = {item["id"]: item for item in source_tasks["tasks"]}
    if (
        tasks.get("license") != "Apache-2.0"
        or tasks.get("instruction") != source_tasks.get("instruction")
        or tasks.get("tasks") != [source_by_id[task_id] for task_id in task_ids]
        or selected_manifest.get("status") != "valid_frontier"
        or e9a.get("status") != "valid_final_service_win"
    ):
        raise ValueError("E17a prerequisite differs")

    candidate = "ministral3_3b_q4_k_m"
    variant = models["variants"][candidate]
    model_file = variant["files"][0]
    reference_repetitions = selected_manifest["application"][candidate]["quality_repetitions"]
    reference_predictions = [item["predictions"] for item in reference_repetitions]
    if len(reference_predictions) < 2 or any(
        prediction != reference_predictions[0] for prediction in reference_predictions[1:]
    ):
        raise ValueError("E17a selected reference predictions differ")

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)

    return {
        "schema_version": 1,
        "experiment_id": "E17a",
        "title": "Bounded quantized-V compatibility preflight",
        "state": (
            "frozen before observing any quantized-V launch, allocation, answer, "
            "quality, latency, throughput, or failure result"
        ),
        "hypothesis": (
            "The exact E9a b10216 server can launch the selected Q4_K_M model with "
            "quantized K and V caches when flash attention is explicitly enabled."
        ),
        "inputs": inputs,
        "runtime": {
            "artifact": {
                "run_id": "30764802071",
                "name": "e9a-final-service-30764802071-1",
                "id": "8838874234",
                "digest": "sha256:3d360aed5fd02abf5421c3a23309f1abda56bf5f96c0e406a5c13897c15aae70",
                "size_bytes": 18_440_490,
                "summary_sha256": sha256_file(root / INPUT_PATHS["e9a_manifest"]),
            },
            "configuration": "e7c_final",
            "server_sha256": "e15e14bd5d4f86e09a79603862f52db841de758ecc21b2c476a2ba92cc8ee40e",
            "source_commit": "876a4321163249c43ca4e986818fab5ab081f282",
            "source_tag": "b10216",
            "openssl": "off",
        },
        "selected": {
            "candidate": candidate,
            "repository": variant["repository"],
            "revision": variant["revision"],
            "path": variant["entrypoint"],
            "model_sha256": model_file["sha256"],
            "model_size_bytes": model_file["size_bytes"],
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "fresh_process_per_configuration": True,
            "order": ["f16_f16", "q8_0_q8_0", "q4_0_q4_0"],
            "quantized_candidates": ["q8_0_q8_0", "q4_0_q4_0"],
            "configurations": {
                "f16_f16": {
                    "context_size": 1024,
                    "kv_cache_type_k": "f16",
                    "kv_cache_type_v": "f16",
                    "flash_attention": "on",
                },
                "q8_0_q8_0": {
                    "context_size": 1024,
                    "kv_cache_type_k": "q8_0",
                    "kv_cache_type_v": "q8_0",
                    "flash_attention": "on",
                },
                "q4_0_q4_0": {
                    "context_size": 1024,
                    "kv_cache_type_k": "q4_0",
                    "kv_cache_type_v": "q4_0",
                    "flash_attention": "on",
                },
            },
            "threads": 4,
            "parallel_slots": 1,
            "batch_size": 1024,
            "micro_batch_size": 512,
            "request_cache_prompt": False,
            "seed": 424242,
            "max_output_tokens": 8,
        },
        "quality_preflight": {
            "task_ids": task_ids,
            "task_selection_reason": (
                "one stable arithmetic control, one stable logic control, and the "
                "previously K-q4-sensitive systems-04 task"
            ),
            "expected_answers": {item["id"]: item["answer"] for item in tasks["tasks"]},
            "reference_predictions": {
                task_id: reference_predictions[0][task_id] for task_id in task_ids
            },
            "quality_or_performance_result_may_select_successor": False,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "f16_control_must_launch_and_serve": True,
            "all_three_configurations_must_be_attempted": True,
            "successful_cell_requires_zero_request_failures": True,
            "successful_cell_requires_exact_allocation_log": True,
            "quantized_allocation_must_be_below_f16": True,
            "failed_quantized_launch_is_valid_negative_evidence": True,
            "quantized_successor_requires_at_least_one_structurally_supported_quantized_configuration": True,
        },
        "decision": {
            "successor_configuration_rule": (
                "Include every frozen quantized candidate that launches, serves all "
                "preflight requests, and proves a smaller KV allocation; do not use "
                "preflight quality or performance to cherry-pick among supported candidates."
            ),
            "preflight_promotes_service_configuration": False,
            "preflight_makes_performance_claim": False,
        },
        "claim_boundary": (
            "E17a establishes only native API, launch, request, and allocation compatibility "
            "for three frozen 1K single-slot cache pairs. Its three-task answers and timings "
            "are diagnostic. It makes no long-context, serving-density, quality-robustness, "
            "performance, energy, PMU, local-device, fleet, or cost claim."
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
