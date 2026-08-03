#!/usr/bin/env python3
"""Retain E17a's subset-reference probe failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file


RUN_ID = "30855793293"
JOB_ID = "91826376788"
ARTIFACT_ID = "8872425138"
ARTIFACT_NAME = "e17a-kv-v-cache-preflight-30855793293-1"
ARTIFACT_DIGEST = "sha256:b818da16524ce873ea61b90c4da23f34d3499965356f8b5cf9f97d19148e1f39"
EXPECTED_ALLOCATIONS = {
    "f16_f16": 104.0,
    "q8_0_q8_0": 55.25,
    "q4_0_q4_0": 29.25,
}
ALLOCATION = re.compile(r"CPU KV buffer size =\s+([0-9.]+) MiB")

SUPPLEMENTAL = {
    "artifact-inventory-sha256.txt",
    "github-artifact.json",
    "github-run.json",
    "github-run.log",
}


def git_blob(root: Path, commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def artifact_inventory(evidence: Path) -> dict[str, Any]:
    entries: list[str] = []
    total_bytes = 0
    files = (item for item in evidence.rglob("*") if item.is_file())
    for item in sorted(files, key=lambda value: value.relative_to(evidence).as_posix()):
        relative = item.relative_to(evidence).as_posix()
        if relative in SUPPLEMENTAL:
            continue
        entries.append(f"{sha256_file(item)}  {relative}\n")
        total_bytes += item.stat().st_size
    inventory = evidence / "artifact-inventory-sha256.txt"
    if inventory.read_text() != "".join(entries):
        raise ValueError("E17a probe failure artifact inventory differs")
    return {
        "file_count": len(entries),
        "total_regular_file_bytes": total_bytes,
        "inventory_sha256": sha256_file(inventory),
        "all_extracted_regular_files_hashed": True,
    }


def build_manifest(evidence: Path, contract_relative: str, root: Path) -> dict[str, Any]:
    run = load_object(evidence / "github-run.json")
    artifact = load_object(evidence / "github-artifact.json")
    jobs = run.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 1:
        raise ValueError("E17a probe failure job metadata differs")
    job = jobs[0]
    failed_steps = [
        step for step in job.get("steps", []) if step.get("conclusion") == "failure"
    ]
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or str(job.get("databaseId")) != JOB_ID
        or len(failed_steps) != 1
        or failed_steps[0].get("name") != "Independently validate bounded preflight"
        or artifact.get("id") != int(ARTIFACT_ID)
        or artifact.get("name") != ARTIFACT_NAME
        or artifact.get("digest") != ARTIFACT_DIGEST
    ):
        raise ValueError("E17a probe failure provenance differs")
    contract_bytes = git_blob(root, run["headSha"], contract_relative)
    contract = json.loads(contract_bytes)
    if contract.get("experiment_id") != "E17a" or load_object(evidence / "contract.json") != contract:
        raise ValueError("E17a probe failure contract differs")
    if load_object(evidence / "first-failure.json") != load_object(
        root / "results/manifests/e17a-30855155720.json"
    ):
        raise ValueError("E17a first failure was not retained")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError("E17a probe failure is not native Arm64")

    launches: dict[str, Any] = {}
    for index, configuration in enumerate(contract["execution"]["order"], start=1):
        cell = evidence / f"cells/{index:02d}-{configuration}"
        readiness = load_object(cell / "readiness.json")
        recipe = load_object(cell / "recipe.json")
        log = (cell / "server.stderr.log").read_text(errors="replace")
        allocation = ALLOCATION.findall(log)
        if (
            readiness.get("status") != "ok"
            or recipe.get("configuration") != configuration
            or int((cell / "caller-exit.txt").read_text()) == 0
            or (cell / "probe.json").exists()
            or len(allocation) != 1
            or float(allocation[0]) != EXPECTED_ALLOCATIONS[configuration]
            or "flash_attn    = enabled" not in log
        ):
            raise ValueError(f"E17a failed launch evidence differs for {configuration}")
        launches[configuration] = {
            "server_ready": True,
            "readiness_ms": readiness["ready_ms"],
            "flash_attention_enabled": True,
            "kv_allocation_mib": float(allocation[0]),
            "model_requests_completed": 0,
            "recipe_sha256": sha256_file(cell / "recipe.json"),
            "server_stderr_sha256": sha256_file(cell / "server.stderr.log"),
        }

    run_log = (evidence / "github-run.log").read_text(errors="replace")
    if run_log.count("ValueError: task IDs differ from the selected reference predictions") != 3:
        raise ValueError("E17a subset-reference probe failure count differs")
    return {
        "schema_version": 1,
        "experiment_id": "E17a",
        "status": "invalid_premeasurement_subset_reference_probe_failure",
        "experiment_result_valid": False,
        "configuration_processes_started": 3,
        "configuration_processes_ready": 3,
        "measured_model_requests_completed": 0,
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "platform": platform,
        "descriptive_launch_evidence": launches,
        "failure": {
            "stage": "pre-request reference-map validation",
            "exception": "ValueError: task IDs differ from the selected reference predictions",
            "cause": (
                "The reused E5b probe requires the task ID set to equal the full 30-task "
                "reference map, while E17a intentionally froze a three-task diagnostic subset."
            ),
            "repair_boundary": (
                "A separately frozen successor may add a subset-aware adapter that loads "
                "the same stable reference map and filters it to the three already-frozen "
                "task IDs before calling the unchanged request engine. Nothing else changes."
            ),
        },
        "github": {
            "run_id": RUN_ID,
            "run_attempt": 1,
            "run_url": run["url"],
            "job_id": JOB_ID,
            "repository_commit": run["headSha"],
            "artifact_name": ARTIFACT_NAME,
            "artifact_id": ARTIFACT_ID,
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": ARTIFACT_DIGEST,
            "run_log_sha256": sha256_file(evidence / "github-run.log"),
        },
        "artifact_validation": artifact_inventory(evidence),
        "decision": {
            "compatibility_result_accepted": False,
            "long_context_successor_allowed": False,
            "descriptive_launch_values_promoted": False,
            "failed_runs_rehabilitated": False,
            "separately_frozen_subset_probe_repair_allowed": True,
        },
        "claim_boundary": (
            "All three native servers reached readiness and logged descriptive KV allocations, "
            "but no measured model request ran. This is not accepted KV compatibility, answer, "
            "quality, performance, long-context, energy, PMU, device, fleet, or cost evidence."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract-relative", default="experiments/e17a_successor_contract.json")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract_relative, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
