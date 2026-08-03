#!/usr/bin/env python3
"""Freeze the E16b fail-closed read-only repack-sidecar loader comparison."""

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
    "e16a_result": "results/manifests/e16a-30837796757.json",
    "patch_1": "patches/llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch",
    "patch_2": "patches/llama.cpp/0002-arm-q8-vector-narrowing-stores.patch",
    "patch_3": "patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch",
    "dump_patch": "patches/llama.cpp/b10216/0006-repack-sidecar-feasibility-dump.patch",
    "loader_patch": "patches/llama.cpp/b10216/0007-repack-sidecar-readonly-loader.patch",
    "sidecar_builder": "experiments/e16a_sidecar.py",
    "constructor": "experiments/e16b_construct.sh",
    "cell_runner": "experiments/e16b_cell.sh",
    "ingest": "experiments/e16b_ingest.py",
    "freeze": "experiments/e16b_freeze.py",
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


def build_contract(root: Path) -> dict[str, Any]:
    e9a = load_object(root / INPUT_PATHS["e9a_contract"])
    e16a = load_object(root / INPUT_PATHS["e16a_result"])
    if (
        e16a.get("status") != "valid_loader_feasibility"
        or e16a.get("loader_successor_authorized") is not True
    ):
        raise ValueError("retained E16a result does not authorize E16b")
    service = e9a["profiles"]["e7c_final"]
    order = [
        {"configuration": "normal_repack", "repetition": 1},
        {"configuration": "sidecar_loader", "repetition": 1},
        {"configuration": "sidecar_loader", "repetition": 2},
        {"configuration": "normal_repack", "repetition": 2},
        {"configuration": "sidecar_loader", "repetition": 3},
        {"configuration": "normal_repack", "repetition": 3},
        {"configuration": "normal_repack", "repetition": 4},
        {"configuration": "sidecar_loader", "repetition": 4},
    ]
    return {
        "schema_version": 1,
        "experiment_id": "E16b",
        "title": "Fail-closed read-only Arm repack-sidecar loader comparison",
        "hypothesis": (
            "Mapping the E16a-validated packed arena read-only can eliminate runtime "
            "weight repacking and its anonymous copy while preserving the exact E7c "
            "service output and steady-state performance."
        ),
        "scope": (
            "Build one provenance-bound sidecar, reject a deliberately mismatched "
            "identity before readiness, then compare normal repacking with the exact "
            "read-only sidecar loader in eight reverse-balanced fresh native Arm64 "
            "processes and 240 measured requests."
        ),
        "artifact_name_prefix": "e16b-repack-sidecar-loader",
        "prerequisite": {
            "experiment_id": "E16a",
            "manifest_path": INPUT_PATHS["e16a_result"],
            "manifest_sha256": sha256_file(root / INPUT_PATHS["e16a_result"]),
            "required_status": "valid_loader_feasibility",
            "loader_successor_authorized": True,
        },
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
                for name in (
                    "patch_1",
                    "patch_2",
                    "patch_3",
                    "dump_patch",
                    "loader_patch",
                )
            ],
            "aggregate_diff_sha256": "48a7611bbe6e22a0303bf0b8855dbab3f718ca6d56d5a594a8ef1650f959f003",
            "changed_files": [
                "common/reasoning-budget.cpp",
                "ggml/src/ggml-cpu/CMakeLists.txt",
                "ggml/src/ggml-cpu/arch/arm/quants.c",
                "ggml/src/ggml-cpu/repack.cpp",
                "tests/test-reasoning-budget.cpp",
            ],
        },
        "build": service["build"],
        "service": {**service["service"], "client_concurrency": 1},
        "mechanism": {
            "sidecar_environment_variable": "GGML_CPU_REPACK_SIDECAR",
            "dump_environment_variable": "GGML_CPU_REPACK_DUMP_DIR",
            "default_behavior_unchanged_when_both_unset": True,
            "mapping_protection": "PROT_READ",
            "mapping_sharing": "MAP_SHARED",
            "mapped_file_offset_bytes": 1048576,
            "sidecar_data_offset_bytes": 1048576,
            "sidecar_format_version": 1,
            "dump_format_version": 1,
            "runtime_binding_fields": [
                "experiment ID",
                "source GGUF SHA-256",
                "llama.cpp commit",
                "aggregate source diff SHA-256",
                "architecture",
                "common CPU feature hash",
                "SVE vector length",
                "format versions",
                "complete tensor name/type/shape/layout inventory",
            ],
            "complete_sidecar_verification_before_each_loader_process": True,
            "source_gguf_remains_metadata_authority": True,
            "repacking_skipped_only_after_per_tensor_binding": True,
            "proof_log_verbosity": 4,
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
            "configurations": ["normal_repack", "sidecar_loader"],
            "baseline_configuration": "normal_repack",
            "loader_configuration": "sidecar_loader",
            "repetitions_per_configuration": 4,
            "order": order,
            "order_design": "ABBA followed by BAAB",
            "fresh_server_per_cell": True,
            "measured_processes": 8,
            "total_measured_requests": 240,
            "one_time_sidecar_construction_process": 1,
            "invalid_identity_preflight_process": 1,
            "total_processes_including_preflights": 10,
            "delete_generated_raw_tensors_after_sidecar_verification": True,
            "delete_sidecar_after_all_cells_and_final_verification": True,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "required_common_cpu_features": ["asimd", "asimddp"],
            "minimum_tensor_count": 100,
            "minimum_packed_buffer_coverage_fraction": 0.99,
            "maximum_ready_ms": 120000,
            "maximum_process_rss_kib": 7340032,
            "accepted_server_shell_exit_statuses": [0, 130],
            "http_status": 200,
            "termination_reason": "stop",
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "correct_per_repetition": 23,
            "stable_predictions_across_all_cells": True,
            "invalid_model_identity_must_fail_before_readiness": True,
            "loader_mapping_permissions": "r--s",
            "loader_mapping_offset_hex": "00100000",
            "maximum_throughput_coefficient_of_variation": 0.10,
            "minimum_throughput_retention_ratio": 0.97,
            "maximum_median_http_latency_ratio": 1.05,
            "maximum_p95_http_latency_ratio": 1.05,
            "maximum_cpu_seconds_per_request_ratio": 1.03,
            "maximum_peak_rss_ratio": 0.75,
            "maximum_post_workload_pss_ratio": 0.75,
            "maximum_readiness_ratio": 0.80,
            "material_benefit_rule": (
                "At least one of peak RSS, post-workload PSS, or readiness must "
                "meet its frozen ratio after all exactness and retention gates pass."
            ),
            "generated_binary_cleanup_required": True,
            "post_result_gate_change_permitted": False,
        },
        "promotion_rule": (
            "Promote the exact sidecar-loader configuration only if every identity, "
            "read-only mapping, per-tensor layout, exact-output, stability, throughput, "
            "latency, CPU, cleanup, and fail-closed gate passes and at least one frozen "
            "startup or memory benefit is material."
        ),
        "negative_result_rule": (
            "Retain any loader crash, identity/layout rejection, quality drift, unstable "
            "cell, performance regression, or absent material benefit without changing "
            "the thresholds or rebuilding the observed sidecar."
        ),
        "measurement_boundary": (
            "All comparative cells use fresh processes on one ubuntu-24.04-arm job, "
            "the exact E7c service argv, the same generated sidecar, and reverse-balanced "
            "order. Linux page cache is neither flushed nor claimed cold; readiness is "
            "same-job process startup under the observed cache state. Sidecar construction "
            "cost is measured separately and excluded from steady-state request metrics."
        ),
        "claim_boundary": (
            "E16b may claim only the observed single-process Neoverse N2 identity-bound "
            "read-only loader result. It cannot claim cold-storage startup, multi-process "
            "physical sharing, portability to other CPUs or source/model hashes, energy, "
            "or amortized construction economics without separate experiments."
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
