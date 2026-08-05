#!/usr/bin/env python3
"""Freeze the clean-checkout E16d persistent-sidecar product lifecycle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e16d_lifecycle_fixture import run_synthetic_replay
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e16d_lifecycle_fixture import run_synthetic_replay


INPUT_PATHS = {
    "e16c_contract": "experiments/e16c_contract.json",
    "e16c_manifest": "results/manifests/e16c-30851609576.json",
    "e16c_report": "results/reports/e16c-shared-repack-arena.md",
    "e16b_manifest": "results/manifests/e16b-30842925537.json",
    "model_registry": "experiments/e3f_models.json",
    "tasks": "experiments/e3_tasks.json",
    "reference_manifest": "results/manifests/e3f-30656151957.json",
    "product_sidecar": "pareto64/sidecar.py",
    "product_cli": "pareto64/cli.py",
    "ingest": "experiments/e16d_lifecycle_ingest.py",
    "synthetic_fixture": "experiments/e16d_lifecycle_fixture.py",
    "freeze": "experiments/e16d_lifecycle_freeze.py",
    "sidecar_tests": "tests/test_pareto64_sidecar.py",
    "cli_tests": "tests/test_pareto64_cli.py",
    "lifecycle_tests": "tests/test_e16d_lifecycle.py",
}


def build_contract(root: Path) -> dict[str, Any]:
    e16c_contract_path = root / INPUT_PATHS["e16c_contract"]
    e16c_manifest_path = root / INPUT_PATHS["e16c_manifest"]
    e16b_manifest_path = root / INPUT_PATHS["e16b_manifest"]
    e16c_contract = load_object(e16c_contract_path)
    e16c = load_object(e16c_manifest_path)
    e16b = load_object(e16b_manifest_path)
    if (
        e16c_contract.get("experiment_id") != "E16c"
        or e16c.get("status") != "valid_shared_sidecar_workers_promoted"
        or e16c.get("promoted") is not True
        or not all(e16c.get("gates", {}).values())
        or e16c.get("contract_sha256") != sha256_file(e16c_contract_path)
        or e16b.get("status") != "valid_sidecar_loader_promoted"
        or not all(e16b.get("gates", {}).values())
    ):
        raise ValueError("E16d lacks promoted E16b/E16c prerequisites")
    index = e16c["construction"]["sidecar_index"]
    closure = e16c["source_build"]["runtime_closure"]
    server = next(
        item
        for item in closure["files"]
        if item["relative_path"] == closure["server_relative_path"]
    )
    return {
        "schema_version": 1,
        "experiment_id": "E16d",
        "title": "Clean-checkout persistent Arm-prepacked sidecar lifecycle",
        "state": ("frozen_after_byte_stable_synthetic_replay_before_native_lifecycle"),
        "inputs": {
            name: {"path": path, "sha256": sha256_file(root / path)}
            for name, path in sorted(INPUT_PATHS.items())
        },
        "prerequisite": {
            "e16c_contract_path": INPUT_PATHS["e16c_contract"],
            "e16c_contract_sha256": sha256_file(e16c_contract_path),
            "e16c_manifest_path": INPUT_PATHS["e16c_manifest"],
            "e16c_manifest_sha256": sha256_file(e16c_manifest_path),
            "e16c_artifact_run_id": "30851609576",
            "e16c_artifact_id": "8871236545",
            "e16c_artifact_name": "e16c-shared-repack-arena-30851609576-1",
            "e16c_artifact_digest": (
                "sha256:e29d3a4440dafd42364fb586f9d5f8adb2c6c69b3bd312a10ffd10761312db02"
            ),
            "e16c_artifact_expires_at": "2026-11-01T20:44:53Z",
            "reuse": (
                "Download the retained E16c runtime closure; do not rebuild the "
                "already validated source or rerun its performance matrix."
            ),
        },
        "selected": e16c_contract["selected"],
        "source": e16c_contract["source"],
        "runtime": {
            "server_relative_path": closure["server_relative_path"],
            "server_sha256": server["sha256"],
            "closure_file_count": closure["file_count"],
            "closure_total_size_bytes": closure["total_size_bytes"],
            "openssl_linked": False,
        },
        "product": {
            "commands": [
                "python3 -m pareto64 sidecar-prepack",
                "python3 -m pareto64 sidecar-verify",
                "python3 -m pareto64 sidecar-launch --workers 2",
                "python3 -m pareto64 sidecar-cleanup",
            ],
            "lifecycle": (
                "one-time prepack -> independent full verify -> two-worker "
                "read-only shared launch -> receipt-bound cleanup"
            ),
            "fresh_checkout_required": True,
            "sidecar_and_index_read_only": True,
            "receipt_bound_cleanup": True,
        },
        "workload": {
            "tasks": 30,
            "workers": 2,
            "requests": 60,
            "reference_score_per_worker": "23/30",
            "maximum_output_tokens": 8,
            "seed": 424242,
            "temperature": 0.0,
            "client_concurrency_per_worker": 1,
            "simultaneous_measurement_barrier": True,
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "required_architecture": "aarch64",
            "fresh_checkout": True,
            "source_runtime": "retained exact E16c artifact",
            "model_download": "exact pinned Hugging Face revision",
            "sidecar_retained_during_launch": True,
            "large_model_raw_dump_and_sidecar_excluded_from_artifact": True,
            "metadata_logs_receipt_and_raw_quality_retained": True,
        },
        "acceptance": {
            "tensor_count": index["header"]["tensor_count"],
            "arena_size_bytes": index["header"]["arena_size_bytes"],
            "sidecar_size_bytes": index["sidecar_size_bytes"],
            "data_offset_bytes": index["header"]["data_offset"],
            "tasks_per_worker": 30,
            "correct_per_worker": 23,
            "worker_ports": [18081, 18082],
            "worker_exit_statuses": [0, -2, 130],
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "worker_answer_mismatches": 0,
            "required_mapping_permissions": "r--s",
            "full_verification_before_each_worker": True,
            "raw_tensor_cleanup_required": True,
            "final_sidecar_cleanup_required": True,
        },
        "readiness": {
            "mechanism_unit": {
                "status": "passed",
                "command": (
                    "python3 -m unittest tests.test_pareto64_sidecar "
                    "tests.test_pareto64_cli tests.test_pareto64_runtime"
                ),
                "tests": 30,
            },
            "synthetic_replay": {
                "status": "passed",
                "independent_replays": 2,
                "byte_stable": True,
                "complete_lifecycle_gates": 14,
            },
            "native_preflight": {
                "status": "this bounded run is the product lifecycle preflight",
                "control_cells": 0,
                "candidate_lifecycles": 1,
                "performance_matrix_authorized": False,
            },
            "affected_end_to_end_share": (
                "Not used for a new speed claim. E16b bounds same-job warm "
                "readiness; E16c bounds two-worker summed PSS."
            ),
            "optimistic_amdahl_ceiling": (
                "Not applicable: this run validates deployment lifecycle rather "
                "than estimating another performance mechanism."
            ),
            "minimum_product_changing_result": (
                "All four clean-checkout commands must pass with exact quality, "
                "read-only same-inode sharing, corruption-bound verification, "
                "recorded construction/storage cost, and safe cleanup."
            ),
            "claim_unlocked": (
                "The existing E16 mechanism is reproducibly deployable through "
                "the Pareto64 product CLI on its exact native identity."
            ),
            "budget": {
                "maximum_runtime_minutes": 30,
                "maximum_generated_storage_bytes": 8589934592,
                "expected_peak_large_bytes": (
                    e16c_contract["selected"]["model_size_bytes"]
                    + index["header"]["arena_size_bytes"]
                    + index["sidecar_size_bytes"]
                ),
                "artifact_excludes_large_generated_files": True,
            },
            "decision": "single_native_lifecycle_allowed",
        },
        "negative_result_rule": (
            "Retain any failure without weakening identity, quality, mapping, "
            "cleanup, storage, or boundary gates. Do not infer performance from "
            "this lifecycle validation."
        ),
        "claim_boundary": (
            "A valid E16d result establishes only that a clean Pareto64 checkout "
            "can prepack, fully verify, launch two exact E7c Q4_K_M workers on one "
            "read-only identity-bound sidecar, preserve the 23/30 reference map, "
            "record construction/storage cost, and clean up by verified receipt "
            "on the exact native GitHub Arm64 host. E16b remains the same-job warm "
            "readiness evidence and E16c remains the two-worker summed-PSS evidence. "
            "E16d makes no cold-start, new throughput, per-process RSS, energy, PMU, "
            "Mac, other CPU/model, fleet, or cost claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--synthetic-output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root)
    summary, replay = run_synthetic_replay(contract, args.root)
    if (
        summary.get("status") != "valid_product_sidecar_lifecycle"
        or not all(summary.get("gates", {}).values())
        or not replay.get("byte_stable")
        or replay.get("complete_gates") != 14
    ):
        raise ValueError("E16d complete synthetic replay differs")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.synthetic_output.parent.mkdir(parents=True, exist_ok=True)
    args.synthetic_output.write_text(
        json.dumps({"summary": summary, "replay": replay}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(replay, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
