#!/usr/bin/env python3
"""Retain E14a's complete cells and invalid mechanism instrumentation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, summarize
    from experiments.e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
    )
    from experiments.e5h_ingest import parse_model_buffers
    from experiments.e5j_ingest import validate_process_cpu
    from experiments.e14a_ingest import (
        parse_excluded_tensors,
        validate_e14a_cell,
        validate_inputs,
        validate_invocation,
        validate_source_build,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, summarize
    from e5b_ingest import load_object, load_tasks, reference_predictions, sha256_file
    from e5h_ingest import parse_model_buffers
    from e5j_ingest import validate_process_cpu
    from e14a_ingest import (
        parse_excluded_tensors,
        validate_e14a_cell,
        validate_inputs,
        validate_invocation,
        validate_source_build,
    )


def extracted_inventory(evidence: Path) -> dict[str, Any]:
    entries: list[str] = []
    total_bytes = 0
    for path in sorted(item for item in evidence.rglob("*") if item.is_file()):
        relative = path.relative_to(evidence).as_posix()
        size = path.stat().st_size
        entries.append(f"{sha256_file(path)}  {relative}\n")
        total_bytes += size
    if not entries:
        raise ValueError("E14a artifact is empty")
    return {
        "file_count": len(entries),
        "total_regular_file_bytes": total_bytes,
        "inventory_sha256": hashlib.sha256("".join(entries).encode()).hexdigest(),
        "all_extracted_regular_files_hashed": True,
    }


def summarize_observed_cells(
    cells: list[dict[str, Any]],
    probes: dict[tuple[str, int], dict[str, Any]],
    cpu: dict[tuple[str, int], dict[str, float | int]],
    configurations: dict[str, dict[str, Any]],
    reference_correct: int,
) -> dict[str, Any]:
    performance: dict[str, Any] = {}
    for name, config in configurations.items():
        selected = [cell for cell in cells if cell["configuration"] == name]
        selected_probes = [probes[(name, int(cell["repetition"]))] for cell in selected]
        raw_cases = [case for probe in selected_probes for case in probe["cases"]]
        prediction_maps = [
            {case["id"]: case["predicted"] for case in probe["cases"]}
            for probe in selected_probes
        ]
        selected_cpu = [cpu[(name, int(cell["repetition"]))] for cell in selected]
        performance[name] = {
            "weight_repack": config["weight_repack"],
            "exclusion_regex": config["exclusion_regex"],
            "quality": {
                "exact_selected_predictions": all(
                    cell["probe"]["correct"] == reference_correct
                    and cell["probe"]["reference_prediction_mismatches"] == 0
                    for cell in selected
                )
                and all(value == prediction_maps[0] for value in prediction_maps[1:]),
                "correct_per_repetition": [
                    cell["probe"]["correct"] for cell in selected
                ],
                "reference_prediction_mismatches_per_repetition": [
                    cell["probe"]["reference_prediction_mismatches"]
                    for cell in selected
                ],
            },
            "requests_per_second": summarize(
                [cell["probe"]["requests_per_second"] for cell in selected]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in raw_cases]),
            "server_cpu_seconds_per_request": summarize(
                [float(item["seconds_per_request"]) for item in selected_cpu]
            ),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in selected]
            ),
            "ready_ms": summarize([float(cell["ready_ms"]) for cell in selected]),
        }
    return performance


def build_manifest(
    *,
    evidence: Path,
    contract_path: Path,
    root: Path,
    run_id: str,
    run_attempt: int,
    job_id: str,
    artifact_name: str,
    artifact_id: str,
    artifact_size_bytes: int,
    artifact_digest: str,
) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E14a failure evidence is not native Arm64")
    source_build = validate_source_build(evidence, contract)
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["manifest_path"]),
        contract["selected"]["candidate"],
    )
    configurations = contract["execution"]["configurations"]
    cells: list[dict[str, Any]] = []
    probes: dict[tuple[str, int], dict[str, Any]] = {}
    cpu: dict[tuple[str, int], dict[str, float | int]] = {}
    missing_instrumentation: dict[str, Any] = {}
    for index, item in enumerate(contract["execution"]["order"], start=1):
        name = item["configuration"]
        repetition = int(item["repetition"])
        config = configurations[name]
        cell_dir = evidence / "cells" / f"{index:02d}-{name}-r{repetition}"
        validate_invocation(cell_dir, config)
        cell = validate_e14a_cell(
            cell_dir,
            configuration=name,
            repetition=repetition,
            config=config,
            contract=contract,
            tasks=tasks,
            references=references,
        )
        cells.append(cell)
        probe = load_object(cell_dir / "probe.json")
        probes[(name, repetition)] = probe
        cpu[(name, repetition)] = validate_process_cpu(
            probe,
            cell_dir=cell_dir,
            measured_requests=contract["request"]["measured_tasks"],
        )
        log = (cell_dir / "server.stderr.log").read_text(errors="replace")
        parse_error = None
        try:
            parse_model_buffers(log, config=config)
        except ValueError as error:
            parse_error = str(error)
        if parse_error != "mechanism log lacks the mapped model buffer":
            raise ValueError(f"{cell_dir.name} did not reproduce the E14a blocker")
        missing_instrumentation[cell_dir.name] = {
            "mapped_buffer_line_present": False,
            "repack_buffer_line_present": False,
            "excluded_tensor_lines_observed": len(parse_excluded_tensors(log)),
            "parser_error": parse_error,
        }

    provenance = load_object(evidence / "provenance.json")
    values = (run_id, job_id, artifact_id)
    if (
        not all(value.isdigit() for value in values)
        or artifact_size_bytes <= 0
        or not artifact_digest.startswith("sha256:")
        or len(artifact_digest.removeprefix("sha256:")) != 64
        or provenance.get("experiment_id") != "E14a"
        or provenance.get("github_run_id") != run_id
        or provenance.get("github_run_attempt") != run_attempt
        or provenance.get("runner_arch") != "ARM64"
    ):
        raise ValueError("E14a GitHub provenance differs")
    performance = summarize_observed_cells(
        cells,
        probes,
        cpu,
        configurations,
        contract["selected"]["reference_correct"],
    )
    if not all(
        point["quality"]["exact_selected_predictions"] for point in performance.values()
    ):
        raise ValueError("E14a observed cells do not preserve exact selected quality")
    if any(
        not math.isfinite(point["requests_per_second"]["median"])
        or point["requests_per_second"]["median"] <= 0
        for point in performance.values()
    ):
        raise ValueError("E14a observed throughput is invalid")
    return {
        "schema_version": 1,
        "experiment_id": "E14a",
        "status": "invalid_incomplete_mechanism_instrumentation",
        "experiment_result_valid": False,
        "promotion_decision_permitted": False,
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "source_build": source_build,
        "completed_cells": len(cells),
        "completed_measured_requests": sum(
            len(probe["cases"]) for probe in probes.values()
        ),
        "observed_performance_descriptive_only": performance,
        "instrumentation_failure": {
            "required_log_verbosity": 4,
            "observed_recipe_log_verbosity": None,
            "default_runtime_log_verbosity": 3,
            "failed_ingester_requirement": "CPU_Mapped model buffer size",
            "cells": missing_instrumentation,
            "repair_boundary": (
                "A successor may add --log-verbosity 4 to every cell while keeping "
                "all configurations, order, repetitions, requests, and acceptance "
                "thresholds byte-for-byte identical. E14a remains invalid."
            ),
        },
        "github": {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "job_id": job_id,
            "repository_commit": provenance["git_commit"],
            "artifact_name": artifact_name,
            "artifact_id": artifact_id,
            "artifact_size_bytes": artifact_size_bytes,
            "artifact_digest": artifact_digest,
        },
        "artifact_validation": extracted_inventory(evidence),
        "claim_boundary": (
            "The eight measurements are retained only as descriptive failed-run "
            "evidence. They cannot select or promote a repack configuration because "
            "the frozen mechanism proof was not captured."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact-size-bytes", type=int, required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        root=args.root,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        job_id=args.job_id,
        artifact_name=args.artifact_name,
        artifact_id=args.artifact_id,
        artifact_size_bytes=args.artifact_size_bytes,
        artifact_digest=args.artifact_digest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
