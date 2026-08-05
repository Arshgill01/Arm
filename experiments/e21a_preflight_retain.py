#!/usr/bin/env python3
"""Bind the independently replayed E21a preflight to its native artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e21a_preflight_ingest import build_summary
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e21a_preflight_ingest import build_summary


RUN_ID = 30979498751
RUN_ATTEMPT = 1
JOB_ID = 92220680510
ARTIFACT_ID = 8919581630
ARTIFACT_NAME = f"e21a-online-certificate-preflight-{RUN_ID}-{RUN_ATTEMPT}"
ARTIFACT_SIZE_BYTES = 13_780_881
ARTIFACT_DIGEST = (
    "sha256:24ee6f5e9d01ac3cb054b99fffea989c47b31cd652adb4d8a4092aefc1fcb741"
)
ARTIFACT_EXPIRES_AT = "2026-11-03T05:53:13Z"
HEAD_SHA = "7e47c20745d7b1694247770edc36fe1908021fce"
INVENTORY_FILES = 60
ARTIFACT_ROOT = f"/results/raw/e21a-preflight-{RUN_ID}-{RUN_ATTEMPT}/"
RUNTIME_ALIASES = {
    "build/runtime-files/bin/libggml-base.so.0": (
        "build/runtime-files/bin/libggml-base.so.0.18.0"
    ),
    "build/runtime-files/bin/libggml-cpu.so.0": (
        "build/runtime-files/bin/libggml-cpu.so.0.18.0"
    ),
    "build/runtime-files/bin/libggml.so.0": (
        "build/runtime-files/bin/libggml.so.0.18.0"
    ),
    "build/runtime-files/bin/libllama-common.so.0": (
        "build/runtime-files/bin/libllama-common.so.0.0.10216"
    ),
    "build/runtime-files/bin/libllama.so.0": (
        "build/runtime-files/bin/libllama.so.0.0.10216"
    ),
    "build/runtime-files/bin/libmtmd.so.0": (
        "build/runtime-files/bin/libmtmd.so.0.0.10216"
    ),
}


def validate_workflow_inventory(evidence: Path) -> dict[str, Any]:
    inventory = evidence / "file-inventory-sha256.txt"
    entries: dict[str, str] = {}
    for line in inventory.read_text(encoding="utf-8").splitlines():
        digest, separator, absolute = line.partition("  ")
        if not separator or len(digest) != 64 or ARTIFACT_ROOT not in absolute:
            raise ValueError("E21a preflight workflow inventory line differs")
        relative = absolute.split(ARTIFACT_ROOT, 1)[1]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in entries:
            raise ValueError("E21a preflight inventory path is unsafe or duplicate")
        local = evidence / relative
        if not local.is_file() or sha256_file(local) != digest:
            raise ValueError(f"E21a preflight inventory differs for {relative}")
        entries[relative] = digest

    required = {
        "contract.json",
        "summary.json",
        "github.json",
        "source-diff.patch",
        "build/runtime-closure.json",
        "cells/01-all_uncached/probe.json",
        "cells/01-all_uncached/slots.json",
        "cells/02-online/probe.json",
        "cells/02-online/slots.json",
    }
    actual = {
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file() and path.name != "file-inventory-sha256.txt"
    }
    outside = actual - set(entries)
    expected_outside = {"disk-after.txt", *RUNTIME_ALIASES}
    if (
        len(entries) != INVENTORY_FILES
        or not required.issubset(entries)
        or set(entries) - actual
        or outside != expected_outside
        or any(
            sha256_file(evidence / alias) != sha256_file(evidence / target)
            for alias, target in RUNTIME_ALIASES.items()
        )
    ):
        raise ValueError("E21a preflight workflow inventory file set differs")
    return {
        "hashed_files": len(entries),
        "sha256": sha256_file(inventory),
        "files_outside_runner_regular_file_inventory": {
            relative: sha256_file(evidence / relative)
            for relative in sorted(outside)
        },
        "all_retained_file_hashes_verified": True,
    }


def retain(evidence: Path, contract: Path, root: Path) -> dict[str, Any]:
    replay = build_summary(evidence, contract, root)
    replay_bytes = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    workflow_summary = evidence / "summary.json"
    if replay_bytes != workflow_summary.read_bytes():
        raise ValueError("E21a preflight independent replay differs")

    github = load_object(evidence / "github.json")
    failed_gates = sorted(
        name for name, passed in replay.get("gates", {}).items() if not passed
    )
    if (
        replay.get("status")
        != "valid_online_transition_certificate_preflight"
        or failed_gates
        or replay.get("decision", {}).get("full_experiment_authorized") is not True
        or replay.get("decision", {}).get("native_performance_claim_allowed")
        is not False
        or replay.get("quality", {}).get("online_vs_uncached_response_mismatches")
        != 0
        or replay.get("baseline", {}).get("request_failures") != 0
        or replay.get("online", {}).get("request_failures") != 0
        or replay.get("online_decisions", {}).get("certified_transitions") != 2
        or replay.get("online_decisions", {}).get("denied_transitions") != 1
        or github.get("run_id") != str(RUN_ID)
        or github.get("run_attempt") != RUN_ATTEMPT
        or github.get("sha") != HEAD_SHA
        or github.get("runner_arch") != "ARM64"
        or github.get("runner_os") != "Linux"
    ):
        raise ValueError("E21a preflight retained identity or decision differs")

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
        "preflight_decision": {
            "all_frozen_gates_passed": True,
            "full_experiment_authorized": True,
            "native_performance_claim_allowed": False,
            "diagnostic_throughput_ratio": replay["ratios_diagnostic_only"][
                "throughput"
            ],
            "diagnostic_p95_latency_ratio": replay["ratios_diagnostic_only"][
                "p95_user_latency"
            ],
            "observed_first_use_tail_regression_retained": True,
            "post_result_gate_change_permitted": False,
        },
        "retention_validation": {
            "independent_replay_byte_identical": True,
            "workflow_summary_sha256": sha256_file(workflow_summary),
            "workflow_inventory_sha256": inventory["sha256"],
            "workflow_inventory_hashed_files": inventory["hashed_files"],
            "workflow_inventory": inventory,
            "artifact_identity_bound": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
