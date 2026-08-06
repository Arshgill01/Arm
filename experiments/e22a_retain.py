#!/usr/bin/env python3
"""Bind the independently replayed E22a preflight to its native artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e22a_freeze import load_object, sha256_file
    from experiments.e22a_ingest import ingest
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e22a_freeze import load_object, sha256_file
    from e22a_ingest import ingest


RUN_ID = 31086439785
RUN_ATTEMPT = 1
JOB_ID = 92566886659
ARTIFACT_ID = 8962040739
ARTIFACT_NAME = f"e22a-sidecar-scaling-preflight-{RUN_ID}-{RUN_ATTEMPT}"
ARTIFACT_SIZE_BYTES = 14_302_290
ARTIFACT_DIGEST = (
    "sha256:112ac47bdffdf2ba5ad620f2e6d5b8c8f68392ae6b949c21d311680a1f8f5fe5"
)
ARTIFACT_EXPIRES_AT = "2026-11-04T08:48:52Z"
HEAD_SHA = "659c53acf83f6669957e7a30cf1c0a80287e58c4"
WORKFLOW_SUMMARY_SHA256 = (
    "02228e33f4f295f1aa638b623c952f9aed7df406768f7810c4a948477bc3cf11"
)
WORKFLOW_INVENTORY_SHA256 = (
    "10f9ce347d9420f696c680e104edfc531bb807db03fb0ad3437ad53fbe82f068"
)
INVENTORY_FILES = 214
EXTRACTED_FILES = 221
EXTRACTED_BYTES = 36_256_683
ARTIFACT_ROOT = f"/results/raw/e22a-{RUN_ID}-{RUN_ATTEMPT}/"
RUNTIME_ALIASES = {
    "runtime/bin/libggml-base.so.0": "runtime/bin/libggml-base.so.0.18.0",
    "runtime/bin/libggml-cpu.so.0": "runtime/bin/libggml-cpu.so.0.18.0",
    "runtime/bin/libggml.so.0": "runtime/bin/libggml.so.0.18.0",
    "runtime/bin/libllama-common.so.0": ("runtime/bin/libllama-common.so.0.0.10216"),
    "runtime/bin/libllama.so.0": "runtime/bin/libllama.so.0.0.10216",
    "runtime/bin/libmtmd.so.0": "runtime/bin/libmtmd.so.0.0.10216",
}


def validate_workflow_inventory(evidence: Path) -> dict[str, Any]:
    inventory = evidence / "file-inventory-sha256.txt"
    entries: dict[str, str] = {}
    for line in inventory.read_text(encoding="utf-8").splitlines():
        digest, separator, absolute = line.partition("  ")
        if not separator or len(digest) != 64 or ARTIFACT_ROOT not in absolute:
            raise ValueError("E22a workflow inventory line differs")
        relative = absolute.split(ARTIFACT_ROOT, 1)[1]
        relative_path = Path(relative)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or relative in entries
        ):
            raise ValueError("E22a inventory path is unsafe or duplicate")
        local = evidence / relative_path
        if not local.is_file() or sha256_file(local) != digest:
            raise ValueError(f"E22a inventory differs for {relative}")
        entries[relative] = digest

    actual = {
        item.relative_to(evidence).as_posix()
        for item in evidence.rglob("*")
        if item.is_file() and item.name != "file-inventory-sha256.txt"
    }
    required = {
        "contract.json",
        "github.json",
        "summary.json",
        "product/sidecar-receipt.json",
        "product/sidecar-verification.json",
        "runtime/bin/llama-server",
        *{
            f"cells/{cell}/probe.json"
            for cell in (
                "01-normal-w1",
                "02-shared-w1",
                "03-shared-w2",
                "04-normal-w2",
                "05-normal-w4",
                "06-shared-w4",
            )
        },
    }
    outside = actual - set(entries)
    all_files = [item for item in evidence.rglob("*") if item.is_file()]
    generated = [
        item.relative_to(evidence).as_posix()
        for item in all_files
        if item.suffix == ".gguf"
        or item.name == "pareto64-sidecar.bin"
        or "raw-tensors" in item.parts
    ]
    if (
        len(entries) != INVENTORY_FILES
        or not required.issubset(entries)
        or set(entries) - actual
        or outside != set(RUNTIME_ALIASES)
        or len(all_files) != EXTRACTED_FILES
        or sum(item.stat().st_size for item in all_files) != EXTRACTED_BYTES
        or any(
            sha256_file(evidence / alias) != sha256_file(evidence / target)
            for alias, target in RUNTIME_ALIASES.items()
        )
        or generated
        or sha256_file(inventory) != WORKFLOW_INVENTORY_SHA256
    ):
        raise ValueError("E22a workflow inventory file set differs")
    return {
        "hashed_files": len(entries),
        "extracted_files": len(all_files),
        "extracted_bytes": sum(item.stat().st_size for item in all_files),
        "sha256": sha256_file(inventory),
        "files_outside_runner_regular_file_inventory": {
            relative: sha256_file(evidence / relative) for relative in sorted(outside)
        },
        "generated_model_sidecar_or_raw_tensors_retained": False,
        "all_retained_file_hashes_verified": True,
    }


def retain(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    replay = ingest(evidence, contract_path, root)
    replay_bytes = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    workflow_summary = evidence / "summary.json"
    if replay_bytes != workflow_summary.read_bytes():
        raise ValueError("E22a independent replay differs")

    github = load_object(evidence / "github.json")
    pairs = {item["worker_count"]: item for item in replay.get("pairs", [])}
    if (
        replay.get("status") != "valid_sidecar_scaling_preflight"
        or replay.get("decision") != "proceed_to_stable_host_fixed_memory_contract"
        or replay.get("failed_advance_gates") != []
        or not all(replay.get("advance_gates", {}).values())
        or replay.get("repository_commit") != HEAD_SHA
        or replay.get("claim_boundary", {}).get("preflight_only") is not True
        or replay.get("claim_boundary", {}).get("final_performance_claim_permitted")
        is not False
        or replay.get("host", {}).get("stable_performance_authority") is not False
        or replay.get("host", {}).get("perf", {}).get("available") is not False
        or [item.get("measured_requests") for item in replay.get("cells", [])]
        != [30, 30, 60, 60, 120, 120]
        or any(item.get("reference_prediction_mismatches") for item in replay["cells"])
        or any(item.get("request_failures") for item in replay["cells"])
        or any(item.get("response_differences") for item in pairs.values())
        or pairs.get(2, {}).get("summed_pss_saved_kib") != 2_086_925
        or pairs.get(4, {}).get("summed_pss_saved_kib") != 6_261_824
        or github.get("run_id") != str(RUN_ID)
        or github.get("run_attempt") != RUN_ATTEMPT
        or github.get("sha") != HEAD_SHA
        or github.get("runner_arch") != "ARM64"
        or github.get("runner_os") != "Linux"
    ):
        raise ValueError("E22a retained identity or outcome differs")
    if sha256_file(workflow_summary) != WORKFLOW_SUMMARY_SHA256:
        raise ValueError("E22a workflow summary digest differs")

    inventory = validate_workflow_inventory(evidence)
    return {
        **replay,
        "github": {
            "run_id": str(RUN_ID),
            "run_attempt": RUN_ATTEMPT,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{RUN_ID}",
            "repository_commit": HEAD_SHA,
            "job_id": str(JOB_ID),
            "artifact_id": str(ARTIFACT_ID),
            "artifact_name": ARTIFACT_NAME,
            "artifact_size_bytes": ARTIFACT_SIZE_BYTES,
            "artifact_digest": ARTIFACT_DIGEST,
            "artifact_expires_at": ARTIFACT_EXPIRES_AT,
        },
        "retention_validation": {
            "independent_replays": 2,
            "independent_replay_byte_identical": True,
            "workflow_summary_sha256": sha256_file(workflow_summary),
            "workflow_inventory_sha256": inventory["sha256"],
            "workflow_inventory": inventory,
            "artifact_identity_bound": True,
            "native_measurements_added": 0,
            "source_contract_or_gates_changed": False,
        },
        "campaign_decision": {
            "sidecar_density_hypothesis_remains_primary": True,
            "stable_host_fixed_memory_successor_authorized": True,
            "fixed_memory_cap_frozen": False,
            "final_performance_claim_permitted": False,
            "pmu_causality_claim_permitted": False,
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
