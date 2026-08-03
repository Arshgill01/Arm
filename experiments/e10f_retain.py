#!/usr/bin/env python3
"""Retain independently reproduced E10f paired holdout evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


ALIAS_TARGETS = {
    "build/runtime-files/bin/libggml-base.so.0": "build/runtime-files/bin/libggml-base.so.0.18.0",
    "build/runtime-files/bin/libggml-cpu.so.0": "build/runtime-files/bin/libggml-cpu.so.0.18.0",
    "build/runtime-files/bin/libggml.so.0": "build/runtime-files/bin/libggml.so.0.18.0",
    "build/runtime-files/bin/libllama-common.so.0": "build/runtime-files/bin/libllama-common.so.0.0.10216",
    "build/runtime-files/bin/libllama.so.0": "build/runtime-files/bin/libllama.so.0.0.10216",
    "build/runtime-files/bin/libmtmd.so.0": "build/runtime-files/bin/libmtmd.so.0.0.10216",
}


def validate_inventory(evidence: Path, marker: str) -> dict[str, Any]:
    inventory_path = evidence / "file-inventory-sha256.txt"
    entries: dict[str, str] = {}
    raw_inventory = hashlib.sha256()
    raw_files = 0
    raw_compressed_bytes = 0
    for line in inventory_path.read_text(encoding="utf-8").splitlines():
        digest, absolute = line.split("  ", 1)
        if len(digest) != 64 or marker not in absolute:
            raise ValueError("E10f artifact inventory line is invalid")
        relative = absolute.split(marker, 1)[1]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in entries:
            raise ValueError("E10f artifact inventory path is unsafe or duplicate")
        local = evidence / path
        if not local.is_file() or sha256_file(local) != digest:
            raise ValueError(f"E10f artifact inventory differs for {relative}")
        entries[relative] = digest
        if relative.startswith("raw/") and relative.endswith(".json.gz"):
            raw_inventory.update(f"{digest}  {relative}\n".encode())
            raw_files += 1
            raw_compressed_bytes += local.stat().st_size
    actual = {
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file() and path.name != "file-inventory-sha256.txt"
    }
    expected_unlisted = {*ALIAS_TARGETS, "disk-after.txt"}
    if any(
        sha256_file(evidence / alias) != sha256_file(evidence / target)
        for alias, target in ALIAS_TARGETS.items()
    ):
        raise ValueError("E10f materialized runtime alias differs from its target")
    if set(entries) - actual or actual - set(entries) != expected_unlisted:
        raise ValueError("E10f artifact inventory file set differs")
    return {
        "file_count": len(entries),
        "inventory_sha256": sha256_file(inventory_path),
        "raw_responses": {
            "file_count": raw_files,
            "compressed_bytes": raw_compressed_bytes,
            "inventory_sha256": raw_inventory.hexdigest(),
        },
        "files_outside_runner_regular_file_inventory": {
            relative: sha256_file(evidence / relative)
            for relative in sorted(expected_unlisted)
        },
        "all_retained_file_hashes_verified": True,
    }


def artifact_record(
    *, name: str, artifact_id: str, size_bytes: int, digest: str
) -> dict[str, Any]:
    if (
        not artifact_id.isdigit()
        or size_bytes <= 0
        or not digest.startswith("sha256:")
        or len(digest.removeprefix("sha256:")) != 64
    ):
        raise ValueError("E10f artifact metadata is invalid")
    return {
        "name": name,
        "id": artifact_id,
        "size_bytes": size_bytes,
        "digest": digest,
    }


def build_manifest(
    *,
    primary: Path,
    control: Path,
    workflow_aggregate: Path,
    independent_primary: Path,
    independent_control: Path,
    independent_aggregate: Path,
    plan_path: Path,
    run_id: str,
    run_attempt: int,
    repository_commit: str,
    primary_job_id: str,
    control_job_id: str,
    aggregate_job_id: str,
    primary_artifact: dict[str, Any],
    control_artifact: dict[str, Any],
    aggregate_artifact: dict[str, Any],
) -> dict[str, Any]:
    primary_summary_path = primary / "summary.json"
    control_summary_path = control / "summary.json"
    primary_summary = load_object(primary_summary_path)
    control_summary = load_object(control_summary_path)
    aggregate = load_object(workflow_aggregate)
    primary_local = load_object(independent_primary)
    control_local = load_object(independent_control)
    aggregate_local = load_object(independent_aggregate)
    primary_github = load_object(primary / "github.json")
    control_github = load_object(control / "github.json")
    validation = aggregate.get("validation", {})
    models = aggregate.get("models", [])
    if (
        primary_summary != primary_local
        or control_summary != control_local
        or aggregate != aggregate_local
        or aggregate.get("status") != "valid_safe_sampled_external_holdout"
        or primary_summary.get("status") != "valid_safe_sampled_external_holdout_cell"
        or control_summary.get("status") != "valid_safe_sampled_external_holdout_cell"
        or aggregate.get("contract_sha256") != sha256_file(plan_path)
        or len(models) != 2
        or [item.get("model", {}).get("candidate") for item in models]
        != ["ministral3_3b_q4_k_m", "ministral3_3b_q4_0"]
        or any(item.get("request_failures") != 0 for item in models)
        or any(item.get("raw_response_count") != 14374 for item in models)
        or any(item.get("preflight", {}).get("status") != "pass" for item in models)
        or set(validation.values()) != {True, False}
        or validation.get("original_e10d_rewritten") is not False
        or validation.get("original_admission_contract_rewritten") is not False
        or validation.get("minimum_quality_gate_used") is not False
        or not all(
            validation.get(name) is True
            for name in (
                "all_raw_responses_retained_once",
                "both_models_complete",
                "native_arm64",
                "per_sample_logs_retained",
                "same_frozen_workload",
                "zero_request_failures",
            )
        )
        or not run_id.isdigit()
        or run_attempt != 1
        or not all(
            value.isdigit()
            for value in (primary_job_id, control_job_id, aggregate_job_id)
        )
        or any(
            github.get("run_id") != run_id
            or github.get("run_attempt") != run_attempt
            or github.get("sha") != repository_commit
            for github in (primary_github, control_github)
        )
    ):
        raise ValueError("E10f retained result or provenance differs")
    primary_inventory = validate_inventory(
        primary,
        f"/results/raw/e10f-ministral3_3b_q4_k_m-{run_id}-{run_attempt}/",
    )
    control_inventory = validate_inventory(
        control,
        f"/results/raw/e10f-ministral3_3b_q4_0-{run_id}-{run_attempt}/",
    )
    if (
        primary_inventory["raw_responses"]["file_count"] != 14374
        or control_inventory["raw_responses"]["file_count"] != 14374
    ):
        raise ValueError("E10f retained raw response count differs")
    return {
        **aggregate,
        "decision": {
            "supplemental_external_holdout_valid": True,
            "original_e10d_rewritten": False,
            "minimum_quality_gate_used": False,
            "e10f_generated_quant_prerequisite_satisfied": True,
            "e12a_imatrix_prerequisite_satisfied": False,
            "generated_quant_frontier_dispatch_allowed": False,
            "reason": (
                "E10f is valid, but the generated-quant frontier remains gated on "
                "an independently retained passing E12a importance matrix."
            ),
        },
        "github": {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "repository_commit": repository_commit,
            "jobs": {
                "primary": primary_job_id,
                "control": control_job_id,
                "aggregate": aggregate_job_id,
            },
            "artifacts": {
                "primary": primary_artifact,
                "control": control_artifact,
                "aggregate": aggregate_artifact,
            },
        },
        "artifact_validation": {
            "primary": {
                "workflow_summary_sha256": sha256_file(primary_summary_path),
                "independent_summary_sha256": sha256_file(independent_primary),
                "independent_summary_byte_identical": True,
                "inventory": primary_inventory,
            },
            "control": {
                "workflow_summary_sha256": sha256_file(control_summary_path),
                "independent_summary_sha256": sha256_file(independent_control),
                "independent_summary_byte_identical": True,
                "inventory": control_inventory,
            },
            "aggregate": {
                "workflow_summary_sha256": sha256_file(workflow_aggregate),
                "independent_summary_sha256": sha256_file(independent_aggregate),
                "independent_summary_byte_identical": True,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--workflow-aggregate", type=Path, required=True)
    parser.add_argument("--independent-primary", type=Path, required=True)
    parser.add_argument("--independent-control", type=Path, required=True)
    parser.add_argument("--independent-aggregate", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument("--primary-job-id", required=True)
    parser.add_argument("--control-job-id", required=True)
    parser.add_argument("--aggregate-job-id", required=True)
    for role in ("primary", "control", "aggregate"):
        parser.add_argument(f"--{role}-artifact-name", required=True)
        parser.add_argument(f"--{role}-artifact-id", required=True)
        parser.add_argument(f"--{role}-artifact-size-bytes", type=int, required=True)
        parser.add_argument(f"--{role}-artifact-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifacts = {
        role: artifact_record(
            name=getattr(args, f"{role}_artifact_name"),
            artifact_id=getattr(args, f"{role}_artifact_id"),
            size_bytes=getattr(args, f"{role}_artifact_size_bytes"),
            digest=getattr(args, f"{role}_artifact_digest"),
        )
        for role in ("primary", "control", "aggregate")
    }
    manifest = build_manifest(
        primary=args.primary,
        control=args.control,
        workflow_aggregate=args.workflow_aggregate,
        independent_primary=args.independent_primary,
        independent_control=args.independent_control,
        independent_aggregate=args.independent_aggregate,
        plan_path=args.plan,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        repository_commit=args.repository_commit,
        primary_job_id=args.primary_job_id,
        control_job_id=args.control_job_id,
        aggregate_job_id=args.aggregate_job_id,
        primary_artifact=artifacts["primary"],
        control_artifact=artifacts["control"],
        aggregate_artifact=artifacts["aggregate"],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
