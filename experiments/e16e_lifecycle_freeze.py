#!/usr/bin/env python3
"""Freeze the E16e byte-safe retention repair for the failed E16d workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import sha256_file
    from experiments.e16e_lifecycle_retain import (
        SOURCE_ARTIFACT_DIGEST,
        SOURCE_ARTIFACT_EXPIRES_AT,
        SOURCE_ARTIFACT_ID,
        SOURCE_ARTIFACT_NAME,
        SOURCE_ARTIFACT_SIZE_BYTES,
        SOURCE_EXTRACTED_BYTES,
        SOURCE_EXTRACTED_FILES,
        SOURCE_HEAD_SHA,
        SOURCE_JOB_ID,
        SOURCE_RUN_ID,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import sha256_file
    from e16e_lifecycle_retain import (
        SOURCE_ARTIFACT_DIGEST,
        SOURCE_ARTIFACT_EXPIRES_AT,
        SOURCE_ARTIFACT_ID,
        SOURCE_ARTIFACT_NAME,
        SOURCE_ARTIFACT_SIZE_BYTES,
        SOURCE_EXTRACTED_BYTES,
        SOURCE_EXTRACTED_FILES,
        SOURCE_HEAD_SHA,
        SOURCE_JOB_ID,
        SOURCE_RUN_ID,
    )


INPUT_PATHS = {
    "e16d_contract": "experiments/e16d_lifecycle_contract.json",
    "e16d_ingest": "experiments/e16d_lifecycle_ingest.py",
    "e16d_synthetic": "results/manifests/e16d-lifecycle-synthetic-replay.json",
    "e16c_contract": "experiments/e16c_contract.json",
    "e16c_manifest": "results/manifests/e16c-30851609576.json",
    "retain": "experiments/e16e_lifecycle_retain.py",
    "freeze": "experiments/e16e_lifecycle_freeze.py",
    "tests": "tests/test_e16e_lifecycle.py",
}


def build_contract(root: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "experiment_id": "E16e",
        "title": "Byte-safe retention repair for the completed E16d lifecycle",
        "state": "frozen_after_e16d_reader_failure_before_repaired_retention",
        "inputs": {
            name: {"path": path, "sha256": sha256_file(root / path)}
            for name, path in sorted(INPUT_PATHS.items())
        },
        "predecessor": {
            "experiment_id": "E16d",
            "contract_path": INPUT_PATHS["e16d_contract"],
            "contract_sha256": sha256_file(root / INPUT_PATHS["e16d_contract"]),
            "run_id": SOURCE_RUN_ID,
            "job_id": SOURCE_JOB_ID,
            "head_sha": SOURCE_HEAD_SHA,
            "workflow_conclusion": "failure",
            "artifact_id": SOURCE_ARTIFACT_ID,
            "artifact_name": SOURCE_ARTIFACT_NAME,
            "artifact_size_bytes": SOURCE_ARTIFACT_SIZE_BYTES,
            "artifact_digest": SOURCE_ARTIFACT_DIGEST,
            "artifact_expires_at": SOURCE_ARTIFACT_EXPIRES_AT,
            "extracted_files": SOURCE_EXTRACTED_FILES,
            "extracted_bytes": SOURCE_EXTRACTED_BYTES,
            "failure_class": "non_utf8_diagnostic_reader_failure",
            "failure_location": "e16d_lifecycle_ingest.py:mechanism_log",
        },
        "repair": {
            "permitted_change": (
                "Search the two frozen ASCII mechanism markers in raw retained "
                "bytes rather than decoding unrelated llama.cpp diagnostics."
            ),
            "artifact_mutation_permitted": False,
            "acceptance_gate_changes_permitted": False,
            "product_rerun_required": False,
            "native_measurements_added": 0,
            "repaired_replay_count": 2,
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "download_exact_failed_artifact": True,
            "model_download": False,
            "sidecar_construction": False,
            "performance_matrix": False,
            "full_source_file_inventory_required": True,
        },
        "acceptance": {
            "unchanged_e16d_gates": 14,
            "all_gates_required": True,
            "strict_utf8_decode_failures": 2,
            "source_extracted_files": SOURCE_EXTRACTED_FILES,
            "source_extracted_bytes": SOURCE_EXTRACTED_BYTES,
            "exact_worker_quality": "23/30 each",
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "worker_answer_mismatches": 0,
        },
        "negative_result_rule": (
            "E16d remains a failed workflow. E16e may promote the product lifecycle "
            "only if the exact failed artifact passes every unchanged E16d gate under "
            "the single byte-safe reader repair."
        ),
        "claim_boundary": (
            "A valid E16e result establishes that the exact native E16d artifact "
            "completed the clean-checkout prepack, full verification, corruption "
            "rejection, two-worker read-only shared launch, exact 23/30 quality on "
            "both workers, controlled stop, and receipt-bound cleanup. E16d's failed "
            "workflow conclusion remains retained. E16e changes no lifecycle gate, "
            "adds no native measurement, and makes no new throughput, cold-start, "
            "per-process RSS, energy, PMU, Mac, fleet, or cost claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"experiment_id": "E16e"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
