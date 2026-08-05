#!/usr/bin/env python3
"""Bind the independently replayed full E21b matrix to its native artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e21b_full_ingest import build_summary
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e21b_full_ingest import build_summary


RUN_ID = 30985501097
RUN_ATTEMPT = 1
JOB_ID = 92239193095
ARTIFACT_ID = 8922450721
ARTIFACT_NAME = f"e21b-openai-certificate-{RUN_ID}-{RUN_ATTEMPT}"
ARTIFACT_SIZE_BYTES = 14_416_402
ARTIFACT_DIGEST = (
    "sha256:dc4ffe0c0b58a805df5d4c1a72c43593bb0fd9513b4726b8814ccd0376bb7fce"
)
ARTIFACT_EXPIRES_AT = "2026-11-03T07:33:41Z"
HEAD_SHA = "48cadbca063a2ad3b541edddf9649eb8356d0511"
WORKFLOW_SUMMARY_SHA256 = (
    "74b4ab3c0cff5bb7785337c4355a90bd9920b5013215e1a891a76c7eb2e790ce"
)
INVENTORY_FILES = 138
EXTRACTED_FILES = 146
EXTRACTED_BYTES = 37_909_169
ARTIFACT_ROOT = f"/results/raw/e21b-{RUN_ID}-{RUN_ATTEMPT}/"
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
CELL_FILES = {
    "health.json",
    "metrics.txt",
    "probe.json",
    "readiness.json",
    "recipe.json",
    "runner-state-after.txt",
    "runner-state-before.txt",
    "server-pid.txt",
    "server-shell-exit.txt",
    "server-time.log",
    "server.stderr.log",
    "server.stdout.log",
    "slots.json",
}


def validate_workflow_inventory(
    evidence: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    inventory = evidence / "file-inventory-sha256.txt"
    entries: dict[str, str] = {}
    for line in inventory.read_text(encoding="utf-8").splitlines():
        digest, separator, absolute = line.partition("  ")
        if not separator or len(digest) != 64 or ARTIFACT_ROOT not in absolute:
            raise ValueError("E21b full workflow inventory line differs")
        relative = absolute.split(ARTIFACT_ROOT, 1)[1]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in entries:
            raise ValueError("E21b full inventory path is unsafe or duplicate")
        local = evidence / relative
        if not local.is_file() or sha256_file(local) != digest:
            raise ValueError(f"E21b full inventory differs for {relative}")
        entries[relative] = digest

    expected_cells = {
        f"cells/{item['index']:02d}-{item['policy']}-r{item['repetition']}"
        for item in contract["execution"]["cell_order"]
    }
    for cell in expected_cells:
        names = {item.name for item in (evidence / cell).iterdir() if item.is_file()}
        if names != CELL_FILES:
            raise ValueError(f"E21b full retained files differ for {cell}")

    actual = {
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file() and path.name != "file-inventory-sha256.txt"
    }
    required = {
        "contract.json",
        "summary.json",
        "github.json",
        "source-diff.patch",
        "build/runtime-closure.json",
        "build/runtime-files/bin/llama-server",
        *{f"{cell}/probe.json" for cell in expected_cells},
    }
    outside = actual - set(entries)
    expected_outside = {"disk-after.txt", *RUNTIME_ALIASES}
    all_files = [path for path in evidence.rglob("*") if path.is_file()]
    if (
        len(entries) != INVENTORY_FILES
        or not required.issubset(entries)
        or set(entries) - actual
        or outside != expected_outside
        or len(all_files) != EXTRACTED_FILES
        or sum(path.stat().st_size for path in all_files) != EXTRACTED_BYTES
        or any(
            sha256_file(evidence / alias) != sha256_file(evidence / target)
            for alias, target in RUNTIME_ALIASES.items()
        )
    ):
        raise ValueError("E21b full workflow inventory file set differs")
    return {
        "hashed_files": len(entries),
        "extracted_files": len(all_files),
        "extracted_bytes": sum(path.stat().st_size for path in all_files),
        "sha256": sha256_file(inventory),
        "files_outside_runner_regular_file_inventory": {
            relative: sha256_file(evidence / relative) for relative in sorted(outside)
        },
        "all_retained_file_hashes_verified": True,
    }


def retain(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    replay = build_summary(evidence, contract_path, root)
    contract = load_object(contract_path)
    replay_bytes = (json.dumps(replay, indent=2, sort_keys=True) + "\n").encode()
    workflow_summary = evidence / "summary.json"
    if replay_bytes != workflow_summary.read_bytes():
        raise ValueError("E21b full independent replay differs")

    github = load_object(evidence / "github.json")
    ratios = replay.get("lifecycle_ratios", {})
    tail = replay.get("tail_boundaries", {})
    decisions = replay.get("online_decisions_per_repetition", [])
    if (
        replay.get("status") != "valid_openai_online_certificate_promoted"
        or not all(replay.get("validity_gates", {}).values())
        or not all(replay.get("promotion_gates", {}).values())
        or replay.get("quality", {}).get("task_score") != "23/30"
        or replay.get("quality", {}).get("baseline_correct") != 368
        or replay.get("quality", {}).get("online_correct") != 368
        or replay.get("quality", {}).get("paired_exact_response_mismatches") != 0
        or replay.get("decision", {}).get("performance_policy_promoted") is not True
        or replay.get("decision", {}).get("safety_certificate_established") is not True
        or ratios.get("throughput") != 1.7277643677141625
        or ratios.get("cpu_seconds_per_served_request") != 0.5775226263862093
        or ratios.get("p95_user_latency") != 1.19683257836113
        or tail.get("synchronous_first_use", {}).get("p95_latency_ratio")
        != 1.6646836511307348
        or tail.get("certified_steady_state", {}).get("p95_latency_ratio")
        != 0.43301642057316214
        or [
            item.get("first_cumulative_break_even_cycle")
            for item in replay["break_even"]
        ]
        != [2, 2, 2, 2]
        or len(decisions) != 4
        or any(
            item.get("certified_transitions") != 30
            or item.get("denied_transitions") != 1
            or item.get("revocations") != 0
            or item.get("route_counts", {}).get("certified_cache") != 89
            or item.get("route_counts", {}).get("unknown_shadow_then_oracle") != 31
            for item in decisions
        )
        or replay.get("revocation_boundary", {}).get(
            "post_certification_revocation_supported"
        )
        is not False
        or github.get("run_id") != str(RUN_ID)
        or github.get("run_attempt") != RUN_ATTEMPT
        or github.get("sha") != HEAD_SHA
        or github.get("runner_arch") != "ARM64"
        or github.get("runner_os") != "Linux"
    ):
        raise ValueError("E21b full retained identity or outcome differs")

    inventory = validate_workflow_inventory(evidence, contract)
    if sha256_file(workflow_summary) != WORKFLOW_SUMMARY_SHA256:
        raise ValueError("E21b full workflow summary digest differs")
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
            "adaptive_online_policy_promoted": True,
            "exact_output_safety_established": True,
            "first_use_tail_regression_retained": True,
            "break_even_cycle": 2,
            "periodic_post_certification_revocation_claimed": False,
            "semantic_or_arbitrary_prompt_generalization_claimed": False,
            "e13b_exact_certificate_remains_valid_for_its_own_boundary": True,
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
