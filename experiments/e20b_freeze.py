#!/usr/bin/env python3
"""Freeze the focused repacked FFN gate/up activation-reuse experiment."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


INPUT_PATHS = {
    "base_contract": Path("experiments/e18a_successor_contract.json"),
    "e9a_manifest": Path("results/manifests/e9a-30764802071.json"),
    "e16a_manifest": Path("results/manifests/e16a-30837796757.json"),
    "e20a_manifest": Path("results/manifests/e20a-30865578508.json"),
    "manifest": Path("results/manifests/e3f-30656151957.json"),
    "models": Path("experiments/e3f_models.json"),
    "tasks": Path("experiments/e3_tasks.json"),
    "probe": Path("experiments/e5b_inference_probe.py"),
    "runtime_closure": Path("experiments/e7a_runtime_closure.py"),
    "cell": Path("experiments/e20b_cell.sh"),
    "freeze": Path("experiments/e20b_freeze.py"),
    "ingest": Path("experiments/e20b_ingest.py"),
    "test": Path("tests/test_e20b.py"),
    "patch_features": Path(
        "patches/llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch"
    ),
    "patch_q8": Path("patches/llama.cpp/0002-arm-q8-vector-narrowing-stores.patch"),
    "patch_reasoning": Path(
        "patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch"
    ),
    "patch_timing": Path("patches/llama.cpp/b10216/0008-cpu-node-timing.patch"),
    "patch_pair": Path(
        "patches/llama.cpp/b10216/0009-reuse-repack-pair-activation.patch"
    ),
}


def walk_objects(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_objects(child)


def validate_tensor_path(e16a: dict[str, Any]) -> dict[str, Any]:
    records: dict[str, tuple[str, str, int, int]] = {}
    pattern = re.compile(r"blk\.(\d+)\.ffn_(gate|up)\.weight")
    for item in walk_objects(e16a):
        name = item.get("tensor")
        if not isinstance(name, str) or pattern.fullmatch(name) is None:
            continue
        if not all(key in item for key in ("type", "parameter_type", "ne0", "ne1")):
            continue
        value = (
            str(item["type"]),
            str(item["parameter_type"]),
            int(item["ne0"]),
            int(item["ne1"]),
        )
        if name in records and records[name] != value:
            raise ValueError(f"E20b tensor execution path differs for {name}")
        records[name] = value
    expected = {
        f"blk.{layer}.ffn_{projection}.weight"
        for layer in range(26)
        for projection in ("gate", "up")
    }
    if set(records) != expected or any(
        value != ("q4_K", "q8_K", 3072, 9216) for value in records.values()
    ):
        raise ValueError("E20b selected FFN tensor execution path differs")
    return {
        "layers": 26,
        "projections_per_layer": ["gate", "up"],
        "weight_type": "q4_K",
        "activation_parameter_type": "q8_K",
        "input_width": 3072,
        "output_width": 9216,
    }


def build_contract(root: Path) -> dict[str, Any]:
    base = load_object(root / INPUT_PATHS["base_contract"])
    e9a = load_object(root / INPUT_PATHS["e9a_manifest"])
    e16a = load_object(root / INPUT_PATHS["e16a_manifest"])
    e20a = load_object(root / INPUT_PATHS["e20a_manifest"])
    models = load_object(root / INPUT_PATHS["models"])
    if (
        base.get("experiment_id") != "E18a"
        or e9a.get("status") != "valid_final_service_win"
        or e16a.get("status") != "valid_loader_feasibility"
        or e20a.get("status")
        != "valid_cpu_node_profile_fusion_candidate_recovered_without_remeasurement"
        or e20a.get("decision", {}).get("selected_family") != "ffn_gate_up"
        or e20a.get("decision", {}).get(
            "focused_fusion_feasibility_successor_allowed"
        )
        is not True
        or e20a.get("decision", {}).get("automatic_source_optimization_allowed")
        is not False
    ):
        raise ValueError("E20b prerequisite differs")
    candidate = base["selected"]["candidate"]
    variant = models["variants"][candidate]
    model_file = variant["files"][0]
    if (
        model_file["sha256"] != base["selected"]["model_sha256"]
        or model_file["size_bytes"] != base["selected"]["model_size_bytes"]
    ):
        raise ValueError("E20b selected model differs")

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)

    runtime = copy.deepcopy(base["runtime"])
    runtime["patches"] = [
        {
            "name": "feature_patch",
            "path": INPUT_PATHS["patch_features"].as_posix(),
            "sha256": inputs["patch_features_sha256"],
        },
        {
            "name": "q8_patch",
            "path": INPUT_PATHS["patch_q8"].as_posix(),
            "sha256": inputs["patch_q8_sha256"],
        },
        {
            "name": "reasoning_patch",
            "path": INPUT_PATHS["patch_reasoning"].as_posix(),
            "sha256": inputs["patch_reasoning_sha256"],
        },
        {
            "name": "timing_patch",
            "path": INPUT_PATHS["patch_timing"].as_posix(),
            "sha256": inputs["patch_timing_sha256"],
        },
        {
            "name": "pair_reuse_patch",
            "path": INPUT_PATHS["patch_pair"].as_posix(),
            "sha256": inputs["patch_pair_sha256"],
        },
    ]
    runtime["changed_files"] = [
        "common/reasoning-budget.cpp",
        "ggml/src/ggml-cpu/CMakeLists.txt",
        "ggml/src/ggml-cpu/arch/arm/quants.c",
        "ggml/src/ggml-cpu/ggml-cpu.c",
        "ggml/src/ggml-cpu/repack.cpp",
        "ggml/src/ggml-cpu/traits.cpp",
        "ggml/src/ggml-cpu/traits.h",
        "tests/test-reasoning-budget.cpp",
    ]
    runtime["source_diff_sha256"] = (
        "21fddaf1ad421312c67ac4f80b3a88c47ab7829e38aa172f86e7cf7607dc88dd"
    )

    order = []
    for block in range(3):
        first = block * 2 + 1
        second = first + 1
        order.extend(
            [
                {"profile": "reuse_off", "repetition": first},
                {"profile": "reuse_on", "repetition": first},
                {"profile": "reuse_on", "repetition": second},
                {"profile": "reuse_off", "repetition": second},
            ]
        )

    environment_name = "GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION"
    return {
        "schema_version": 1,
        "experiment_id": "E20b",
        "title": "Repacked FFN gate/up activation-conversion reuse",
        "state": (
            "frozen after E20a's valid selector recovery and source-path inspection, "
            "before any native patched build, mechanism preflight, service answer, or "
            "performance result was observed"
        ),
        "hypothesis": (
            "Reusing the exact Q8_K activation conversion across each adjacent Q4_K "
            "FFN gate/up pair improves median end-to-end service throughput by at "
            "least 2% and reduces median latency and CPU seconds/request by at least "
            "1%, without answer, p95, readiness, RSS, failure, or closure regression."
        ),
        "inputs": inputs,
        "prerequisites": {
            "e9a_summary_sha256": inputs["e9a_manifest_sha256"],
            "e16a_summary_sha256": inputs["e16a_manifest_sha256"],
            "e20a_summary_sha256": inputs["e20a_manifest_sha256"],
            "profile_selected_family": "ffn_gate_up",
            "profile_shares": copy.deepcopy(
                e20a["recovered_result"]["selection"]["families"]["ffn_gate_up"]
            ),
            "execution_path": validate_tensor_path(e16a),
            "kleidiai_ineligible_for_selected_weight_type": True,
            "repack_backend_converts_shared_f32_source_to_q8_k_per_matmul": True,
        },
        "runtime": runtime,
        "selected": {
            **base["selected"],
            "repository": variant["repository"],
            "revision": variant["revision"],
            "path": variant["entrypoint"],
        },
        "service": base["service"],
        "request": base["request"],
        "build": {
            "directory": "/tmp/llama.cpp-E20b-build",
            "cmake_arguments": [
                "-DCMAKE_BUILD_TYPE=Release",
                "-DGGML_CPU_KLEIDIAI=ON",
                "-DGGML_LTO=OFF",
                "-DGGML_NATIVE=ON",
                "-DLLAMA_BUILD_EXAMPLES=OFF",
                "-DLLAMA_BUILD_SERVER=ON",
                "-DLLAMA_BUILD_TESTS=OFF",
                "-DLLAMA_CURL=OFF",
                "-DLLAMA_OPENSSL=OFF",
            ],
            "required_cmake_cache_entries": [
                "CMAKE_BUILD_TYPE:STRING=Release",
                "CMAKE_GENERATOR:INTERNAL=Ninja",
                "GGML_CPU_KLEIDIAI:BOOL=ON",
                "GGML_LTO:BOOL=OFF",
                "GGML_NATIVE:BOOL=ON",
                "LLAMA_BUILD_EXAMPLES:BOOL=OFF",
                "LLAMA_BUILD_SERVER:BOOL=ON",
                "LLAMA_BUILD_TESTS:BOOL=OFF",
                "LLAMA_CURL:UNINITIALIZED=OFF",
                "LLAMA_OPENSSL:BOOL=OFF",
            ],
            "profiles": {
                "reuse_off": {
                    "pair_fusion": False,
                    "environment": {environment_name: "0", "GGML_CPU_NODE_TIMING": "0"},
                },
                "reuse_on": {
                    "pair_fusion": True,
                    "environment": {environment_name: "1", "GGML_CPU_NODE_TIMING": "0"},
                },
            },
            "single_binary_for_both_profiles": True,
            "runtime_closure_hashed": True,
        },
        "mechanism_preflight": {
            "fresh_process_per_profile": True,
            "environment": environment_name,
            "node_timing_environment": "GGML_CPU_NODE_TIMING",
            "benchmark_argv": [
                "BENCH_PATH",
                "--model",
                "MODEL_PATH",
                "--threads",
                "4",
                "--n-gpu-layers",
                "0",
                "--flash-attn",
                "on",
                "--batch-size",
                "1024",
                "--ubatch-size",
                "512",
                "--no-warmup",
                "--output",
                "jsonl",
                "--repetitions",
                "1",
                "--n-prompt",
                "512",
                "--n-gen",
                "0",
            ],
            "control_expected_separate_ffn_nodes": 52,
            "candidate_expected_fused_ffn_pairs": 26,
            "required_layers": list(range(26)),
            "required_first_projection": "gate",
            "required_second_projection": "up",
            "diagnostic_timing_not_performance_evidence": True,
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "baseline_profile": "reuse_off",
            "candidate_profile": "reuse_on",
            "repetitions_per_profile": 6,
            "fresh_server_per_cell": True,
            "order": order,
            "reverse_balanced_blocks": 3,
        },
        "acceptance": {
            **base["acceptance"],
            "minimum_throughput_ratio": 1.02,
            "maximum_median_http_latency_ratio": 0.99,
            "maximum_p95_http_latency_ratio": 1.02,
            "maximum_cpu_seconds_per_request_ratio": 0.99,
            "maximum_ready_time_ratio": 1.10,
            "maximum_candidate_rss_ratio": 1.02,
            "maximum_runtime_closure_ratio": 1.0,
            "maximum_candidate_throughput_cv": 0.02,
        },
        "decision": {
            "candidate_must_pass_every_gate": True,
            "quality_evaluated_before_performance_promotion": True,
            "pair_fusion_default_remains_off": True,
            "automatic_product_promotion_allowed": False,
            "separate_clean_integration_required_after_win": True,
            "weighted_score_used": False,
        },
        "negative_result_rule": (
            "Retain any patch, build, source-path, mechanism-count, output, quality, "
            "failure, speed, latency, CPU, p95, readiness, RSS, closure, or scheduler-"
            "dispersion failure without changing the pair predicate, toggle, workload, "
            "order, repetitions, or gates."
        ),
        "claim_boundary": (
            "E20b can establish only the effect of reusing one repack-backend Q8_K "
            "activation conversion across adjacent Q4_K FFN gate/up projections for "
            "the exact patched b10216 OpenSSL-off Q4_K_M service and 30-task workload "
            "on one four-vCPU GitHub Arm64 runner. The preflight software timer is "
            "diagnostic only. No other-model, other-backend, long-context, PMU, cache-"
            "counter, energy, local-device, fleet, or cost claim is allowed."
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
