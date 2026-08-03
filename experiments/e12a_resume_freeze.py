#!/usr/bin/env python3
"""Freeze an exact continuation from E12a's last complete checkpoint."""

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


INPUT_PATHS = {
    "base_plan": Path("experiments/e12a_imatrix_plan.json"),
    "failure_manifest": Path("results/manifests/e12a-30822632328.json"),
    "freeze": Path("experiments/e12a_resume_freeze.py"),
    "ingest": Path("experiments/e12a_resume_ingest.py"),
    "test": Path("tests/test_e12a_resume.py"),
}


def build_contract(root: Path) -> dict[str, Any]:
    plan = load_object(root / INPUT_PATHS["base_plan"])
    failure = load_object(root / INPUT_PATHS["failure_manifest"])
    checkpoint = failure.get("resume_checkpoint")
    if (
        plan.get("experiment_id") != "E12a"
        or failure.get("status") != "invalid_native_timeout_with_resume_checkpoint"
        or failure.get("contract_sha256") != sha256_file(root / INPUT_PATHS["base_plan"])
        or failure.get("decision", {}).get("separately_frozen_exact_checkpoint_resume_allowed") is not True
        or not isinstance(checkpoint, dict)
        or checkpoint.get("metadata", {}).get("chunk_count") != 24
        or checkpoint.get("remaining_chunks") != 8
        or checkpoint.get("metadata", {}).get("entries") != 182
    ):
        raise ValueError("E12a resume prerequisite differs")

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    return {
        "schema_version": 1,
        "experiment_id": "E12a-resume",
        "title": "Exact E12a checkpoint continuation",
        "state": (
            "frozen after retaining the native 300-minute timeout and inspecting "
            "only its periodic checkpoint identity/metadata, before observing any "
            "completed-matrix statistics or generated-quant result"
        ),
        "hypothesis": (
            "Loading the exact 24-chunk periodic GGUF checkpoint and processing the "
            "remaining eight corpus chunks in order completes the originally frozen "
            "32-chunk application-conditioned importance matrix without repeating "
            "or changing calibration work."
        ),
        "inputs": inputs,
        "prerequisite": {
            "experiment": "E12a",
            "run_id": failure["github"]["run_id"],
            "run_attempt": failure["github"]["run_attempt"],
            "job_id": failure["github"]["job_id"],
            "artifact_name": failure["github"]["artifact_name"],
            "artifact_id": failure["github"]["artifact_id"],
            "artifact_digest": failure["github"]["artifact_digest"],
            "repository_commit": failure["github"]["repository_commit"],
            "failure_manifest_sha256": sha256_file(root / INPUT_PATHS["failure_manifest"]),
            "base_contract_sha256": failure["contract_sha256"],
            "checkpoint": checkpoint,
        },
        "source": plan["source"],
        "build": plan["build"],
        "model": plan["model"],
        "tokenizer": plan["tokenizer"],
        "calibration": plan["calibration"],
        "resume": {
            "from_chunk": 24,
            "new_chunks": 8,
            "final_chunks": 32,
            "tokens_per_chunk": 512,
            "argv_after_binary": [
                "--model", "MODEL_PATH",
                "--file", "CORPUS_PATH",
                "--in-file", "CHECKPOINT_PATH",
                "--output-file", "IMATRIX_PATH",
                "--output-format", "gguf",
                "--ctx-size", "512",
                "--batch-size", "512",
                "--ubatch-size", "128",
                "--threads", "4",
                "--chunk", "24",
                "--chunks", "8",
                "--output-frequency", "8",
                "--no-ppl",
                "--parse-special",
            ],
            "dataset_metadata_policy": (
                "The final GGUF must list the prerequisite artifact corpus path "
                "followed by the current-run path to byte-identical corpus content."
            ),
            "checkpoint_entry_names_must_match_final": True,
            "job_timeout_minutes": 180,
        },
        "acceptance": {
            **plan["acceptance"],
            "required_checkpoint_chunks": 24,
            "required_new_chunks": 8,
            "required_final_chunks": 32,
            "required_imatrix_entries": 182,
            "require_checkpoint_hash_match": True,
            "require_checkpoint_load_log": True,
            "require_chunk_skip_log": True,
            "require_fresh_source_build_model": True,
        },
        "decision": {
            "resume_success_promotes_model": False,
            "resume_success_authorizes_generated_quant_successor": True,
            "original_timeout_rehabilitated": False,
            "failure_rule": (
                "Retain checkpoint download/identity failure, source/build/model/corpus "
                "drift, load failure, a chunk count other than 32, entry-name drift, "
                "invalid metadata, incomplete statistics, or tool failure without "
                "changing the checkpoint, chunk range, data, model, source, or gates."
            ),
        },
        "claim_boundary": (
            "A passing E12a resume establishes only one complete application-conditioned "
            "importance-matrix artifact assembled by exact ordered continuation on native "
            "GitHub-hosted Arm64. It is not a quantized model, quality, service, energy, "
            "PMU, local-device, fleet, cost, pruning, or other-runtime result."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
