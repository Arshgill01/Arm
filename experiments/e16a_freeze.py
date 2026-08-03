#!/usr/bin/env python3
"""Freeze the E16a persistent Arm-repack sidecar feasibility probe."""

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
    "dump_patch": "patches/llama.cpp/b10216/0006-repack-sidecar-feasibility-dump.patch",
    "sidecar_builder": "experiments/e16a_sidecar.py",
    "cell_runner": "experiments/e16a_cell.sh",
    "ingest": "experiments/e16a_ingest.py",
    "freeze": "experiments/e16a_freeze.py",
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
    service = e9a["profiles"]["e7c_final"]
    return {
        "schema_version": 1,
        "experiment_id": "E16a",
        "title": "Persistent Arm-repack deterministic sidecar feasibility",
        "hypothesis": (
            "The exact native Arm packed-weight arena is deterministic and "
            "position-independent for a model hash, source diff, CPU feature set, "
            "and kernel-layout inventory, so it can be serialized into a verified "
            "sidecar before implementing a mapped loader."
        ),
        "scope": (
            "Two fresh native Arm64 E7c-derived processes dump every packed tensor, "
            "run the exact 30-task quality workload, build and verify a fixed-format "
            "sidecar, and compare all metadata, tensor hashes, and container bytes. "
            "This is a feasibility gate, not a startup, RSS, PSS, or throughput claim."
        ),
        "artifact_name_prefix": "e16a-repack-sidecar-feasibility",
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
                for name in ("patch_1", "patch_2", "patch_3", "dump_patch")
            ],
            "aggregate_diff_sha256": "4c9a3d6f148894bd78609cd11cfc990275391bda8f457b0d458d5730c047bd89",
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
            "environment_variable": "GGML_CPU_REPACK_DUMP_DIR",
            "default_behavior_unchanged_when_unset": True,
            "dump_format_version": 1,
            "sidecar_format_version": 1,
            "sidecar_magic_ascii": "P64ARMPACKV1",
            "sidecar_data_offset_bytes": 1048576,
            "arena_layout": "original packed-buffer-relative tensor offsets",
            "tensor_binding": [
                "name",
                "source type",
                "repack parameter type",
                "dimensions",
                "bytes",
                "buffer offset",
                "column group",
                "interleave",
                "sha256",
            ],
            "sidecar_binding": [
                "source GGUF SHA-256",
                "llama.cpp commit",
                "aggregate source diff SHA-256",
                "architecture and common CPU feature mask",
                "SVE vector length",
                "dump and sidecar format versions",
                "complete tensor metadata and hashes",
            ],
            "absolute_buffer_base_excluded_from_sidecar": True,
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
            "repetitions": 2,
            "fresh_server_per_repetition": True,
            "order": [1, 2],
            "total_fresh_processes": 2,
            "total_measured_requests": 60,
            "build_sidecar_after_each_process": True,
            "verify_each_complete_sidecar_before_comparison": True,
            "delete_only_generated_raw_tensor_bins_and_sidecars_after_hashing": True,
            "retain_indexes_inventories_runtime_addresses_and_quality": True,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "required_common_cpu_features": ["asimd", "asimddp"],
            "minimum_tensor_count": 100,
            "minimum_packed_buffer_coverage_fraction": 0.99,
            "identical_cpu_identity_between_repetitions": True,
            "identical_tensor_metadata_between_repetitions": True,
            "identical_tensor_sha256_between_repetitions": True,
            "identical_complete_sidecar_sha256_between_repetitions": True,
            "sidecar_verification_status": "valid_sidecar",
            "http_status": 200,
            "termination_reason": "stop",
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "correct_per_repetition": 23,
            "predictions_stable_between_repetitions": True,
            "accepted_server_shell_exit_statuses": [0, 130],
            "generated_binary_cleanup_required": True,
            "post_result_gate_change_permitted": False,
        },
        "promotion_rule": (
            "Only if every feasibility and quality gate passes may a separately "
            "frozen loader experiment mmap this format and measure startup, RSS/PSS, "
            "and service throughput against normal runtime repacking."
        ),
        "negative_result_rule": (
            "Retain any metadata, tensor, sidecar, architecture, quality, or cleanup "
            "failure without editing the sidecar format or acceptance gates. Do not "
            "start a mapped loader from a failed preflight."
        ),
        "claim_boundary": (
            "E16a can establish only deterministic serialization feasibility for the "
            "exact Q4_K_M model, b10216 four-patch diff, GitHub native Arm64 feature "
            "identity, and packed layout. It cannot claim a usable loader, shared "
            "mapping, memory saving, startup gain, throughput gain, energy result, or "
            "portability to a different CPU identity."
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
