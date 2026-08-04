#!/usr/bin/env python3
"""Retain E17b's terminal native timeout and resource-bound evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e2_ingest import elapsed_seconds
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e17b_freeze import INPUT_PATHS
    from experiments.e17b_ingest import (
        KV_ALLOCATION,
        validate_address_limit,
        validate_recipe,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e2_ingest import elapsed_seconds
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure
    from e17b_freeze import INPUT_PATHS
    from e17b_ingest import KV_ALLOCATION, validate_address_limit, validate_recipe


LOCAL_METADATA = {
    "artifact-metadata.json",
    "job-metadata.json",
    "run-metadata.json",
}
TIMEOUT_ERROR = re.compile(r"cancel task, id_task = \d+")
ALLOCATION_FAILURE = re.compile(
    r"insufficient memory \(attempted to allocate ([0-9.]+) MB\)"
)


def validate_frozen_inputs(evidence: Path, root: Path, contract: dict[str, Any]) -> None:
    for name, relative in INPUT_PATHS.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if contract["inputs"][f"{name}_path"] != relative.as_posix():
            raise ValueError(f"E17b {name} path differs")
        for path in (root / relative, evidence / "frozen-inputs" / relative):
            if sha256_file(path) != expected:
                raise ValueError(f"E17b {name} hash differs")


def artifact_inventory(evidence: Path) -> dict[str, Any]:
    entries: dict[str, str] = {}
    total = 0
    lines = []
    for path in sorted(item for item in evidence.rglob("*") if item.is_file()):
        relative = path.relative_to(evidence).as_posix()
        if relative in LOCAL_METADATA:
            continue
        digest = sha256_file(path)
        entries[relative] = digest
        total += path.stat().st_size
        lines.append(f"{digest}  {relative}\n")
    required = {
        "contract.json",
        "model-sha256.txt",
        "repository-commit.txt",
        "runtime/runtime-closure.json",
        *(f"cells/{index:02d}-{name}/caller-exit.txt" for index, name in (
            (1, "f16_f16-s4-r1"),
            (2, "q8_0_q8_0-s4-r1"),
            (3, "q4_0_q4_0-s4-r1"),
            (4, "q4_0_q4_0-s4-r2"),
            (5, "q8_0_q8_0-s4-r2"),
            (6, "f16_f16-s4-r2"),
            (7, "q4_0_q4_0-s8-r1"),
            (8, "q8_0_q8_0-s8-r1"),
            (9, "f16_f16-s8-r1"),
        )),
    }
    if not required.issubset(entries) or len(entries) < 100:
        raise ValueError("E17b artifact inventory is incomplete")
    return {
        "file_count": len(entries),
        "total_uncompressed_bytes": total,
        "inventory_sha256": hashlib.sha256("".join(lines).encode()).hexdigest(),
        "entries": entries,
    }


def validate_timeout_cell(
    path: Path,
    contract: dict[str, Any],
    configuration: str,
    slots: int,
    repetition: int,
) -> dict[str, Any]:
    validate_recipe(
        load_object(path / "recipe.json"),
        contract,
        configuration,
        slots,
        repetition,
    )
    readiness = load_object(path / "readiness.json")
    process = parse_time_output((path / "server-time.log").read_text())
    process["elapsed_seconds"] = elapsed_seconds(process["elapsed"])
    log = (path / "server.stderr.log").read_text(errors="replace")
    allocations = KV_ALLOCATION.findall(log)
    cancellations = TIMEOUT_ERROR.findall(log)
    expected_minimum_elapsed = contract["workload"]["request_timeout_seconds"]
    if slots == 4:
        expected_minimum_elapsed *= 2
    if (
        int((path / "caller-exit.txt").read_text().strip()) != 1
        or readiness.get("status") != "ok"
        or not isinstance(readiness.get("ready_ms"), (int, float))
        or process["exit_status"] != 0
        or process["elapsed_seconds"] < expected_minimum_elapsed
        or len(allocations) != 1
        or len(cancellations) < contract["workload"]["measured_tasks"]
        or (path / "probe.json").exists()
        or "prompt processing" not in log
        or "insufficient memory" in log
    ):
        raise ValueError(f"E17b timeout evidence differs for {path.name}")
    validate_address_limit(
        path / "process-limits-ready.txt",
        contract["execution"]["process_address_space_limit_bytes"],
    )
    return {
        "configuration": configuration,
        "slots": slots,
        "repetition": repetition,
        "served": False,
        "failure_class": "long_context_request_timeout",
        "readiness_ms": float(readiness["ready_ms"]),
        "request_timeout_seconds": contract["workload"]["request_timeout_seconds"],
        "request_waves": 2 if slots == 4 else 1,
        "cancelled_task_log_records": len(cancellations),
        "kv_allocation_mib": float(allocations[0]),
        "process": process,
        "maximum_rss_kib": process["maximum_rss_kib"],
        "recipe_sha256": sha256_file(path / "recipe.json"),
        "server_stderr_sha256": sha256_file(path / "server.stderr.log"),
        "probe_written": False,
    }


def validate_resource_cell(
    path: Path,
    contract: dict[str, Any],
    configuration: str,
    slots: int,
    repetition: int,
) -> dict[str, Any]:
    validate_recipe(
        load_object(path / "recipe.json"),
        contract,
        configuration,
        slots,
        repetition,
    )
    process = parse_time_output((path / "server-time.log").read_text())
    process["elapsed_seconds"] = elapsed_seconds(process["elapsed"])
    log = (path / "server.stderr.log").read_text(errors="replace")
    allocation = ALLOCATION_FAILURE.findall(log)
    if (
        int((path / "caller-exit.txt").read_text().strip()) != 1
        or process["exit_status"] != 1
        or len(allocation) != 1
        or float(allocation[0]) != 13312.0
        or "failed to allocate buffer of size 13958643712" not in log
        or "failed to allocate buffer for kv cache" not in log
        or (path / "readiness.json").exists()
        or (path / "probe.json").exists()
    ):
        raise ValueError("E17b f16 eight-slot resource evidence differs")
    return {
        "configuration": configuration,
        "slots": slots,
        "repetition": repetition,
        "served": False,
        "failure_class": "address_space_limited_kv_allocation_failure",
        "attempted_allocation_mib": float(allocation[0]),
        "attempted_allocation_bytes": 13_958_643_712,
        "process_address_space_limit_bytes": contract["execution"][
            "process_address_space_limit_bytes"
        ],
        "process": process,
        "recipe_sha256": sha256_file(path / "recipe.json"),
        "server_stderr_sha256": sha256_file(path / "server.stderr.log"),
        "readiness_written": False,
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
        contract.get("experiment_id") != "E17b"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E17b contract differs")
    validate_frozen_inputs(evidence, root, contract)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E17b failure artifact is not native Arm64")
    if load_object(evidence / "e9a-workflow-summary.json") != load_object(
        root / INPUT_PATHS["e9a_manifest"]
    ):
        raise ValueError("E17b E9a prerequisite differs")
    closure = validate_runtime_closure(evidence / "runtime/runtime-closure.json")
    server = evidence / "runtime/runtime-files/bin/llama-server"
    if sha256_file(server) != contract["runtime"]["server_sha256"]:
        raise ValueError("E17b server differs")
    model = (evidence / "model-sha256.txt").read_text().split()
    if len(model) != 2 or model[0] != contract["selected"]["model_sha256"]:
        raise ValueError("E17b model differs")

    cells = []
    for index, item in enumerate(contract["execution"]["cells"], start=1):
        name = (
            f"{index:02d}-{item['configuration']}-s{item['slots']}"
            f"-r{item['repetition']}"
        )
        path = evidence / "cells" / name
        cells.append(
            validate_resource_cell(path, contract, **item)
            if index == 9
            else validate_timeout_cell(path, contract, **item)
        )
    if len(cells) != 9:
        raise ValueError("E17b failure cell accounting differs")

    run = load_object(run_metadata)
    job = load_object(job_metadata)
    artifact = load_object(artifact_metadata)
    run_id = str(run.get("databaseId"))
    expected_artifact = f"e17b-long-context-density-{run_id}-1"
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("headSha") != job.get("head_sha")
        or str(job.get("run_id")) != run_id
        or job.get("run_attempt") != 1
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or job.get("conclusion") != "failure"
        or artifact.get("name") != expected_artifact
        or artifact.get("digest", "").startswith("sha256:") is not True
        or artifact.get("expired") is not False
        or str(artifact.get("workflow_run", {}).get("id")) != run_id
        or artifact.get("workflow_run", {}).get("head_sha") != run.get("headSha")
        or (evidence / "repository-commit.txt").read_text().strip()
        != run.get("headSha")
        or (evidence / "summary.json").exists()
    ):
        raise ValueError("E17b terminal run identity differs")

    timeout_cells = [cell for cell in cells if cell["failure_class"].endswith("timeout")]
    resource_cells = [
        cell for cell in cells if cell["failure_class"].endswith("allocation_failure")
    ]
    return {
        "schema_version": 1,
        "experiment_id": "E17b",
        "status": "invalid_frozen_16k_service_timeout_and_f16_density_resource_failure",
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
        },
        "runtime": {"artifact": contract["runtime"]["artifact"], "closure": closure},
        "selected": contract["selected"],
        "cells": cells,
        "failure_summary": {
            "all_nine_frozen_cells_attempted": True,
            "long_context_request_timeout_cells": len(timeout_cells),
            "f16_four_slot_control_timeout_cells": sum(
                cell["configuration"] == "f16_f16" and cell["slots"] == 4
                for cell in timeout_cells
            ),
            "quantized_four_slot_timeout_cells": sum(
                cell["configuration"] != "f16_f16" and cell["slots"] == 4
                for cell in timeout_cells
            ),
            "quantized_eight_slot_timeout_cells": sum(
                cell["configuration"] != "f16_f16" and cell["slots"] == 8
                for cell in timeout_cells
            ),
            "f16_eight_slot_resource_failure_cells": len(resource_cells),
            "valid_quality_or_performance_comparison_available": False,
            "frozen_hypothesis_evaluable": False,
        },
        "decision": {
            "promoted_long_context_configurations": [],
            "serving_density_win": False,
            "failed_contract_rehabilitated": False,
            "sixteen_k_claim_allowed": False,
            "separately_frozen_shorter_context_successor_allowed": True,
            "successor_must_not_be_reported_as_sixteen_k_evidence": True,
        },
        "validation": {
            "native_arm64": True,
            "exact_e9a_runtime_closure": True,
            "exact_selected_model": True,
            "all_frozen_inputs_match": True,
            "all_nine_cells_accounted_for": True,
            "all_eight_timeout_cells_reached_readiness": True,
            "all_eight_timeout_cells_hit_frozen_timeout": True,
            "f16_eight_slot_allocation_failure_verified": True,
            "no_answer_quality_or_speed_claim_from_incomplete_requests": True,
            "negative_result_preserved_without_gate_change": True,
        },
        "artifact_validation": artifact_inventory(evidence),
        "claim_boundary": (
            "E17b establishes only that the frozen 14.5K-token retrieval workload "
            "did not complete within its 600-second per-request contract on this "
            "four-vCPU native Arm64 runner, and that the f16 eight-slot configuration "
            "failed a 13,312 MiB KV allocation under the 15 GiB address-space ceiling. "
            "It makes no answer-quality, comparative-speed, 16K viability, energy, "
            "PMU, device, fleet, or cost claim."
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
