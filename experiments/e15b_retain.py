#!/usr/bin/env python3
"""Retain the independently reproduced E15b affinity result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


RUNTIME_ALIASES = {
    "runtime/runtime-files/bin/libggml-base.so.0": "runtime/runtime-files/bin/libggml-base.so.0.18.0",
    "runtime/runtime-files/bin/libggml-cpu.so.0": "runtime/runtime-files/bin/libggml-cpu.so.0.18.0",
    "runtime/runtime-files/bin/libggml.so.0": "runtime/runtime-files/bin/libggml.so.0.18.0",
    "runtime/runtime-files/bin/libllama-common.so.0": "runtime/runtime-files/bin/libllama-common.so.0.0.10216",
    "runtime/runtime-files/bin/libllama.so.0": "runtime/runtime-files/bin/libllama.so.0.0.10216",
    "runtime/runtime-files/bin/libmtmd.so.0": "runtime/runtime-files/bin/libmtmd.so.0.0.10216",
}
LOCAL_METADATA = {"artifact.json", "job.json", "job.log", "summary-local.json"}


def validate_inventory(evidence: Path, run_id: str, run_attempt: int) -> dict[str, Any]:
    inventory_path = evidence / "file-inventory-sha256.txt"
    marker = f"/results/raw/e15b-{run_id}-{run_attempt}/"
    entries: dict[str, str] = {}
    for line in inventory_path.read_text(encoding="utf-8").splitlines():
        digest, absolute = line.split("  ", 1)
        if len(digest) != 64 or marker not in absolute:
            raise ValueError("E15b artifact inventory line is invalid")
        relative = absolute.split(marker, 1)[1]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in entries:
            raise ValueError("E15b artifact inventory path is unsafe or duplicate")
        local = evidence / path
        if not local.is_file() or sha256_file(local) != digest:
            raise ValueError(f"E15b artifact inventory differs for {relative}")
        entries[relative] = digest
    actual = {
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file()
        and path.name not in {"file-inventory-sha256.txt", *LOCAL_METADATA}
    }
    unlisted = actual - set(entries)
    expected_unlisted = {"disk-after.txt", *RUNTIME_ALIASES}
    if any(
        sha256_file(evidence / alias) != sha256_file(evidence / target)
        for alias, target in RUNTIME_ALIASES.items()
    ):
        raise ValueError("E15b materialized runtime alias differs")
    if set(entries) - actual or unlisted != expected_unlisted:
        raise ValueError("E15b artifact inventory file set differs")
    return {
        "file_count": len(entries),
        "inventory_sha256": sha256_file(inventory_path),
        "files_outside_runner_regular_file_inventory": {
            relative: sha256_file(evidence / relative) for relative in sorted(unlisted)
        },
        "all_retained_file_hashes_verified": True,
    }


def validate_github(
    *,
    github: dict[str, Any],
    job: dict[str, Any],
    artifact: dict[str, Any],
    run_id: str,
    run_attempt: int,
) -> None:
    expected_sha = "fef62442316adcb4ccc4ae05fa1c8504fa595040"
    if (
        github.get("run_id") != run_id
        or github.get("run_attempt") != run_attempt
        or github.get("sha") != expected_sha
        or str(job.get("run_id")) != run_id
        or str(job.get("id")) != "91812704259"
        or job.get("conclusion") != "success"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or job.get("head_sha") != expected_sha
        or str(artifact.get("id")) != "8871235428"
        or artifact.get("name") != f"e15b-affinity-split-scheduler-{run_id}-1"
        or artifact.get("digest")
        != "sha256:f25c9faf66e445d070613cabfed589091cd222d88496a40c5ae1c6745a43d5cd"
        or artifact.get("workflow_run", {}).get("head_sha") != expected_sha
        or str(artifact.get("workflow_run", {}).get("id")) != run_id
    ):
        raise ValueError("E15b GitHub provenance differs")


def build_manifest(
    *,
    evidence: Path,
    contract_path: Path,
    independent_summary_path: Path,
    job_path: Path,
    artifact_path: Path,
    job_log_path: Path,
    run_id: str,
    run_attempt: int,
) -> dict[str, Any]:
    summary_path = evidence / "summary.json"
    summary = load_object(summary_path)
    independent = load_object(independent_summary_path)
    github = load_object(evidence / "github.json")
    job = load_object(job_path)
    artifact = load_object(artifact_path)
    split = summary.get("decision", {}).get("profile_gates", {}).get("split2_4", {})
    performance = summary.get("performance", {})
    if (
        summary != independent
        or summary.get("status") != "valid_affinity_split_scheduler_no_promotion"
        or summary.get("contract_sha256") != sha256_file(contract_path)
        or summary.get("decision", {}).get("passed") is not False
        or summary.get("decision", {}).get("selected_configuration") != "tied4_4"
        or split.get("eligible") is not False
        or split.get("cpu_time_passed") is not False
        or split.get("ratios", {}).get("cpu_seconds_per_request") != 1.0
        or set(performance) != {"tied4_4", "split2_4"}
        or any(len(point.get("repetitions", [])) != 6 for point in performance.values())
        or any(
            point.get("quality", {}).get("exact_selected_predictions") is not True
            for point in performance.values()
        )
        or summary.get("validation", {}).get("all_server_threads_two_cpu_affinity")
        is not True
        or "valid_affinity_split_scheduler_no_promotion"
        not in job_log_path.read_text(errors="replace")
    ):
        raise ValueError("E15b retained result differs")
    validate_github(
        github=github,
        job=job,
        artifact=artifact,
        run_id=run_id,
        run_attempt=run_attempt,
    )
    return {
        **summary,
        "github": {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "job_id": str(job["id"]),
            "repository_commit": github["sha"],
            "artifact_name": artifact["name"],
            "artifact_id": str(artifact["id"]),
            "artifact_size_bytes": artifact["size_in_bytes"],
            "artifact_digest": artifact["digest"],
            "artifact_expires_at": artifact["expires_at"],
        },
        "artifact_validation": {
            "workflow_summary_sha256": sha256_file(summary_path),
            "independent_summary_sha256": sha256_file(independent_summary_path),
            "independent_summary_byte_identical": True,
            "job_log_sha256": sha256_file(job_log_path),
            "inventory": validate_inventory(evidence, run_id, run_attempt),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--independent-summary", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--job-log", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        independent_summary_path=args.independent_summary,
        job_path=args.job,
        artifact_path=args.artifact,
        job_log_path=args.job_log,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
