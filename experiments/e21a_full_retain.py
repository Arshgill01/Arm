#!/usr/bin/env python3
"""Bind the recovered full E21a matrix to its failed source run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e21a_full_recovery import build_recovered_summary
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e21a_full_recovery import build_recovered_summary


RUN_ID = 30980957266
JOB_ID = 92225070047
HEAD_SHA = "3f540e010f3a14de2ba9eabd5c5cee1b16c24db4"
ARTIFACT_ID = 8920582060
ARTIFACT_NAME = "e21a-online-certificate-30980957266-1"
ARTIFACT_SIZE = 14098713
ARTIFACT_DIGEST = (
    "sha256:c66adef1b213d18f5eec42187c752d87c74ea8ce8c1d035316ee45066bd90c52"
)
ARTIFACT_EXPIRES = "2026-11-03T06:19:15Z"
ARTIFACT_FILES = 143
ARTIFACT_BYTES = 36028075
INVENTORY_SHA256 = "92b558de41cf5ff890be1d6d1fe877f295bea2d9523010f9d209c753afee5920"
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


def validate_inventory(evidence: Path, contract: dict[str, Any]) -> dict[str, Any]:
    expected_cells = {
        Path("cells") / f"{item['index']:02d}-{item['policy']}-r{item['repetition']}"
        for item in contract["execution"]["cell_order"]
    }
    observed_cells = {
        item.parent.relative_to(evidence)
        for item in evidence.glob("cells/*/probe.json")
    }
    if observed_cells != expected_cells:
        raise ValueError("E21a retained cell set differs")
    for cell in expected_cells:
        names = {item.name for item in (evidence / cell).iterdir() if item.is_file()}
        if names != CELL_FILES:
            raise ValueError(f"E21a retained files differ for {cell}")

    files = sorted(
        (item for item in evidence.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(evidence).as_posix(),
    )
    required = {
        "build/runtime-closure.json",
        "build/runtime-files/bin/llama-server",
        "contract.json",
        "github.json",
        "model-sha256.txt",
        "patches/0001-kleidiai-use-validated-arm-features.patch",
        "patches/0002-arm-q8-vector-narrowing-stores.patch",
        "patches/0003-reasoning-budget-forced-token-guard.patch",
        "source-diff.patch",
    }
    relative = {item.relative_to(evidence).as_posix() for item in files}
    if len(files) != ARTIFACT_FILES or not required.issubset(relative):
        raise ValueError("E21a retained artifact inventory is incomplete")
    rows = [
        f"{sha256_file(item)}  {item.relative_to(evidence).as_posix()}"
        for item in files
    ]
    inventory = hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
    total_bytes = sum(item.stat().st_size for item in files)
    if inventory != INVENTORY_SHA256 or total_bytes != ARTIFACT_BYTES:
        raise ValueError("E21a retained artifact inventory digest differs")
    return {
        "file_count": len(files),
        "total_bytes": total_bytes,
        "independent_inventory_sha256": inventory,
        "fresh_process_cells": len(expected_cells),
        "served_requests": contract["execution"]["total_served_requests"],
        "all_source_artifact_files_hashed": True,
    }


def retain(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    summary = build_recovered_summary(evidence, contract_path, root)
    contract = load_object(contract_path)
    github = load_object(evidence / "github.json")
    inventory = validate_inventory(evidence, contract)
    observed = summary["recovery"]["observed_counts_by_cell"]
    if (
        str(github.get("run_id")) != str(RUN_ID)
        or int(github.get("run_attempt", 0)) != 1
        or github.get("sha") != HEAD_SHA
        or summary.get("status") != "invalid_online_transition_certificate"
        or summary.get("quality", {}).get("task_score") != "21/30"
        or summary.get("quality", {}).get("frozen_reference_task_score") != "23/30"
        or summary.get("quality", {}).get("exact_response_mismatches") != 0
        or summary.get("baseline", {}).get("served_requests") != 480
        or summary.get("online", {}).get("served_requests") != 480
        or summary.get("decision", {}).get("valid") is not False
        or summary.get("decision", {}).get("promoted") is not False
        or summary.get("validity_gates", {}).get("reference_answers_preserved")
        is not False
        or summary.get("validity_gates", {}).get("frozen_route_and_admission_counts")
        is not False
        or any(
            cell["request_failures"] != 0
            or cell["served_requests"] != 120
            or cell["correct"] != 84
            or cell["reference_prediction_mismatches"] != 8
            for cell in observed.values()
        )
    ):
        raise ValueError("E21a recovered identity or negative outcome differs")
    return {
        **summary,
        "github": {
            "source_run_id": str(RUN_ID),
            "source_run_attempt": 1,
            "source_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{RUN_ID}",
            "source_run_conclusion": "failure",
            "source_job_id": str(JOB_ID),
            "repository_commit": HEAD_SHA,
            "artifact_id": str(ARTIFACT_ID),
            "artifact_name": ARTIFACT_NAME,
            "artifact_size_bytes": ARTIFACT_SIZE,
            "artifact_digest": ARTIFACT_DIGEST,
            "artifact_expires_at": ARTIFACT_EXPIRES,
        },
        "artifact_recovery": {
            "source_workflow_remains_failed": True,
            "source_failure": "E21a all_uncached r1 frozen counts differ",
            "measurement_step_conclusion": "success",
            "source_ingestion_step_conclusion": "failure",
            "artifact_upload_step_conclusion": "success",
            "complete_retained_matrix_replayed": True,
            "independent_replays": 2,
            "byte_stable": True,
            "native_measurements_added": 0,
            "native_rerun_required": False,
            "source_contract_or_gates_changed": False,
            "inventory": inventory,
        },
        "root_cause_boundary": {
            "observed": (
                "The raw-completion client returned C instead of the frozen B for "
                "arithmetic-04 and systems-04 in every control and online cycle."
            ),
            "policy_behavior": (
                "The online policy failed closed on three transitions, served no "
                "unknown cached attempt, and retained 84 certified routes per cell."
            ),
            "preflight_coverage_gap": (
                "The two-task preflight did not include either drifting task."
            ),
            "unattributed_difference": (
                "The E21 client used /completion with pre-rendered tokens and an "
                "E9c-built binary, while the frozen reference map came from the "
                "earlier OpenAI-compatible quality path and another build. The "
                "artifact does not isolate which difference caused the drift."
            ),
        },
        "campaign_decision": {
            "product_promotion_made": False,
            "diagnostic_performance_gates_passed": all(
                summary["promotion_gates"].values()
            ),
            "online_certificate_generalization_claim_made": False,
            "exact_retained_certificate_boundary_remains_authoritative": True,
            "corrected_successor_requires_full_quality_api_equivalence_preflight": True,
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
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
