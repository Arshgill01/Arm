#!/usr/bin/env python3
"""Freeze the E14b selective Arm weight-repack frontier."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


INPUT_PATHS = {
    "manifest": "results/manifests/e3f-30656151957.json",
    "policy": "configs/cloud-quality.json",
    "models": "experiments/e3f_models.json",
    "runtime_contract": "experiments/e3f_contract.json",
    "tasks": "experiments/e3_tasks.json",
    "e9a_contract": "experiments/e9a_contract.json",
    "patch_1": "patches/llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch",
    "patch_2": "patches/llama.cpp/0002-arm-q8-vector-narrowing-stores.patch",
    "patch_3": "patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch",
    "selective_patch": "patches/llama.cpp/b10216/0004-selective-repack-exclusion.patch",
    "e14a_contract": "experiments/e14a_contract.json",
    "e14a_manifest": "results/manifests/e14a-30832494881.json",
    "e14a_report": "results/reports/e14a-selective-repack-instrumentation-failure.md",
    "cell_runner": "experiments/e14b_cell.sh",
    "ingest": "experiments/e14b_ingest.py",
    "freeze": "experiments/e14b_freeze.py",
}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def base_configuration(*, weight_repack: bool) -> dict[str, Any]:
    return {
        "threads": 4,
        "server_parallel_slots": 1,
        "client_concurrency": 1,
        "prompt_cache": True,
        "warmup_slot_ids": [0, 0],
        "context_per_slot": 256,
        "kv_cache_type_k": "f16",
        "kv_cache_type_v": "f16",
        "flash_attention": "auto",
        "batch_size": 64,
        "micro_batch_size": 64,
        "explicit_batch_arguments": True,
        "weight_repack": weight_repack,
    }


def attention_tensor_names() -> list[str]:
    return [
        f"blk.{layer}.{group}.weight"
        for layer in range(26)
        for group in ("attn_q", "attn_k", "attn_v", "attn_output")
    ]


def build_contract(root: Path) -> dict[str, Any]:
    e9a = load_object(root / INPUT_PATHS["e9a_contract"])
    e14a_contract = load_object(root / INPUT_PATHS["e14a_contract"])
    e14a_manifest = load_object(root / INPUT_PATHS["e14a_manifest"])
    if (
        e14a_contract.get("experiment_id") != "E14a"
        or e14a_manifest.get("status") != "invalid_incomplete_mechanism_instrumentation"
        or e14a_manifest.get("experiment_result_valid") is not False
        or e14a_manifest.get("promotion_decision_permitted") is not False
    ):
        raise ValueError("E14b predecessor is not the retained invalid E14a run")
    service = e9a["profiles"]["e7c_final"]
    attention = sorted(attention_tensor_names())
    attention_down = sorted(
        attention + [f"blk.{layer}.ffn_down.weight" for layer in range(26)]
    )
    common = base_configuration(weight_repack=True)
    configurations = {
        "full_repack": {
            **common,
            "exclusion_regex": None,
            "expected_excluded_tensors": [],
        },
        "attention_raw": {
            **common,
            "exclusion_regex": (
                r"^blk\.[0-9]+\.(attn_q|attn_k|attn_v|attn_output)\.weight$"
            ),
            "expected_excluded_tensors": attention,
        },
        "attention_down_raw": {
            **common,
            "exclusion_regex": (
                r"^blk\.[0-9]+\.(attn_q|attn_k|attn_v|attn_output|ffn_down)\.weight$"
            ),
            "expected_excluded_tensors": attention_down,
        },
        "no_repack": {
            **base_configuration(weight_repack=False),
            "exclusion_regex": None,
            "expected_excluded_tensors": [],
        },
    }
    return {
        "schema_version": 1,
        "experiment_id": "E14b",
        "title": "Verbosity-corrected tensor-selective Arm weight-repack frontier",
        "hypothesis": (
            "Leaving only predeclared attention or attention-plus-FFN-down tensor "
            "groups in the ordinary CPU buffer can create a non-dominated memory/"
            "throughput point between exact full-repack and no-repack endpoints."
        ),
        "scope": (
            "An instrumentation-only successor to invalid E14a. It repeats the "
            "same four-point, two-repetition native Arm64 matrix and changes only "
            "uniform server log verbosity from the default 3 to explicit 4."
        ),
        "artifact_name_prefix": "e14b-selective-repack",
        "inputs": {
            **{f"{name}_path": path for name, path in INPUT_PATHS.items()},
            **{
                f"{name}_sha256": sha256_file(root / path)
                for name, path in INPUT_PATHS.items()
            },
        },
        "selected": {
            "candidate": "ministral3_3b_q4_k_m",
            "reference_correct": 23,
            "reference_total": 30,
            "reference_accuracy": 23 / 30,
            "model_sha256": "fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4",
            "model_size_bytes": 2146497824,
            "llama_cpp_commit": service["source"]["commit"],
            "llama_cpp_tag": service["source"]["tag"],
        },
        "predecessor": {
            "experiment_id": "E14a",
            "run_id": e14a_manifest["github"]["run_id"],
            "manifest_sha256": sha256_file(root / INPUT_PATHS["e14a_manifest"]),
            "status": e14a_manifest["status"],
            "result_observed_during_freeze": True,
            "only_permitted_change": "append --log-verbosity 4 to every recipe",
            "e14a_remains_invalid": True,
        },
        "source": {
            "repository": service["source"]["repository"],
            "commit": service["source"]["commit"],
            "tag": service["source"]["tag"],
            "patches": [
                {
                    "path": INPUT_PATHS[name],
                    "sha256": sha256_file(root / INPUT_PATHS[name]),
                }
                for name in ("patch_1", "patch_2", "patch_3", "selective_patch")
            ],
            "aggregate_diff_sha256": "d8a74bc63b660d5e80c31c3dbdd9705eb68313020cb55035bbaf20a4b64c6a64",
            "changed_files": [
                "common/reasoning-budget.cpp",
                "ggml/src/ggml-cpu/CMakeLists.txt",
                "ggml/src/ggml-cpu/arch/arm/quants.c",
                "ggml/src/ggml-cpu/repack.cpp",
                "tests/test-reasoning-budget.cpp",
            ],
        },
        "build": service["build"],
        "mechanism": {
            "proof_log_verbosity": 4,
            "environment_variable": "GGML_CPU_REPACK_EXCLUDE",
            "separator": ";",
            "matching": "std::regex_search against exact tensor name",
            "fail_closed_invalid_or_empty_pattern": True,
            "default_behavior_unchanged_when_unset": True,
            "buffer_patterns": {
                "mapped": "CPU_Mapped model buffer size",
                "repack": "CPU_REPACK model buffer size",
                "excluded": "ggml_repack_tensor_is_excluded: excluded tensor ",
            },
        },
        "request": {
            "instruction_role": "system",
            "chat_template_mode": "model_jinja_system_instruction",
            "temperature": 0.0,
            "seed": 424242,
            "max_output_tokens": 8,
            "timeout_seconds": 30.0,
            "warmup_task_ids": ["arithmetic-02", "logic-01"],
            "measured_tasks": 30,
        },
        "execution": {
            "configurations": configurations,
            "baseline_configuration": "full_repack",
            "no_repack_configuration": "no_repack",
            "selective_configurations": ["attention_raw", "attention_down_raw"],
            "repetitions_per_configuration": 2,
            "fresh_server_per_cell": True,
            "order": [
                {"configuration": "full_repack", "repetition": 1},
                {"configuration": "attention_raw", "repetition": 1},
                {"configuration": "attention_down_raw", "repetition": 1},
                {"configuration": "no_repack", "repetition": 1},
                {"configuration": "no_repack", "repetition": 2},
                {"configuration": "attention_down_raw", "repetition": 2},
                {"configuration": "attention_raw", "repetition": 2},
                {"configuration": "full_repack", "repetition": 2},
            ],
            "total_fresh_processes": 8,
            "total_measured_requests": 240,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "http_status": 200,
            "termination_reason": "stop",
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "minimum_candidate_cached_tokens_per_request": 1,
            "maximum_throughput_coefficient_of_variation": 0.05,
            "minimum_selective_throughput_retention_ratio": 0.80,
            "minimum_selective_extra_rss_saved_fraction": 0.40,
            "maximum_selective_p95_http_latency_ratio": 1.25,
            "minimum_non_dominated_points": 3,
            "maximum_ready_ms": 15000.0,
            "maximum_process_rss_kib": 8388608,
            "accepted_server_shell_exit_statuses": [0, 130],
            "weighted_score_used": False,
        },
        "measurement_boundary": (
            "Linux process CPU counters are sampled after two warmups and only "
            "around the 30 measured requests. Model load, selective repacking, "
            "readiness, warmups, client CPU, metrics, and shutdown are excluded. "
            "CPU time is not energy or power."
        ),
        "negative_result_rule": (
            "Retain dominated points, quality drift, mechanism mismatches, noise, "
            "or a missed 80%-throughput/40%-extra-memory target without changing "
            "groups, order, repetitions, or thresholds."
        ),
        "successor_integrity": {
            "configurations_equal_e14a": configurations
            == e14a_contract["execution"]["configurations"],
            "order_equal_e14a": e14a_contract["execution"]["order"]
            == [
                {"configuration": "full_repack", "repetition": 1},
                {"configuration": "attention_raw", "repetition": 1},
                {"configuration": "attention_down_raw", "repetition": 1},
                {"configuration": "no_repack", "repetition": 1},
                {"configuration": "no_repack", "repetition": 2},
                {"configuration": "attention_down_raw", "repetition": 2},
                {"configuration": "attention_raw", "repetition": 2},
                {"configuration": "full_repack", "repetition": 2},
            ],
            "request_equal_e14a": e14a_contract["request"]
            == {
                "instruction_role": "system",
                "chat_template_mode": "model_jinja_system_instruction",
                "temperature": 0.0,
                "seed": 424242,
                "max_output_tokens": 8,
                "timeout_seconds": 30.0,
                "warmup_task_ids": ["arithmetic-02", "logic-01"],
                "measured_tasks": 30,
            },
            "acceptance_equal_e14a": e14a_contract["acceptance"]
            == {
                "required_architecture": "aarch64",
                "http_status": 200,
                "termination_reason": "stop",
                "request_failures": 0,
                "reference_prediction_mismatches": 0,
                "minimum_candidate_cached_tokens_per_request": 1,
                "maximum_throughput_coefficient_of_variation": 0.05,
                "minimum_selective_throughput_retention_ratio": 0.80,
                "minimum_selective_extra_rss_saved_fraction": 0.40,
                "maximum_selective_p95_http_latency_ratio": 1.25,
                "minimum_non_dominated_points": 3,
                "maximum_ready_ms": 15000.0,
                "maximum_process_rss_kib": 8388608,
                "accepted_server_shell_exit_statuses": [0, 130],
                "weighted_score_used": False,
            },
            "results_used_to_change_groups_order_or_gates": False,
        },
        "claim_boundary": (
            "E14b can support a tensor-selective repack tier only for the exact "
            "Q4_K_M model, exact E7c service plus the retained experimental hook, "
            "30-task cached one-slot workload, and native GitHub Arm64 host. It "
            "makes no energy, PMU, local-device, fleet, concurrency, other-model, "
            "or other-runtime claim and does not publish an upstream patch."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root)
    args.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
