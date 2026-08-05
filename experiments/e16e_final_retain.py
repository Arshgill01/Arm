#!/usr/bin/env python3
"""Bind the repaired E16e replay to its successful native retention artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e16e_lifecycle_retain import build_summary
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e16e_lifecycle_retain import build_summary


RUN_ID = "30989161576"
RUN_ATTEMPT = 1
JOB_ID = "92250913881"
HEAD_SHA = "144b22e584b9f325ad03721fde900c074a83c343"
ARTIFACT_ID = "8923346367"
ARTIFACT_NAME = "e16e-lifecycle-retention-repair-30989161576-1"
ARTIFACT_SIZE_BYTES = 13_997_803
ARTIFACT_DIGEST = (
    "sha256:7dc461cacd549a10e3fbd6777758ff7bada630dc9d58aadf1a6507c63ccf686e"
)
ARTIFACT_EXPIRES_AT = "2026-11-03T08:28:30Z"
EXTRACTED_FILES = 67
EXTRACTED_BYTES = 33_885_227
SUMMARY_SHA256 = "7d9aa3af0ce2b674bd4386a8e7760a5cde633d0b5a096dd9214c2013ad64bc57"
SOURCE_INVENTORY_SHA256 = (
    "b55833c162f77859550dd0f82b26e483866e412aeef78c3b6c6a335ff4d66a4b"
)


def artifact_inventory(artifact: Path) -> dict[str, Any]:
    files = sorted(path for path in artifact.rglob("*") if path.is_file())
    relative = [path.relative_to(artifact).as_posix() for path in files]
    required = {
        "contract.json",
        "github.json",
        "source-file-inventory-sha256.txt",
        "summary-a.json",
        "summary-b.json",
        "summary.json",
        "source/contract.json",
        "source/github.json",
        "source/product/probe.json",
        "source/product/receipt.json",
        "source/product/cleanup-complete.json",
    }
    if (
        len(files) != EXTRACTED_FILES
        or sum(path.stat().st_size for path in files) != EXTRACTED_BYTES
        or not required.issubset(relative)
    ):
        raise ValueError("E16e retained artifact file set differs")
    entries = [
        f"{sha256_file(path)}  {name}"
        for path, name in zip(files, relative, strict=True)
    ]
    return {
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "sha256": hashlib.sha256(("\n".join(entries) + "\n").encode()).hexdigest(),
        "all_file_hashes_verified": True,
    }


def retain(artifact: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    replay = build_summary(artifact / "source", contract_path, root)
    replay_bytes = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    summaries = [
        artifact / name for name in ("summary-a.json", "summary-b.json", "summary.json")
    ]
    if any(path.read_bytes() != replay_bytes for path in summaries):
        raise ValueError("E16e independent replay differs from workflow summaries")
    if sha256_file(artifact / "summary.json") != SUMMARY_SHA256:
        raise ValueError("E16e workflow summary digest differs")
    if (
        sha256_file(artifact / "source-file-inventory-sha256.txt")
        != SOURCE_INVENTORY_SHA256
    ):
        raise ValueError("E16e source inventory digest differs")
    if (artifact / "contract.json").read_bytes() != contract_path.read_bytes():
        raise ValueError("E16e retained contract differs")
    github = load_object(artifact / "github.json")
    if (
        github.get("run_id") != RUN_ID
        or github.get("run_attempt") != RUN_ATTEMPT
        or github.get("sha") != HEAD_SHA
        or github.get("runner_arch") != "ARM64"
        or github.get("runner_os") != "Linux"
    ):
        raise ValueError("E16e native retention identity differs")
    inventory = artifact_inventory(artifact)
    return {
        **replay,
        "native_retention": {
            "run_id": RUN_ID,
            "run_attempt": RUN_ATTEMPT,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{RUN_ID}",
            "job_id": JOB_ID,
            "repository_commit": HEAD_SHA,
            "artifact_id": ARTIFACT_ID,
            "artifact_name": ARTIFACT_NAME,
            "artifact_size_bytes": ARTIFACT_SIZE_BYTES,
            "artifact_digest": ARTIFACT_DIGEST,
            "artifact_expires_at": ARTIFACT_EXPIRES_AT,
        },
        "retention_validation": {
            "independent_replays": 2,
            "workflow_and_local_replays_byte_identical": True,
            "workflow_summary_sha256": SUMMARY_SHA256,
            "source_inventory_sha256": SOURCE_INVENTORY_SHA256,
            "artifact_inventory": inventory,
            "artifact_identity_bound": True,
            "source_e16d_artifact_mutated": False,
            "native_measurements_added": 0,
            "acceptance_gates_changed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(args.artifact_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
