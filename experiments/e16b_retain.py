#!/usr/bin/env python3
"""Retain an independently reproduced E16b loader result."""

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
    "build/runtime-files/bin/libggml-base.so.0": "build/runtime-files/bin/libggml-base.so.0.18.0",
    "build/runtime-files/bin/libggml-cpu.so.0": "build/runtime-files/bin/libggml-cpu.so.0.18.0",
    "build/runtime-files/bin/libggml.so.0": "build/runtime-files/bin/libggml.so.0.18.0",
    "build/runtime-files/bin/libllama-common.so.0": "build/runtime-files/bin/libllama-common.so.0.0.10216",
    "build/runtime-files/bin/libllama.so.0": "build/runtime-files/bin/libllama.so.0.0.10216",
    "build/runtime-files/bin/libmtmd.so.0": "build/runtime-files/bin/libmtmd.so.0.0.10216",
}


def validate_inventory(evidence: Path, run_id: str, run_attempt: int) -> dict[str, Any]:
    inventory_path = evidence / "file-inventory-sha256.txt"
    marker = f"/results/raw/e16b-{run_id}-{run_attempt}/"
    entries: dict[str, str] = {}
    for line in inventory_path.read_text(encoding="utf-8").splitlines():
        digest, absolute = line.split("  ", 1)
        if len(digest) != 64 or marker not in absolute:
            raise ValueError("E16b artifact inventory line is invalid")
        relative = absolute.split(marker, 1)[1]
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative in entries:
            raise ValueError("E16b artifact inventory path is unsafe or duplicate")
        local = evidence / path
        if not local.is_file() or sha256_file(local) != digest:
            raise ValueError(f"E16b artifact inventory differs for {relative}")
        entries[relative] = digest
    actual = {
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file()
        and path.name not in {"file-inventory-sha256.txt", "summary-local.json"}
    }
    unlisted = actual - set(entries)
    expected_unlisted = {"disk-after.txt"}
    materialized_aliases = set(RUNTIME_ALIASES) & unlisted
    if materialized_aliases:
        if materialized_aliases != set(RUNTIME_ALIASES) or any(
            sha256_file(evidence / alias) != sha256_file(evidence / target)
            for alias, target in RUNTIME_ALIASES.items()
        ):
            raise ValueError("E16b materialized runtime alias differs")
        expected_unlisted.update(RUNTIME_ALIASES)
    if set(entries) - actual or unlisted != expected_unlisted:
        raise ValueError("E16b artifact inventory file set differs")
    generated = [
        path.relative_to(evidence).as_posix()
        for path in evidence.rglob("*")
        if path.is_file()
        and (path.suffix == ".gguf" or path.name == "pareto64-e16b-sidecar.bin")
    ]
    if generated:
        raise ValueError("E16b artifact retained a generated model or sidecar")
    return {
        "file_count": len(entries),
        "inventory_sha256": sha256_file(inventory_path),
        "files_outside_runner_regular_file_inventory": {
            relative: sha256_file(evidence / relative) for relative in sorted(unlisted)
        },
        "generated_sidecar_or_model_retained": False,
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
    gates = summary.get("gates", {})
    failed = sorted(name for name, passed in gates.items() if not passed)
    promoted = summary.get("promoted") is True
    expected_status = (
        "valid_sidecar_loader_promoted"
        if promoted
        else "valid_sidecar_loader_no_promotion"
    )
    expected_selection = "sidecar_loader" if promoted else "normal_repack"
    cells = summary.get("cells", [])
    if (
        summary != independent
        or summary.get("status") != expected_status
        or summary.get("contract_sha256") != sha256_file(contract_path)
        or failed != summary.get("failed_gates")
        or promoted != all(gates.values())
        or len(cells) != 8
        or any(
            cell.get("probe", {}).get("correct") != 23
            or cell.get("probe", {}).get("failures") != 0
            or cell.get("probe", {}).get("reference_prediction_mismatches") != 0
            or cell.get("mechanism_valid") is not True
            for cell in cells
        )
        or summary.get("decision", {}).get("selected_configuration")
        != expected_selection
        or summary.get("decision", {}).get("cold_storage_claim_permitted") is not False
        or summary.get("decision", {}).get("multi_process_sharing_claim_permitted")
        is not False
        or summary.get("sidecar_cleanup", {}).get("sidecar_cleanup_complete")
        is not True
        or provenance.get("github_run_id") != run_id
        or provenance.get("github_run_attempt") != run_attempt
        or provenance.get("experiment_id") != "E16b"
        or not all(value.isdigit() for value in (run_id, job_id, artifact_id))
        or artifact_size_bytes <= 0
        or not artifact_digest.startswith("sha256:")
        or len(artifact_digest.removeprefix("sha256:")) != 64
    ):
        raise ValueError("E16b retained result or provenance differs")
    return {
        **summary,
        "decision": {
            **summary["decision"],
            "loader_promoted": promoted,
            "failed_gates": failed,
            "admitted_boundary": (
                "Exact identity-bound single-process Neoverse N2 loader only; "
                "same-job readiness is not a cold-storage claim and sharing, "
                "portability, energy, and amortized construction remain unmeasured."
                if promoted
                else "Normal runtime repacking remains selected; no loader result "
                "is promoted and no frozen gate is changed after observation."
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
        "artifact_validation": {
            "workflow_summary_sha256": sha256_file(summary_path),
            "independent_summary_sha256": sha256_file(independent_summary_path),
            "independent_summary_byte_identical": True,
            "inventory": validate_inventory(evidence, run_id, run_attempt),
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
