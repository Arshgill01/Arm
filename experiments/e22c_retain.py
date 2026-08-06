#!/usr/bin/env python3
"""Bind the independently replayed E22c result to its sealed Axion bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e22a_freeze import sha256_file
    from experiments.e22c_ingest import ingest
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e22a_freeze import sha256_file
    from e22c_ingest import ingest


INSTANCE_ID = "5558962151178759364"
HEAD_SHA = "15ca91b637f2dba744305c1402217f2fecb7cc5a"
CONTRACT_SHA256 = "9bc0e63c4a59e5b9efaba176a47f5efe4b8b4664e27847dae0d675d06a360207"
SUMMARY_SHA256 = "1df07171f09c780ca33c1d6f7d1049bf2f8094908dc75537bdd486fe477a55b8"
INVENTORY_SHA256 = "7448fb7fbea83cbc3124c4c2e7b0beeb02f6314d25038432159eed648c8d275e"
ARCHIVE_NAME = "e22c-evidence-15ca91b.tar.gz"
ARCHIVE_SHA256 = "4ec1589ddb986667a710d8b049b2ce3d37fc6ea8c2caee656bc2d6c428b58246"
ARCHIVE_SIZE_BYTES = 10_317_998
INVENTORY_FILES = 554
REGULAR_FILES = 555
SYMLINKS = {
    "runtime/bin/libggml-base.so.0": "libggml-base.so.0.18.0",
    "runtime/bin/libggml-cpu.so.0": "libggml-cpu.so.0.18.0",
    "runtime/bin/libggml.so.0": "libggml.so.0.18.0",
    "runtime/bin/libllama-common.so.0": "libllama-common.so.0.0.10216",
    "runtime/bin/libllama.so.0": "libllama.so.0.0.10216",
    "runtime/bin/libmtmd.so.0": "libmtmd.so.0.0.10216",
}


def validate_inventory(evidence: Path) -> dict[str, Any]:
    inventory_path = evidence / "file-inventory-sha256.txt"
    entries: dict[str, str] = {}
    for line in inventory_path.read_text(encoding="utf-8").splitlines():
        digest, separator, recorded = line.partition("  ")
        if not separator or len(digest) != 64 or not recorded.startswith("./"):
            raise ValueError("E22c inventory line differs")
        relative = recorded[2:]
        relative_path = Path(relative)
        if (
            not relative
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative in entries
        ):
            raise ValueError("E22c inventory path is unsafe or duplicate")
        local = evidence / relative_path
        if not local.is_file() or local.is_symlink() or sha256_file(local) != digest:
            raise ValueError(f"E22c inventory differs for {relative}")
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
        *{
            f"cells/{position:02d}-{mode}-w{workers}/probe.json"
            for position, mode, workers in (
                (1, "normal", 6),
                (2, "shared", 8),
                (3, "shared", 8),
                (4, "normal", 6),
                (5, "shared", 8),
                (6, "normal", 6),
                (7, "normal", 6),
                (8, "shared", 8),
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
        raise ValueError("E22c retained file set differs")
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
        raise ValueError("E22c independent replay differs")

    ratios = replay.get("ratio_distributions", {})
    aggregate = ratios.get("aggregate_throughput_ratio", {})
    readiness = ratios.get("all_worker_readiness_ratio", {})
    p95 = ratios.get("p95_latency_ratio", {})
    throughput_per_gib = ratios.get("throughput_per_gib_pss_ratio", {})
    if (
        replay.get("status") != "valid_repeated_maximum_density_not_promoted"
        or replay.get("decision") != "retain_and_narrow_native_axion_claim"
        or replay.get("failed_advance_gates") != ["median_readiness_bounded"]
        or not all(replay.get("validity_gates", {}).values())
        or sum(not value for value in replay.get("advance_gates", {}).values()) != 1
        or replay.get("advance_gates", {}).get("median_readiness_bounded") is not False
        or replay.get("repository_commit") != HEAD_SHA
        or replay.get("contract_sha256") != CONTRACT_SHA256
        or replay.get("host", {}).get("instance_id") != INSTANCE_ID
        or aggregate.get("median") != 1.3525388639297642
        or aggregate.get("minimum") != 1.3457125871306612
        or aggregate.get("coefficient_of_variation") != 0.0036283077729608385
        or p95.get("median") != 0.9779794570822045
        or throughput_per_gib.get("median") != 3.334480682137521
        or readiness.get("median") != 2.0816513504316654
        or sha256_file(workflow_summary) != SUMMARY_SHA256
        or sha256_file(evidence / "contract.json") != CONTRACT_SHA256
    ):
        raise ValueError("E22c retained identity or outcome differs")

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
        "claim_decision": {
            "full_all_lifecycle_promotion": False,
            "repeated_steady_state_fixed_memory_result_valid": True,
            "readiness_regression_must_be_disclosed": True,
            "kernel_or_energy_causality_permitted": False,
            "billing_cost_claim_permitted": False,
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
