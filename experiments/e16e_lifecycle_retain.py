#!/usr/bin/env python3
"""Repair E16d retention without changing its frozen lifecycle gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments import e16d_lifecycle_ingest as e16d
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    import e16d_lifecycle_ingest as e16d
    from e5b_ingest import load_object, sha256_file


SOURCE_RUN_ID = "30988414887"
SOURCE_JOB_ID = "92248513907"
SOURCE_HEAD_SHA = "9baf8b53b8ac704a509ff9abb68805ebbf6b34dd"
SOURCE_ARTIFACT_ID = "8923128444"
SOURCE_ARTIFACT_NAME = "e16d-product-sidecar-lifecycle-30988414887-1"
SOURCE_ARTIFACT_SIZE_BYTES = 13_968_867
SOURCE_ARTIFACT_DIGEST = (
    "sha256:9324b4dabdccd47fdb2094ec309de9f9ef79f6f5c688aab7a1166f25d9b8d51d"
)
SOURCE_ARTIFACT_EXPIRES_AT = "2026-11-03T08:17:31Z"
SOURCE_EXTRACTED_FILES = 61
SOURCE_EXTRACTED_BYTES = 33_762_667
RUNTIME_ALIASES = {
    "runtime/bin/libggml-base.so.0": "runtime/bin/libggml-base.so.0.18.0",
    "runtime/bin/libggml-cpu.so.0": "runtime/bin/libggml-cpu.so.0.18.0",
    "runtime/bin/libggml.so.0": "runtime/bin/libggml.so.0.18.0",
    "runtime/bin/libllama-common.so.0": ("runtime/bin/libllama-common.so.0.0.10216"),
    "runtime/bin/libllama.so.0": "runtime/bin/libllama.so.0.0.10216",
    "runtime/bin/libmtmd.so.0": "runtime/bin/libmtmd.so.0.0.10216",
}
REQUIRED_SOURCE_FILES = {
    "contract.json",
    "github.json",
    "product/cleanup-complete.json",
    "product/cleanup-plan.json",
    "product/corruption-rejection.json",
    "product/launch-plan.json",
    "product/logs/worker-1.stderr.log",
    "product/logs/worker-2.stderr.log",
    "product/outcome.json",
    "product/probe.json",
    "product/process-maps-worker-1.txt",
    "product/process-maps-worker-2.txt",
    "product/ready.json",
    "product/receipt.json",
    "product/verification.json",
    "repository-commit.txt",
    "runtime/runtime-closure.json",
    "runtime/source-diff.patch",
    "runtime/bin/llama-server",
}


def validate_contract(contract: dict[str, Any], root: Path) -> None:
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E16e"
        or contract.get("state")
        != "frozen_after_e16d_reader_failure_before_repaired_retention"
    ):
        raise ValueError("contract does not identify frozen E16e")
    for name, item in contract.get("inputs", {}).items():
        path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise ValueError(f"E16e frozen input differs for {name}")
    predecessor = contract.get("predecessor", {})
    if (
        predecessor.get("run_id") != SOURCE_RUN_ID
        or predecessor.get("head_sha") != SOURCE_HEAD_SHA
        or predecessor.get("artifact_id") != SOURCE_ARTIFACT_ID
        or predecessor.get("artifact_digest") != SOURCE_ARTIFACT_DIGEST
        or predecessor.get("failure_class") != "non_utf8_diagnostic_reader_failure"
    ):
        raise ValueError("E16e predecessor identity differs")


def mechanism_log(path: Path, arena_bytes: int, tensors: int) -> dict[str, Any]:
    """Search ASCII markers without decoding unrelated raw tokenizer bytes."""
    data = path.read_bytes()
    return {
        "mapped_read_only": (
            f"CPU repack sidecar: mapped {arena_bytes} bytes read-only".encode() in data
            and f"with {tensors} bound tensors".encode() in data
        ),
        "all_tensors_loaded_without_runtime_repacking": (
            f"CPU repack sidecar: validated and loaded all {tensors} tensors "
            "without runtime repacking"
        ).encode()
        in data,
        "identity_rejection_observed": b"identity mismatch" in data.lower(),
    }


def source_inventory(evidence: Path) -> dict[str, Any]:
    files = sorted(path for path in evidence.rglob("*") if path.is_file())
    relative = [path.relative_to(evidence).as_posix() for path in files]
    if (
        len(files) != SOURCE_EXTRACTED_FILES
        or sum(path.stat().st_size for path in files) != SOURCE_EXTRACTED_BYTES
        or not REQUIRED_SOURCE_FILES.issubset(relative)
        or "summary.json" in relative
        or "file-inventory-sha256.txt" in relative
    ):
        raise ValueError("E16d failed artifact file set differs")
    for alias, target in RUNTIME_ALIASES.items():
        if sha256_file(evidence / alias) != sha256_file(evidence / target):
            raise ValueError(f"E16d runtime alias differs for {alias}")
    entries = [f"{sha256_file(path)}  {name}" for path, name in zip(files, relative)]
    payload = ("\n".join(entries) + "\n").encode()
    return {
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "entries": entries,
        "all_file_hashes_computed": True,
    }


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    validate_contract(contract, root)
    inventory = source_inventory(evidence)
    source_contract = root / contract["predecessor"]["contract_path"]
    if (evidence / "contract.json").read_bytes() != source_contract.read_bytes():
        raise ValueError("E16d artifact contract differs")
    github = load_object(evidence / "github.json")
    if (
        github.get("run_id") != SOURCE_RUN_ID
        or github.get("run_attempt") != 1
        or github.get("sha") != SOURCE_HEAD_SHA
        or github.get("runner_arch") != "ARM64"
        or github.get("runner_os") != "Linux"
        or (evidence / "repository-commit.txt").read_text().strip() != SOURCE_HEAD_SHA
    ):
        raise ValueError("E16d native source identity differs")

    worker_logs = [
        evidence / f"product/logs/worker-{worker}.stderr.log" for worker in (1, 2)
    ]
    strict_decode_failures = 0
    for path in worker_logs:
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            strict_decode_failures += 1
    if strict_decode_failures != 2:
        raise ValueError("E16d retained log failure mode differs")

    original_reader = e16d.mechanism_log
    e16d.mechanism_log = mechanism_log
    try:
        replay = e16d.build_summary(evidence, source_contract, root)
    finally:
        e16d.mechanism_log = original_reader
    if (
        replay.get("status") != "valid_product_sidecar_lifecycle"
        or len(replay.get("gates", {})) != 14
        or not all(replay.get("gates", {}).values())
        or replay.get("failed_gates")
    ):
        raise ValueError(
            "E16d repaired independent replay did not pass unchanged gates"
        )

    return {
        **replay,
        "experiment_id": "E16e",
        "status": "valid_product_sidecar_lifecycle_retained_after_reader_repair",
        "contract_sha256": sha256_file(contract_path),
        "source_experiment": {
            "experiment_id": "E16d",
            "workflow_conclusion": "failure",
            "run_id": SOURCE_RUN_ID,
            "job_id": SOURCE_JOB_ID,
            "run_url": (
                "https://github.com/Arshgill01/Arm/actions/runs/" + SOURCE_RUN_ID
            ),
            "head_sha": SOURCE_HEAD_SHA,
            "artifact_id": SOURCE_ARTIFACT_ID,
            "artifact_name": SOURCE_ARTIFACT_NAME,
            "artifact_size_bytes": SOURCE_ARTIFACT_SIZE_BYTES,
            "artifact_digest": SOURCE_ARTIFACT_DIGEST,
            "artifact_expires_at": SOURCE_ARTIFACT_EXPIRES_AT,
            "inventory": inventory,
        },
        "validation_repair": {
            "failure": (
                "The frozen E16d reader raised UnicodeDecodeError on raw tokenizer "
                "diagnostic bytes before it could evaluate any lifecycle gate."
            ),
            "change": (
                "Search the same two ASCII mechanism markers in retained bytes; "
                "all other E16d parsing and all 14 acceptance gates are unchanged."
            ),
            "strict_utf8_decode_failures": strict_decode_failures,
            "source_artifact_mutated": False,
            "native_measurements_added": 0,
            "acceptance_gates_changed": False,
            "product_commands_rerun": False,
        },
        "decision": {
            **replay["decision"],
            "e16d_failed_workflow_retained": True,
            "e16e_repaired_retention_valid": True,
            "product_sidecar_workflow_promoted": True,
        },
        "claim_boundary": contract["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inventory-output", type=Path)
    args = parser.parse_args()
    result = build_summary(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if args.inventory_output:
        args.inventory_output.write_text(
            "\n".join(result["source_experiment"]["inventory"]["entries"]) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
