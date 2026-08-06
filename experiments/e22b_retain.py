#!/usr/bin/env python3
"""Bind the independently replayed E22b curve to its sealed Axion bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e22a_freeze import sha256_file
    from experiments.e22b_ingest import ingest
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e22a_freeze import sha256_file
    from e22b_ingest import ingest


INSTANCE_NAME = "pareto64-axion-e22-20260806"
INSTANCE_ID = "5558962151178759364"
HEAD_SHA = "a0c539fced9c054f3f3148d90b5f0efbcc3e2e7d"
CONTRACT_SHA256 = "8f26bc713a817636b97aaa772c3926977d5d5cabaed9b7c4f8c66cc2d7849fae"
SUMMARY_SHA256 = "06d921ad37bfb19969ab4a5a564937f3176fe556d25f28f0df61fd30bd6e09c9"
INVENTORY_SHA256 = "b9ba8cb790c7164ea2e858f8f01b95100197cedfc3dde7bb2351b59118d06eee"
ARCHIVE_NAME = "e22b-evidence-a0c539f-v2.tar.gz"
ARCHIVE_SHA256 = "a415ac6ad262911a98b38c6fe136bd4dfbe74d2e815531a80d2037d884af5ec0"
ARCHIVE_SIZE_BYTES = 10_255_094
INVENTORY_FILES = 628
REGULAR_FILES = 629
SYMLINKS = {
    "runtime/bin/libggml-base.so.0": "libggml-base.so.0.18.0",
    "runtime/bin/libggml-cpu.so.0": "libggml-cpu.so.0.18.0",
    "runtime/bin/libggml.so.0": "libggml.so.0.18.0",
    "runtime/bin/libllama-common.so.0": "libllama-common.so.0.0.10216",
    "runtime/bin/libllama.so.0": "libllama.so.0.0.10216",
    "runtime/bin/libmtmd.so.0": "libmtmd.so.0.0.10216",
}


def vmstat_value(path: Path, key: str) -> int:
    values = [
        int(line.split()[1])
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.startswith(f"{key} ")
    ]
    if len(values) != 1:
        raise ValueError(f"E22b {path.name} has an ambiguous {key}")
    return values[0]


def validate_inventory(evidence: Path) -> dict[str, Any]:
    inventory_path = evidence / "file-inventory-sha256.txt"
    entries: dict[str, str] = {}
    for line in inventory_path.read_text(encoding="utf-8").splitlines():
        digest, separator, recorded = line.partition("  ")
        if not separator or len(digest) != 64 or not recorded.startswith("./"):
            raise ValueError("E22b inventory line differs")
        relative = recorded[2:]
        relative_path = Path(relative)
        if (
            not relative
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative in entries
        ):
            raise ValueError("E22b inventory path is unsafe or duplicate")
        local = evidence / relative_path
        if not local.is_file() or local.is_symlink() or sha256_file(local) != digest:
            raise ValueError(f"E22b inventory differs for {relative}")
        entries[relative] = digest

    actual = {
        item.relative_to(evidence).as_posix()
        for item in evidence.rglob("*")
        if item.is_file()
        and not item.is_symlink()
        and item != inventory_path
    }
    links = {
        item.relative_to(evidence).as_posix(): item.readlink().as_posix()
        for item in evidence.rglob("*")
        if item.is_symlink()
    }
    required = {
        "contract.json",
        "summary.json",
        "summary-independent.json",
        "campaign-status.json",
        "product/sidecar-receipt.json",
        "product/sidecar-verification.json",
        "runtime/bin/llama-server",
        "failed-attempt-01/failed-attempt-status.json",
        "preflight-smoke-01/cells/01-normal-w1/probe.json",
        "preflight-smoke-02/cells/01-normal-w1/probe.json",
        *{
            f"cells/{position:02d}-{mode}-w{workers}/cell-status.json"
            for position, mode, workers in (
                (1, "normal", 1),
                (2, "shared", 1),
                (3, "shared", 2),
                (4, "normal", 2),
                (5, "normal", 4),
                (6, "shared", 4),
                (7, "shared", 5),
                (8, "normal", 5),
                (9, "normal", 6),
                (10, "shared", 6),
                (11, "shared", 8),
                (12, "normal", 8),
            )
        },
    }
    generated = [
        relative
        for relative in actual
        if relative.endswith((".gguf", "weights.sidecar"))
        or "raw-tensors" in Path(relative).parts
    ]
    if (
        len(entries) != INVENTORY_FILES
        or entries.keys() != actual
        or not required.issubset(entries)
        or len(actual) + 1 != REGULAR_FILES
        or links != SYMLINKS
        or generated
        or sha256_file(inventory_path) != INVENTORY_SHA256
        or any(
            sha256_file(evidence / link) != sha256_file((evidence / link).resolve())
            for link in SYMLINKS
        )
    ):
        raise ValueError("E22b retained file set differs")
    return {
        "hashed_regular_files": len(entries),
        "regular_files_including_root_inventory": len(actual) + 1,
        "runtime_symlinks": len(links),
        "sha256": sha256_file(inventory_path),
        "all_retained_file_hashes_verified": True,
        "generated_model_sidecar_or_raw_tensors_retained": False,
    }


def retain(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    replay = ingest(evidence, contract_path, root)
    replay_bytes = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    workflow_summary = evidence / "summary.json"
    if replay_bytes != workflow_summary.read_bytes():
        raise ValueError("E22b independent replay differs")

    cells = {
        (cell["mode"], cell["worker_count"]): cell for cell in replay["cells"]
    }
    normal_eight = cells[("normal", 8)]
    failed = evidence / "cells/12-normal-w8"
    oom_before = vmstat_value(failed / "host-state-before.txt", "oom_kill")
    oom_after = vmstat_value(failed / "host-state-after.txt", "oom_kill")
    swap_in_before = vmstat_value(failed / "host-state-before.txt", "pswpin")
    swap_in_after = vmstat_value(failed / "host-state-after.txt", "pswpin")
    swap_out_before = vmstat_value(failed / "host-state-before.txt", "pswpout")
    swap_out_after = vmstat_value(failed / "host-state-after.txt", "pswpout")
    if (
        replay.get("status") != "valid_fixed_memory_curve_promoted"
        or replay.get("decision")
        != "freeze_clean_repeated_maximum_density_comparison"
        or replay.get("failed_advance_gates") != []
        or not all(replay.get("validity_gates", {}).values())
        or not all(replay.get("advance_gates", {}).values())
        or replay.get("repository_commit") != HEAD_SHA
        or replay.get("contract_sha256") != CONTRACT_SHA256
        or replay.get("host", {}).get("instance_id") != INSTANCE_ID
        or replay.get("maximum_admitted", {}).get("normal", {}).get("worker_count")
        != 6
        or replay.get("maximum_admitted", {}).get("shared", {}).get("worker_count")
        != 8
        or replay.get("fixed_memory_aggregate_throughput_ratio")
        != 1.3544872858658519
        or normal_eight.get("failure_class") != "fixed_memory_admission_failure"
        or normal_eight.get("resource_boundary_evidence") is not True
        or oom_after - oom_before != 1
        or swap_in_after != swap_in_before
        or swap_out_after != swap_out_before
        or sha256_file(workflow_summary) != SUMMARY_SHA256
        or sha256_file(evidence / "contract.json") != CONTRACT_SHA256
    ):
        raise ValueError("E22b retained identity, boundary, or outcome differs")

    inventory = validate_inventory(evidence)
    return {
        **replay,
        "retention_validation": {
            "independent_replays": 3,
            "independent_replay_byte_identical": True,
            "workflow_summary_sha256": sha256_file(workflow_summary),
            "workflow_inventory": inventory,
            "archive_name": ARCHIVE_NAME,
            "archive_sha256": ARCHIVE_SHA256,
            "archive_size_bytes": ARCHIVE_SIZE_BYTES,
            "artifact_identity_bound": True,
            "native_measurements_added": 0,
            "source_contract_or_gates_changed": False,
        },
        "normal_eight_resource_boundary": {
            "status": "retained_native_oom_admission_boundary",
            "oom_kill_before": oom_before,
            "oom_kill_after": oom_after,
            "oom_kill_delta": oom_after - oom_before,
            "swap_in_delta": swap_in_after - swap_in_before,
            "swap_out_delta": swap_out_after - swap_out_before,
            "worker_exit_signal": 9,
        },
        "cloud": {
            "instance_name": INSTANCE_NAME,
            "instance_id": INSTANCE_ID,
            "project_redacted_from_public_manifest": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(args.evidence_dir, args.contract, args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "failed_advance_gates": result["failed_advance_gates"],
                "status": result["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
