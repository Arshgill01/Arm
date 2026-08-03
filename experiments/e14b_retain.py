#!/usr/bin/env python3
"""Retain independently reproduced E14b selective-repack negative result."""

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


def validate_inventory(evidence: Path) -> dict[str, Any]:
    inventory_path = evidence / "file-inventory-sha256.txt"
    entries: dict[str, str] = {}
    for line in inventory_path.read_text(encoding="utf-8").splitlines():
        digest, absolute = line.split("  ", 1)
        marker = "/results/raw/e14b-"
        if len(digest) != 64 or marker not in absolute:
            raise ValueError("E14b artifact inventory line is invalid")
        suffix = absolute.split(marker, 1)[1]
        if "/" not in suffix:
            raise ValueError("E14b artifact inventory path is invalid")
        relative = suffix.split("/", 1)[1]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in entries:
            raise ValueError("E14b artifact inventory path is unsafe or duplicate")
        local = evidence / path
        if not local.is_file() or sha256_file(local) != digest:
            raise ValueError(f"E14b artifact inventory differs for {relative}")
        entries[relative] = digest
    actual = {
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file()
        and path.name not in {"file-inventory-sha256.txt", "summary-local.json"}
    }
    alias_targets = {
        "build/runtime-files/bin/libggml-base.so.0": "build/runtime-files/bin/libggml-base.so.0.18.0",
        "build/runtime-files/bin/libggml-cpu.so.0": "build/runtime-files/bin/libggml-cpu.so.0.18.0",
        "build/runtime-files/bin/libggml.so.0": "build/runtime-files/bin/libggml.so.0.18.0",
        "build/runtime-files/bin/libllama-common.so.0": "build/runtime-files/bin/libllama-common.so.0.0.10216",
        "build/runtime-files/bin/libllama.so.0": "build/runtime-files/bin/libllama.so.0.0.10216",
        "build/runtime-files/bin/libmtmd.so.0": "build/runtime-files/bin/libmtmd.so.0.0.10216",
    }
    expected_unlisted: set[str] = set()
    if (evidence / "build/runtime-files/bin").is_dir():
        expected_unlisted = {"disk-after.txt"}
        present_aliases = {
            alias for alias in alias_targets if (evidence / alias).is_file()
        }
        if present_aliases:
            if present_aliases != set(alias_targets) or any(
                sha256_file(evidence / alias) != sha256_file(evidence / target)
                for alias, target in alias_targets.items()
            ):
                raise ValueError(
                    "E14b materialized runtime alias differs from its target"
                )
            expected_unlisted.update(alias_targets)
    unlisted = actual - set(entries)
    if set(entries) - actual or unlisted != expected_unlisted:
        raise ValueError("E14b artifact inventory file set differs")
    return {
        "file_count": len(entries),
        "inventory_sha256": sha256_file(inventory_path),
        "files_outside_runner_regular_file_inventory": {
            relative: sha256_file(evidence / relative) for relative in sorted(unlisted)
        },
        "all_retained_file_hashes_verified": True,
    }


def build_manifest(
    *,
    evidence: Path,
    contract_path: Path,
    independent_summary_path: Path,
    run_id: str,
    run_attempt: int,
    job_id: str,
    artifact_name: str,
    artifact_id: str,
    artifact_size_bytes: int,
    artifact_digest: str,
) -> dict[str, Any]:
    summary_path = evidence / "summary.json"
    summary = load_object(summary_path)
    independent = load_object(independent_summary_path)
    provenance = load_object(evidence / "provenance.json")
    failed_gates = sorted(
        name for name, passed in summary.get("gates", {}).items() if not passed
    )
    candidate_gates = summary.get("candidate_gates", {})
    performance = summary.get("performance", {})
    if (
        summary != independent
        or summary.get("status") != "valid_no_selective_repack_promotion"
        or summary.get("promoted") is not False
        or summary.get("contract_sha256") != sha256_file(contract_path)
        or failed_gates != ["selective_target"]
        or summary.get("selection", {}).get("selected_configuration") != "full_repack"
        or summary.get("selection", {}).get("non_dominated_configurations")
        != ["attention_down_raw", "attention_raw", "full_repack", "no_repack"]
        or any(value.get("eligible") is not False for value in candidate_gates.values())
        or any(
            value.get("quality", {}).get("exact_selected_predictions") is not True
            for value in performance.values()
        )
        or provenance.get("github_run_id") != run_id
        or provenance.get("github_run_attempt") != run_attempt
        or not all(value.isdigit() for value in (run_id, job_id, artifact_id))
        or artifact_size_bytes <= 0
        or not artifact_digest.startswith("sha256:")
        or len(artifact_digest.removeprefix("sha256:")) != 64
    ):
        raise ValueError("E14b retained summary or negative-result boundary differs")
    return {
        **summary,
        "decision": {
            "selective_tier_promoted": False,
            "selected_configuration": "full_repack",
            "failed_gates": failed_gates,
            "candidate_blockers": {
                name: sorted(
                    gate for gate, passed in value["gates"].items() if not passed
                )
                for name, value in candidate_gates.items()
            },
            "all_points_quality_exact_and_non_dominated": True,
            "exact_boundary": (
                "Neither predeclared selective point jointly clears the frozen "
                "throughput, extra-RSS saving, and p95 requirements. Full repack "
                "remains selected; the default-off experimental hook is not promoted."
            ),
            "post_result_gate_change_permitted": False,
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
        "artifact_validation": {
            "workflow_summary_sha256": sha256_file(summary_path),
            "independent_summary_sha256": sha256_file(independent_summary_path),
            "independent_summary_byte_identical": True,
            "inventory": validate_inventory(evidence),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--independent-summary", type=Path, required=True)
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
        independent_summary_path=args.independent_summary,
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
