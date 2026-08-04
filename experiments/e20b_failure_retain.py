#!/usr/bin/env python3
"""Retain E20b's valid mechanism proof and terminal candidate assertion."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
    )
    from experiments.e20b_ingest import (
        validate_inputs,
        validate_preflight,
        validate_service_cell,
        validate_source_and_build,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, load_tasks, reference_predictions, sha256_file
    from e20b_ingest import (
        validate_inputs,
        validate_preflight,
        validate_service_cell,
        validate_source_and_build,
    )


LOCAL_METADATA = {
    "artifact-metadata.json",
    "job-metadata.json",
    "run-metadata.json",
}


def artifact_inventory(evidence: Path) -> dict[str, Any]:
    entries: dict[str, str] = {}
    lines = []
    total = 0
    for path in sorted(item for item in evidence.rglob("*") if item.is_file()):
        relative = path.relative_to(evidence).as_posix()
        if relative in LOCAL_METADATA:
            continue
        digest = sha256_file(path)
        entries[relative] = digest
        lines.append(f"{digest}  {relative}\n")
        total += path.stat().st_size
    required = {
        "contract.json",
        "source.json",
        "source-diff.patch",
        "build/runtime-closure.json",
        "preflight/reuse_off/stderr.log",
        "preflight/reuse_on/stderr.log",
        "cells/01-reuse_off-r1/probe.json",
        "cells/02-reuse_on-r1/server.stderr.log",
    }
    if len(entries) < 70 or not required.issubset(entries):
        raise ValueError("E20b artifact inventory is incomplete")
    return {
        "file_count": len(entries),
        "total_uncompressed_bytes": total,
        "inventory_sha256": hashlib.sha256("".join(lines).encode()).hexdigest(),
        "entries": entries,
    }


def validate_candidate_assertion(
    directory: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    recipe = load_object(directory / "recipe.json")
    expected_environment = contract["build"]["profiles"]["reuse_on"]["environment"]
    readiness = load_object(directory / "readiness.json")
    process_text = (directory / "server-time.log").read_text(errors="replace")
    process = parse_time_output(process_text)
    stderr = (directory / "server.stderr.log").read_text(errors="replace")
    assertion = (
        "/ggml/src/ggml-cpu/repack.cpp:4295: "
        "GGML_ASSERT(nb1 <= nb2) failed"
    )
    if (
        recipe.get("experiment_id") != "E20b"
        or recipe.get("profile_name") != "reuse_on"
        or recipe.get("environment") != expected_environment
        or readiness.get("status") != "ok"
        or not isinstance(readiness.get("ready_ms"), (int, float))
        or assertion not in stderr
        or "compute_forward_pair" not in stderr
        or "ggml_cpu_extra_compute_forward_pair" not in stderr
        or "Command terminated by signal 6" not in process_text
        or "GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION=1" not in process_text
        or (directory / "probe.json").exists()
        or (directory / "server-shell-exit.txt").exists()
        or (directory / "metrics.txt").exists()
        or (directory / "slots.json").exists()
    ):
        raise ValueError("E20b candidate assertion evidence differs")
    return {
        "profile": "reuse_on",
        "repetition": 1,
        "served": False,
        "failure_class": "candidate_process_sigabrt_noncontiguous_output_assertion",
        "readiness_ms": float(readiness["ready_ms"]),
        "signal": 6,
        "assertion": assertion,
        "backtrace_contains_pair_path": True,
        "process": process,
        "recipe_sha256": sha256_file(directory / "recipe.json"),
        "server_stderr_sha256": sha256_file(directory / "server.stderr.log"),
        "probe_written": False,
    }


def retain(
    *,
    evidence: Path,
    contract_path: Path,
    root: Path,
    run_metadata: Path,
    job_metadata: Path,
    artifact_metadata: Path,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("experiment_id") != "E20b"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E20b contract differs")
    validate_inputs(evidence, root, contract)
    source, build = validate_source_and_build(evidence, contract)
    preflight = validate_preflight(evidence, contract)

    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    selected_manifest = load_object(root / contract["inputs"]["manifest_path"])
    candidate = contract["selected"]["candidate"]
    references = reference_predictions(selected_manifest, candidate)
    control = validate_service_cell(
        evidence / "cells/01-reuse_off-r1",
        "reuse_off",
        1,
        contract,
        tasks,
        references,
    )
    if (
        control["probe"]["correct"] != contract["selected"]["reference_correct"]
        or control["probe"]["reference_prediction_mismatches"] != 0
    ):
        raise ValueError("E20b completed control quality differs")
    candidate_failure = validate_candidate_assertion(
        evidence / "cells/02-reuse_on-r1", contract
    )
    if any((evidence / "cells" / name).exists() for name in (
        "03-reuse_on-r2",
        "04-reuse_off-r2",
        "05-reuse_off-r3",
        "06-reuse_on-r3",
        "07-reuse_on-r4",
        "08-reuse_off-r4",
        "09-reuse_off-r5",
        "10-reuse_on-r5",
        "11-reuse_on-r6",
        "12-reuse_off-r6",
    )):
        raise ValueError("E20b unexpectedly contains post-assertion service cells")

    run = load_object(run_metadata)
    job = load_object(job_metadata)
    artifact = load_object(artifact_metadata)
    run_id = str(run.get("databaseId"))
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("headSha") != job.get("head_sha")
        or str(job.get("run_id")) != run_id
        or job.get("run_attempt") != 1
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or job.get("conclusion") != "failure"
        or artifact.get("name") != f"e20b-repack-pair-{run_id}-1"
        or artifact.get("digest", "").startswith("sha256:") is not True
        or artifact.get("expired") is not False
        or str(artifact.get("workflow_run", {}).get("id")) != run_id
        or artifact.get("workflow_run", {}).get("head_sha") != run.get("headSha")
        or (evidence / "summary.json").exists()
    ):
        raise ValueError("E20b terminal identity differs")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E20b failure artifact is not native Arm64")
    return {
        "schema_version": 1,
        "experiment_id": "E20b",
        "status": "invalid_repack_pair_candidate_assertion_after_valid_mechanism_preflight",
        "contract_sha256": sha256_file(contract_path),
        "github": {
            "run_id": run_id,
            "run_attempt": 1,
            "run_url": run["url"],
            "job_id": str(job["id"]),
            "repository_commit": run["headSha"],
            "artifact_name": artifact["name"],
            "artifact_id": str(artifact["id"]),
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": artifact["digest"],
            "artifact_expires_at": artifact["expires_at"],
        },
        "platform": {
            **platform,
            "uname": (evidence / "uname.txt").read_text().strip(),
            "compiler": (evidence / "compiler.txt").read_text().strip(),
        },
        "source": source,
        "build": build,
        "mechanism_preflight": preflight,
        "completed_control": control,
        "candidate_failure": candidate_failure,
        "failure_summary": {
            "mechanism_preflight_valid": True,
            "control_expected_separate_ffn_nodes": 52,
            "candidate_expected_fused_ffn_pairs": 26,
            "completed_service_cells": 1,
            "candidate_crash_cells": 1,
            "unattempted_service_cells": 10,
            "valid_quality_comparison_available": False,
            "valid_performance_comparison_available": False,
            "frozen_hypothesis_evaluable": False,
        },
        "decision": {
            "optimization_promoted": False,
            "failed_contract_rehabilitated": False,
            "original_patch_safe_for_service": False,
            "separately_frozen_stricter_predicate_successor_allowed": True,
            "successor_must_reprove_mechanism_before_service_measurement": True,
            "automatic_product_promotion_allowed": False,
        },
        "validation": {
            "native_arm64": True,
            "all_frozen_inputs_match": True,
            "exact_source_and_patch_series_verified": True,
            "exact_model_verified": True,
            "single_binary_for_control_and_candidate": True,
            "mechanism_counts_verified": True,
            "control_exact_quality_verified": True,
            "candidate_sigabrt_verified": True,
            "no_partial_quality_or_speed_claim": True,
            "negative_result_preserved_without_gate_change": True,
        },
        "artifact_validation": artifact_inventory(evidence),
        "claim_boundary": (
            "E20b establishes only that the patched native Arm64 binary produced "
            "the exact frozen 52-to-26 FFN mechanism count on pp512, then aborted "
            "during its first candidate service cell on a non-contiguous-output "
            "stride assertion. It establishes no candidate quality, speed, CPU, "
            "latency, memory, energy, PMU, fleet, or cost result."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--job-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        root=args.root,
        run_metadata=args.run_metadata,
        job_metadata=args.job_metadata,
        artifact_metadata=args.artifact_metadata,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
