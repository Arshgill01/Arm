#!/usr/bin/env python3
"""Retain E15a's complete but topology-invalid native Arm experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
    )
    from experiments.e15a_split_scheduler_ingest import (
        evaluate,
        summarize_performance,
        validate_cell,
        validate_inputs,
        validate_runtime,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, load_tasks, reference_predictions, sha256_file
    from e15a_split_scheduler_ingest import (
        evaluate,
        summarize_performance,
        validate_cell,
        validate_inputs,
        validate_runtime,
    )


def inventory(directory: Path) -> dict[str, Any]:
    rows = []
    total_bytes = 0
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        size = path.stat().st_size
        rows.append({"path": relative, "size_bytes": size, "sha256": sha256_file(path)})
        total_bytes += size
    if not rows:
        raise ValueError("E15a artifact is empty")
    return {
        "all_extracted_regular_files_hashed": True,
        "file_count": len(rows),
        "total_regular_file_bytes": total_bytes,
        "files": rows,
    }


def retain(
    *,
    evidence: Path,
    contract_path: Path,
    root: Path,
    run_log: Path,
    run_metadata: Path,
    job_metadata: Path,
    artifact_metadata: Path,
) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    runtime = validate_runtime(evidence, contract)
    run = load_object(run_metadata)
    job = load_object(job_metadata)
    artifact = load_object(artifact_metadata)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    expected_platform = {
        "architecture": contract["acceptance"]["required_architecture"],
        "logical_cpus": contract["acceptance"]["required_logical_cpus"],
        "model_name": contract["acceptance"]["required_model_name"],
    }
    if (
        platform["architecture"] != expected_platform["architecture"]
        or platform["model_name"] != expected_platform["model_name"]
        or platform["logical_cpus"] == expected_platform["logical_cpus"]
    ):
        raise ValueError("E15a failure is not the retained logical-CPU mismatch")
    log_text = run_log.read_text(errors="replace")
    required_log_fragments = (
        'test "$index" -eq 16',
        "E15a native runner topology differs",
        "Process completed with exit code 1",
    )
    if not all(fragment in log_text for fragment in required_log_fragments):
        raise ValueError("E15a run log lacks the retained topology failure")
    github = load_object(evidence / "github.json")
    if (
        str(run.get("id")) != github.get("run_id")
        or run.get("run_attempt") != github.get("run_attempt")
        or run.get("head_sha") != github.get("sha")
        or run.get("conclusion") != "failure"
        or str(job.get("id")) != "91805076924"
        or job.get("conclusion") != "failure"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or str(artifact.get("id")) != "8870310205"
        or artifact.get("name") != "e15a-split-scheduler-30849270574-1"
        or artifact.get("digest")
        != "sha256:6eb27a160f1d16135de752a0c1432f6591c298a62592f07def7bd15a81dd3948"
    ):
        raise ValueError("E15a GitHub identity differs")
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if (
        len(model_line) != 2
        or model_line[0] != contract["selected"]["model_sha256"]
        or int((evidence / "model-size.txt").read_text())
        != contract["selected"]["model_size_bytes"]
    ):
        raise ValueError("E15a retained model identity differs")
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["manifest_path"]),
        contract["selected"]["candidate"],
    )
    cells = []
    samples = {name: [] for name in contract["execution"]["configurations"]}
    for index, item in enumerate(contract["execution"]["order"], start=1):
        name = item["configuration"]
        repetition = item["repetition"]
        cell, raw = validate_cell(
            evidence / "cells" / f"{index:02d}-{name}-r{repetition}",
            configuration=name,
            repetition=repetition,
            contract=contract,
            tasks=tasks,
            references=references,
        )
        cells.append(cell)
        samples[name].extend({**case, "repetition": repetition} for case in raw)
    performance = summarize_performance(cells, samples, contract)
    counterfactual_decision = evaluate(performance, contract)
    files = inventory(evidence)
    return {
        "schema_version": 1,
        "experiment_id": "E15a",
        "status": "invalid_native_runner_topology_mismatch",
        "experiment_result_valid": False,
        "promotion_decision_permitted": False,
        "contract_sha256": sha256_file(contract_path),
        "failure": {
            "type": "frozen_runner_topology_mismatch",
            "message": "E15a native runner topology differs",
            "measurement_step_completed": True,
            "independent_validation_reached": True,
            "independent_validation_passed": False,
            "expected_platform": expected_platform,
            "observed_platform": {
                "architecture": platform["architecture"],
                "logical_cpus": platform["logical_cpus"],
                "model_name": platform["model_name"],
            },
        },
        "github": {
            "run_id": str(run["id"]),
            "run_attempt": run["run_attempt"],
            "job_id": str(job["id"]),
            "repository_commit": run["head_sha"],
            "conclusion": run["conclusion"],
            "run_url": run["html_url"],
            "run_log_sha256": sha256_file(run_log),
            "artifact_id": str(artifact["id"]),
            "artifact_name": artifact["name"],
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": artifact["digest"],
            "artifact_expires_at": artifact["expires_at"],
            "runner_name": job["runner_name"],
            "runner_labels": job["labels"],
        },
        "platform": platform,
        "runtime": runtime,
        "model": contract["selected"],
        "artifact_validation": files,
        "raw_cells_validated": len(cells),
        "raw_measured_requests_validated": sum(
            len(values) for values in samples.values()
        ),
        "descriptive_performance_under_unfrozen_four_cpu_topology": performance,
        "counterfactual_gate_result_not_eligible_for_promotion": counterfactual_decision,
        "decision": {
            "e15a_promoted": False,
            "treat_four_cpu_measurements_as_confirmatory": False,
            "change_frozen_required_logical_cpus_after_observation": False,
            "raw_measurements_retained": True,
            "separately_frozen_affinity_control_successor_allowed": True,
        },
        "claim_boundary": (
            "All 16 fresh-process cells and 480 exact requests completed and validate "
            "structurally, but the GitHub-hosted runner exposed four logical CPUs "
            "instead of the frozen two. The raw four-CPU measurements are descriptive "
            "invalid evidence only and cannot promote a scheduler recipe or be "
            "retroactively admitted by changing the topology gate."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--job-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        root=args.root,
        run_log=args.run_log,
        run_metadata=args.run_metadata,
        job_metadata=args.job_metadata,
        artifact_metadata=args.artifact_metadata,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": result["status"],
                "raw_cells_validated": result["raw_cells_validated"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
