#!/usr/bin/env python3
"""Recover E20a by replaying only its corrected deterministic selector."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e20a_ingest import build_manifest
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e20a_ingest import build_manifest


def validate_inventory(evidence: Path, retained: dict[str, Any]) -> dict[str, Any]:
    files = retained.get("files")
    if not isinstance(files, list):
        raise TypeError("E20a retained source inventory differs")
    expected = {item.get("path"): item for item in files}
    observed = sorted(
        item.relative_to(evidence).as_posix()
        for item in evidence.rglob("*")
        if item.is_file()
    )
    if len(expected) != len(files) or observed != sorted(expected):
        raise ValueError("E20a extracted source artifact file set differs")
    total = 0
    for relative in observed:
        item = expected[relative]
        path = evidence / relative
        size = path.stat().st_size
        if item.get("size_bytes") != size or item.get("sha256") != sha256_file(path):
            raise ValueError(f"E20a extracted source artifact differs: {relative}")
        total += size
    if (
        retained.get("file_count") != len(observed)
        or retained.get("total_regular_file_bytes") != total
    ):
        raise ValueError("E20a extracted source artifact totals differ")
    return {
        "file_count": len(observed),
        "total_regular_file_bytes": total,
        "all_extracted_regular_files_verified": True,
    }


def validate_github(
    failure: dict[str, Any],
    run: dict[str, Any],
    job: dict[str, Any],
    artifacts: dict[str, Any],
) -> dict[str, Any]:
    github = failure["github"]
    selected = [
        item
        for item in artifacts.get("artifacts", [])
        if str(item.get("id")) == github["artifact_id"]
    ]
    if (
        str(run.get("id")) != str(github["run_id"])
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("head_sha") != github["repository_commit"]
        or str(job.get("id")) != str(github["job_id"])
        or str(job.get("run_id")) != str(github["run_id"])
        or job.get("status") != "completed"
        or job.get("conclusion") != "failure"
        or job.get("labels") != ["ubuntu-24.04-arm"]
        or len(selected) != 1
        or selected[0].get("name") != github["artifact_name"]
        or selected[0].get("digest") != github["artifact_digest"]
        or selected[0].get("expired") is not False
    ):
        raise ValueError("E20a source GitHub identity differs")
    return selected[0]


def recover(
    *,
    evidence: Path,
    contract_path: Path,
    root: Path,
    source_run_metadata: Path,
    source_job_metadata: Path,
    source_artifact_metadata: Path,
    recovery_run_id: str,
    recovery_run_attempt: int,
    recovery_head_sha: str,
) -> tuple[dict[str, Any], bytes]:
    contract = load_object(contract_path)
    if (
        contract.get("experiment_id") != "E20a-ingestion-recovery"
        or not recovery_run_id.isdigit()
        or recovery_run_attempt != 1
        or re.fullmatch(r"[0-9a-f]{40}", recovery_head_sha) is None
    ):
        raise ValueError("E20a recovery identity differs")
    for name, relative in contract["inputs"].items():
        if name.endswith("_path"):
            expected = contract["inputs"][name.removesuffix("_path") + "_sha256"]
            if sha256_file(root / relative) != expected:
                raise ValueError(f"E20a recovery input differs: {relative}")
    failure = load_object(root / contract["inputs"]["failure_manifest_path"])
    if (
        failure.get("status")
        != "invalid_post_profile_ingestion_failure_with_complete_replay"
        or failure.get("decision", {}).get("inspection_only_native_recovery_allowed")
        is not True
    ):
        raise ValueError("E20a recovery prerequisite differs")
    source_inventory = validate_inventory(evidence, failure["artifact_validation"])
    artifact = validate_github(
        failure,
        load_object(source_run_metadata),
        load_object(source_job_metadata),
        load_object(source_artifact_metadata),
    )
    recovered = build_manifest(
        evidence,
        root / contract["inputs"]["source_contract_path"],
        root,
        corrected_ingestion_recovery=True,
    )
    recovered_bytes = (json.dumps(recovered, indent=2, sort_keys=True) + "\n").encode()
    expected = contract["expected_result"]
    if (
        hashlib.sha256(recovered_bytes).hexdigest() != expected["summary_sha256"]
        or recovered.get("status") != expected["status"]
        or recovered.get("selection") != expected["selection"]
        or recovered.get("quality", {}).get("probe", {}).get("correct") != 23
        or recovered.get("quality", {}).get("probe", {}).get("failures") != 0
    ):
        raise ValueError("E20a corrected recovery result differs")
    result = {
        "schema_version": 1,
        "experiment_id": "E20a-ingestion-recovery",
        "status": "valid_cpu_node_profile_fusion_candidate_recovered_without_remeasurement",
        "contract_sha256": sha256_file(contract_path),
        "source_failure_manifest_sha256": contract["inputs"][
            "failure_manifest_sha256"
        ],
        "source_github": failure["github"],
        "source_artifact_live_metadata": {
            "id": str(artifact["id"]),
            "name": artifact["name"],
            "digest": artifact["digest"],
            "size_bytes": artifact["size_in_bytes"],
            "expires_at": artifact["expires_at"],
        },
        "source_artifact_validation": source_inventory,
        "recovery_github": {
            "run_id": recovery_run_id,
            "run_attempt": recovery_run_attempt,
            "repository_commit": recovery_head_sha,
            "artifact_name": (
                f"e20a-ingestion-recovery-{recovery_run_id}-{recovery_run_attempt}"
            ),
        },
        "recovered_summary_sha256": expected["summary_sha256"],
        "recovered_result": recovered,
        "validation": {
            "native_arm64_recovery_host_required": True,
            "all_source_artifact_files_verified": True,
            "corrected_ingester_only": True,
            "source_build_repeated": False,
            "model_download_repeated": False,
            "benchmark_or_quality_measurement_repeated": False,
            "selection_rule_or_threshold_changed": False,
            "timed_results_used_for_performance_claim": False,
            "failed_workflow_rehabilitated": False,
            "python_version": contract["execution"]["python_version"],
        },
        "decision": {
            "selected_family": recovered["selection"]["selected_family"],
            "focused_fusion_feasibility_successor_allowed": True,
            "automatic_source_optimization_allowed": False,
            "separate_source_contract_required": True,
            "separate_end_to_end_service_gate_required": True,
            "failed_workflow_remains_invalid": True,
        },
        "claim_boundary": contract["claim_boundary"],
    }
    return result, recovered_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--source-run-metadata", type=Path, required=True)
    parser.add_argument("--source-job-metadata", type=Path, required=True)
    parser.add_argument("--source-artifact-metadata", type=Path, required=True)
    parser.add_argument("--recovery-run-id", required=True)
    parser.add_argument("--recovery-run-attempt", type=int, required=True)
    parser.add_argument("--recovery-head-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result, recovered_bytes = recover(
        evidence=args.evidence_dir,
        contract_path=args.contract,
        root=args.root,
        source_run_metadata=args.source_run_metadata,
        source_job_metadata=args.source_job_metadata,
        source_artifact_metadata=args.source_artifact_metadata,
        recovery_run_id=args.recovery_run_id,
        recovery_run_attempt=args.recovery_run_attempt,
        recovery_head_sha=args.recovery_head_sha,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "recovered-summary.json").write_bytes(recovered_bytes)
    (args.output_dir / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
