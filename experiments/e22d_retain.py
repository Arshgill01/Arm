#!/usr/bin/env python3
"""Bind the independently replayed E22d result to its sealed Axion bundle."""

from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path
from typing import Any

try:
    from experiments.e22a_freeze import load_object, sha256_file
    from experiments.e22d_ingest import distribution, ingest
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e22a_freeze import load_object, sha256_file
    from e22d_ingest import distribution, ingest


INSTANCE_ID = "5259602977892141423"
HEAD_SHA = "4ad5ef47ec287edc2e705ca8864d2cb09ffad7cb"
CONTRACT_SHA256 = "7a75de6a0f21d8e8e7fa25111db64ade142569574c8c92376b213970171618f9"
SUMMARY_SHA256 = "ffc5c7587ac72d6c84c7c025a52141ce1300ec770743bb7773c5f4d4ceb75e1f"
INVENTORY_SHA256 = "945c5c011be9a6239e0820ba799475cedda5dbfbceaa175760e879386c6e7a53"
ARCHIVE_NAME = "e22d-evidence-4ad5ef4.tar.gz"
ARCHIVE_SHA256 = "7216dd6e0df5281116af85597b6a1edf7b6fccaa4a532fe8e57baed663c09db6"
ARCHIVE_SIZE_BYTES = 19_382_837
SETUP_FAILURE_ARCHIVE_NAME = "e22d-setup-failures-4ad5ef4.tar.gz"
SETUP_FAILURE_ARCHIVE_SHA256 = (
    "21ecb6913c16c4b4c862507fca5df0b08b69398b2dc65f70d9182568a82ff715"
)
SETUP_FAILURE_ARCHIVE_SIZE_BYTES = 9_101_132
INVENTORY_FILES = 605
REGULAR_FILES = 606
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
        if not separator or len(digest) != 64 or not recorded.startswith("evidence/"):
            raise ValueError("E22d inventory line differs")
        relative = recorded.removeprefix("evidence/")
        relative_path = Path(relative)
        if (
            not relative
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative in entries
        ):
            raise ValueError("E22d inventory path is unsafe or duplicate")
        local = evidence / relative_path
        if not local.is_file() or local.is_symlink() or sha256_file(local) != digest:
            raise ValueError(f"E22d inventory differs for {relative}")
        entries[relative] = digest

    actual = {
        item.relative_to(evidence).as_posix()
        for item in evidence.rglob("*")
        if item.is_file() and not item.is_symlink() and item != inventory_path
    }
    links = {
        item.relative_to(evidence).as_posix(): item.readlink().as_posix()
        for item in evidence.rglob("*")
        if item.is_symlink()
    }
    required = {
        "campaign-status.json",
        "contract.json",
        "host-preflight/cloud-instance.json",
        "host-preflight/host-preflight.json",
        "product/sidecar-receipt.json",
        "product/sidecar-verification.json",
        "repeated-campaign-status.json",
        "runtime/bin/llama-server",
        "summary.json",
        "cells/09-normal-w8/cell-status.json",
        "cells/09-normal-w8/host-state-after.txt",
        "cells/09-normal-w8/host-state-before.txt",
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
        raise ValueError("E22d retained file set differs")
    return {
        "hashed_regular_files": len(entries),
        "regular_files_including_root_inventory": len(actual) + 1,
        "runtime_symlinks": len(links),
        "sha256": sha256_file(inventory_path),
        "all_retained_file_hashes_verified": True,
        "generated_model_sidecar_or_raw_tensors_retained": False,
    }


def validate_archive(path: Path, expected_name: str, digest: str, size: int) -> None:
    if path.name != expected_name or path.stat().st_size != size:
        raise ValueError(f"{expected_name} identity differs")
    if sha256_file(path) != digest:
        raise ValueError(f"{expected_name} hash differs")
    with tarfile.open(path, "r:gz") as archive:
        names = {member.name.rstrip("/") for member in archive.getmembers()}
    if expected_name == ARCHIVE_NAME and not {
        "evidence/summary.json",
        "evidence/file-inventory-sha256.txt",
    }.issubset(names):
        raise ValueError("E22d evidence archive members differ")
    if expected_name == SETUP_FAILURE_ARCHIVE_NAME and not {
        "e22d-setup-failures-inventory.txt",
        "evidence-preflight-paranoid4",
        "evidence-preflight-fresh-build-mismatch",
    }.issubset(names):
        raise ValueError("E22d setup-failure archive members differ")


def combined_result(replay: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    current_pairs = replay["pairs"]
    source_pairs = []
    for pair in source["pairs"]:
        enriched = dict(pair)
        indexed = {
            cell["mode"]: cell
            for cell in source["cells"]
            if cell["repetition"] == pair["repetition"]
        }
        enriched["summed_pss_saved_fraction"] = 1.0 - (
            indexed["shared"]["summed_pss_kib"] / indexed["normal"]["summed_pss_kib"]
        )
        source_pairs.append(enriched)
    pairs = source_pairs + current_pairs
    metrics = (
        "aggregate_throughput_ratio",
        "per_worker_throughput_ratio",
        "p95_latency_ratio",
        "all_worker_readiness_ratio",
        "throughput_per_gib_pss_ratio",
        "summed_pss_saved_fraction",
    )
    return {
        "independent_instances": 2,
        "instance_ids": [source["host"]["instance_id"], replay["host"]["instance_id"]],
        "balanced_pairs": len(pairs),
        "exact_measured_requests": sum(
            cell["measured_requests"] for cell in source["cells"] + replay["cells"]
        ),
        "ratio_distributions": {
            metric: distribution([float(pair[metric]) for pair in pairs])
            for metric in metrics
        },
        "same_provider_machine_class": True,
        "cross_provider_or_fleet_claim": False,
    }


def retain(
    evidence: Path,
    contract_path: Path,
    cleanup_path: Path,
    root: Path,
    archive_path: Path | None = None,
    setup_failures_archive_path: Path | None = None,
) -> dict[str, Any]:
    replay = ingest(evidence, contract_path, root)
    replay_bytes = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    workflow_summary = evidence / "summary.json"
    if replay_bytes != workflow_summary.read_bytes():
        raise ValueError("E22d independent replay differs")

    ratios = replay.get("ratio_distributions", {})
    aggregate = ratios.get("aggregate_throughput_ratio", {})
    readiness = ratios.get("all_worker_readiness_ratio", {})
    p95 = ratios.get("p95_latency_ratio", {})
    per_worker = ratios.get("per_worker_throughput_ratio", {})
    pss = ratios.get("summed_pss_saved_fraction", {})
    throughput_per_gib = ratios.get("throughput_per_gib_pss_ratio", {})
    boundary = replay.get("normal_eight_resource_boundary", {})
    if (
        replay.get("status") != "valid_independent_host_replication_promoted"
        or replay.get("decision")
        != "promote_two_independent_axion_instance_density_result"
        or replay.get("failed_advance_gates")
        or not all(replay.get("validity_gates", {}).values())
        or not all(replay.get("advance_gates", {}).values())
        or replay.get("repository_commit") != HEAD_SHA
        or replay.get("contract_sha256") != CONTRACT_SHA256
        or replay.get("host", {}).get("instance_id") != INSTANCE_ID
        or aggregate.get("median") != 1.3613361603256515
        or aggregate.get("minimum") != 1.354388503905701
        or aggregate.get("coefficient_of_variation") != 0.005988047670527135
        or p95.get("median") != 0.9695073380352219
        or per_worker.get("median") != 1.0210021202442385
        or pss.get("median") != 0.5896364573610855
        or throughput_per_gib.get("median") != 3.3175588277046995
        or readiness.get("median") != 2.21383494546337
        or boundary.get("oom_kill_delta") != 1
        or boundary.get("pswpin_delta") != 0
        or boundary.get("pswpout_delta") != 0
        or sha256_file(workflow_summary) != SUMMARY_SHA256
        or sha256_file(evidence / "contract.json") != CONTRACT_SHA256
    ):
        raise ValueError("E22d retained identity or outcome differs")

    cleanup = load_object(cleanup_path)
    if (
        cleanup.get("experiment_id") != replay["experiment_id"]
        or cleanup.get("instance", {}).get("id") != INSTANCE_ID
        or cleanup.get("delete_operation", {}).get("target_id") != INSTANCE_ID
        or cleanup.get("delete_operation", {}).get("status") != "DONE"
        or not all(cleanup.get("post_delete_checks", {}).values())
        or cleanup.get("cost_closeout", {}).get("estimated_compute_usd")
        >= replay["cost_control"]["experiment_maximum_usd"]
    ):
        raise ValueError("E22d cloud cleanup record differs")

    if archive_path is not None:
        validate_archive(archive_path, ARCHIVE_NAME, ARCHIVE_SHA256, ARCHIVE_SIZE_BYTES)
    if setup_failures_archive_path is not None:
        validate_archive(
            setup_failures_archive_path,
            SETUP_FAILURE_ARCHIVE_NAME,
            SETUP_FAILURE_ARCHIVE_SHA256,
            SETUP_FAILURE_ARCHIVE_SIZE_BYTES,
        )

    source = load_object(root / replay["source_result"]["manifest"])
    inventory = validate_inventory(evidence)
    return {
        **replay,
        "combined_two_instance_result": combined_result(replay, source),
        "resource_cleanup": cleanup,
        "retention_validation": {
            "independent_replays": 3,
            "independent_replay_byte_identical": True,
            "workflow_summary_sha256": sha256_file(workflow_summary),
            "workflow_inventory": inventory,
            "archive_name": ARCHIVE_NAME,
            "archive_sha256": ARCHIVE_SHA256,
            "archive_size_bytes": ARCHIVE_SIZE_BYTES,
            "setup_failure_archive_name": SETUP_FAILURE_ARCHIVE_NAME,
            "setup_failure_archive_sha256": SETUP_FAILURE_ARCHIVE_SHA256,
            "setup_failure_archive_size_bytes": SETUP_FAILURE_ARCHIVE_SIZE_BYTES,
            "artifact_identity_bound": True,
            "native_measurements_added": 0,
            "source_contract_or_gates_changed": False,
            "archives_locally_verified": archive_path is not None
            and setup_failures_archive_path is not None,
        },
        "claim_decision": {
            "two_independent_axion_instance_density_promotion": True,
            "full_all_lifecycle_promotion": False,
            "readiness_regression_must_be_disclosed": True,
            "kernel_or_energy_causality_permitted": False,
            "billing_cost_claim_permitted": False,
            "cross_provider_or_fleet_claim_permitted": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--cleanup", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--setup-failures-archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        args.evidence_dir.resolve(),
        args.contract.resolve(),
        args.cleanup.resolve(),
        args.root.resolve(),
        args.archive.resolve() if args.archive else None,
        args.setup_failures_archive.resolve() if args.setup_failures_archive else None,
    )
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
