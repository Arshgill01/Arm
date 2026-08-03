#!/usr/bin/env python3
"""Freeze bounded CPU graph-node timing before observing any native trace."""

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
    "e9a_contract": Path("experiments/e9a_contract.json"),
    "e9a_manifest": Path("results/manifests/e9a-30764802071.json"),
    "model_contract": Path("experiments/e18a_successor_contract.json"),
    "tasks": Path("experiments/e3_tasks.json"),
    "reference_manifest": Path("results/manifests/e3f-30656151957.json"),
    "probe": Path("experiments/e5b_inference_probe.py"),
    "feature_patch": Path("patches/llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch"),
    "q8_patch": Path("patches/llama.cpp/0002-arm-q8-vector-narrowing-stores.patch"),
    "reasoning_patch": Path("patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch"),
    "timing_patch": Path("patches/llama.cpp/b10216/0008-cpu-node-timing.patch"),
    "bench_cell": Path("experiments/e20a_bench_cell.sh"),
    "quality_cell": Path("experiments/e20a_quality.sh"),
    "freeze": Path("experiments/e20a_freeze.py"),
    "ingest": Path("experiments/e20a_ingest.py"),
    "test": Path("tests/test_e20a.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    e9a_contract = load_object(root / INPUT_PATHS["e9a_contract"])
    e9a = load_object(root / INPUT_PATHS["e9a_manifest"])
    model_contract = load_object(root / INPUT_PATHS["model_contract"])
    selected = model_contract["selected"]
    if (
        e9a.get("status") != "valid_final_service_win"
        or e9a_contract.get("experiment_id") != "E9a"
        or selected.get("candidate") != "ministral3_3b_q4_k_m"
        or selected.get("model_sha256") != e9a_contract["selected"]["model_sha256"]
        or selected.get("reference_correct") != 23
        or selected.get("reference_total") != 30
    ):
        raise ValueError("E20a selected-service prerequisite differs")

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)

    common = [
        "BENCH_PATH",
        "--model", "MODEL_PATH",
        "--threads", "4",
        "--n-gpu-layers", "0",
        "--flash-attn", "on",
        "--batch-size", "1024",
        "--ubatch-size", "512",
        "--no-warmup",
        "--output", "jsonl",
    ]
    cases = []
    for mode, prompt, generation in (
        ("pp512", 512, 0),
        ("pp4096", 4096, 0),
        ("tg128", 0, 128),
    ):
        for timing, repetitions in ((False, 3), (True, 1)):
            suffix = "timed" if timing else "control"
            cases.append(
                {
                    "name": f"{mode}_{suffix}",
                    "mode": mode,
                    "n_prompt": prompt,
                    "n_generation": generation,
                    "node_timing": timing,
                    "repetitions": repetitions,
                    "argv": [
                        *common,
                        "--repetitions", str(repetitions),
                        "--n-prompt", str(prompt),
                        "--n-gen", str(generation),
                    ],
                }
            )

    service = dict(e9a_contract["profiles"]["e7c_final"]["service"])
    service["client_concurrency"] = 1
    request = dict(e9a_contract["request"])
    request["timeout_seconds"] = 180.0
    acceptance = dict(model_contract["acceptance"])
    patches = [
        {
            "name": name,
            "path": inputs[f"{name}_path"],
            "sha256": inputs[f"{name}_sha256"],
        }
        for name in ("feature_patch", "q8_patch", "reasoning_patch", "timing_patch")
    ]
    return {
        "schema_version": 1,
        "experiment_id": "E20a",
        "title": "Bounded software graph-node timing for fusion target selection",
        "state": (
            "frozen before observing any native node-timing trace, op share, "
            "shared-activation set, or fusion-family selection"
        ),
        "hypothesis": (
            "The exact selected prefill path contains a mechanically identifiable "
            "Q/K/V or FFN gate/up projection family with shared activations and at "
            "least ten percent of software-timed graph-node duration in both frozen "
            "prompt shapes, authorizing one focused fusion feasibility successor."
        ),
        "inputs": inputs,
        "selected": selected,
        "source": {
            "repository": "https://github.com/ggml-org/llama.cpp.git",
            "commit": "876a4321163249c43ca4e986818fab5ab081f282",
            "tag": "b10216",
            "patches": patches,
            "source_diff_sha256": "b462dd287ae0cad5ad49d4b444c635293634ad0879a9f1b4cc5dc6a066a9d7ca",
            "changed_files": [
                "common/reasoning-budget.cpp",
                "ggml/src/ggml-cpu/CMakeLists.txt",
                "ggml/src/ggml-cpu/arch/arm/quants.c",
                "ggml/src/ggml-cpu/ggml-cpu.c",
                "tests/test-reasoning-budget.cpp",
            ],
            "timing_environment": "GGML_CPU_NODE_TIMING=1",
        },
        "build": {
            "cmake_arguments": [
                "-DCMAKE_BUILD_TYPE=Release",
                "-DGGML_CPU_KLEIDIAI=ON",
                "-DGGML_LTO=OFF",
                "-DGGML_NATIVE=ON",
                "-DLLAMA_BUILD_EXAMPLES=ON",
                "-DLLAMA_BUILD_SERVER=ON",
                "-DLLAMA_BUILD_TESTS=OFF",
                "-DLLAMA_CURL=OFF",
                "-DLLAMA_OPENSSL=OFF",
            ],
            "targets": ["llama-server", "llama-bench"],
            "forbidden_dynamic_dependency_basenames": ["libcrypto.so.3", "libssl.so.3"],
        },
        "service": service,
        "request": request,
        "acceptance": {
            **acceptance,
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "minimum_positive_timing_records_per_timed_case": 100,
            "control_timing_records": 0,
            "minimum_prefill_group_share": 0.10,
            "minimum_shared_activation_layers_per_prefill_mode": 20,
        },
        "benchmark": {
            "runner": "ubuntu-24.04-arm",
            "required_architecture": "aarch64",
            "cases": cases,
            "control_results_are_performance_descriptors": True,
            "timed_results_are_not_performance_claims": True,
            "selection_modes": ["pp512", "pp4096"],
            "diagnostic_only_mode": "tg128",
        },
        "selection": {
            "eligible_families": ["attention_qkv", "ffn_gate_up"],
            "rule": (
                "A family is eligible only if every frozen prefill mode has at "
                "least 20 distinct layer/shared-activation sets containing at least "
                "two family roles and the family's summed elapsed share is at least "
                "0.10. Select the eligible family with the largest geometric mean "
                "prefill share; break an exact tie lexicographically."
            ),
            "no_eligible_family": "stop before source optimization and retain the profile",
            "automatic_source_optimization_allowed": False,
        },
        "negative_result_rule": (
            "Retain build failure, missing or malformed timing rows, exact-answer "
            "drift, insufficient shared-activation structure, low measured share, "
            "or no eligible fusion family without changing modes, thresholds, or rule."
        ),
        "claim_boundary": (
            "E20a is software wall-clock instrumentation on one native four-vCPU "
            "GitHub Arm64 host. Timed runs include logging overhead and cannot support "
            "service-speed, PMU, cache-counter, energy, fleet, cost, or optimization-win "
            "claims. It can only select or reject one fusion family for a separately "
            "frozen source implementation and end-to-end service experiment."
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
