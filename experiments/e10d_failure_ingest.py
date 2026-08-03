#!/usr/bin/env python3
"""Retain and validate an E10d missing-probability cell failure."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e10d_ingest import (
        cell_summary,
        validate_choice,
        validate_inputs,
        validate_preflight,
        validate_prepared,
        validate_recipe,
        validate_source_and_build,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e10d_ingest import (
        cell_summary,
        validate_choice,
        validate_inputs,
        validate_preflight,
        validate_prepared,
        validate_recipe,
        validate_source_and_build,
    )


MISSING_PROBABILITY_ERROR = (
    "ValueError: completion response lacks one probability entry"
)


def raw_inventory(raw_dir: Path) -> dict[str, Any]:
    files = sorted(raw_dir.glob("*.json.gz"))
    if not files:
        raise ValueError("failed E10d cell has no raw responses")
    inventory = hashlib.sha256()
    compressed_bytes = 0
    uncompressed_bytes = 0
    for path in files:
        compressed = path.read_bytes()
        raw = gzip.decompress(compressed)
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"raw response is not an object: {path.name}")
        digest = hashlib.sha256(compressed).hexdigest()
        inventory.update(f"{digest}  {path.name}\n".encode())
        compressed_bytes += len(compressed)
        uncompressed_bytes += len(raw)
    return {
        "file_count": len(files),
        "compressed_bytes": compressed_bytes,
        "uncompressed_bytes": uncompressed_bytes,
        "inventory_sha256": inventory.hexdigest(),
    }


def infer_failed_request(
    *,
    raw_names: set[str],
    task_name: str,
    sample: dict[str, Any],
    completed_choices: int,
    error: str,
) -> tuple[dict[str, Any], set[str]]:
    if error != MISSING_PROBABILITY_ERROR:
        raise ValueError("failed E10d error is not the retained probability gap")
    requests = sample["requests"]
    if not 0 <= completed_choices < len(requests):
        raise ValueError("failed E10d request ordinal differs")
    request = requests[completed_choices]
    choice_index = request["choice_index"]
    prefix = (
        f"{task_name}-{sample['sample_ordinal']:03d}"
        f"-c{choice_index:02d}-t"
    )
    retained = sorted(name for name in raw_names if name.startswith(prefix))
    expected = [
        f"{prefix}{index:03d}.json.gz" for index in range(len(retained))
    ]
    candidate = request["candidate_tokens"]
    if retained != expected or len(retained) >= len(candidate):
        raise ValueError("failed E10d partial response sequence differs")
    missing_index = len(retained)
    return (
        {
            "failed_choice_index": choice_index,
            "failed_token_index": missing_index,
            "failed_target_token_id": candidate[missing_index],
            "candidate_token_count": len(candidate),
            "retained_partial_token_responses": len(retained),
            "failure_response_received_but_not_retained": True,
        },
        set(retained),
    )


def validate_partial_probe(
    evidence: Path,
    probe: dict[str, Any],
    prepared: dict[str, Any],
    model: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    tasks = probe.get("tasks")
    result = probe.get("result")
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E10d"
        or probe.get("model") != model["candidate"]
        or probe.get("model_sha256") != model["sha256"]
        or probe.get("parameters") != contract["scoring"]["probe_parameters"]
        or not isinstance(tasks, list)
        or len(tasks) != len(prepared["tasks"])
        or not isinstance(result, dict)
        or result.get("samples") != 300
        or not isinstance(result.get("failures"), int)
        or result["failures"] <= 0
    ):
        raise ValueError("failed E10d probe header differs")

    errors: list[dict[str, Any]] = []
    referenced_paths: set[str] = set()
    partial_failure_paths: set[str] = set()
    raw_names = {path.name for path in (evidence / "raw").glob("*.json.gz")}
    completed_choices = 0
    completed_tokens = 0
    for measured_task, source_task in zip(tasks, prepared["tasks"], strict=True):
        samples = measured_task.get("samples")
        if (
            measured_task.get("task") != source_task["task"]
            or measured_task.get("metrics") != source_task["metrics"]
            or not isinstance(samples, list)
            or len(samples) != len(source_task["samples"])
        ):
            raise ValueError("failed E10d task identity differs")
        for measured, source in zip(samples, source_task["samples"], strict=True):
            choices = measured.get("choices")
            error = measured.get("error")
            if (
                measured.get("sample_ordinal") != source["sample_ordinal"]
                or measured.get("source_index") != source["source_index"]
                or measured.get("source_document_sha256")
                != source["source_document_sha256"]
                or measured.get("gold_index") != source["gold_index"]
                or measured.get("choice_text_lengths")
                != source["choice_text_lengths"]
                or not isinstance(choices, list)
                or len(choices) > len(source["requests"])
            ):
                raise ValueError("failed E10d sample identity differs")
            if error is None and len(choices) != len(source["requests"]):
                raise ValueError("successful E10d sample is incomplete")
            if error is not None and (
                not isinstance(error, str) or len(choices) >= len(source["requests"])
            ):
                raise ValueError("failed E10d sample error differs")
            for index, choice in enumerate(choices):
                request = source["requests"][index]
                validate_choice(choice, request, evidence / "raw")
                completed_choices += 1
                completed_tokens += len(request["candidate_tokens"])
                for record in choice["raw_responses"]:
                    path = record["path"]
                    if path in referenced_paths:
                        raise ValueError("failed E10d raw response is referenced twice")
                    referenced_paths.add(path)
            if error is not None:
                inferred, inferred_paths = infer_failed_request(
                    raw_names=raw_names,
                    task_name=source_task["task"],
                    sample=source,
                    completed_choices=len(choices),
                    error=error,
                )
                if partial_failure_paths.intersection(inferred_paths):
                    raise ValueError("failed E10d partial response is reused")
                partial_failure_paths.update(inferred_paths)
                errors.append(
                    {
                        "task": source_task["task"],
                        "sample_ordinal": source["sample_ordinal"],
                        "source_index": source["source_index"],
                        "completed_choices_before_error": len(choices),
                        "error": error,
                        **inferred,
                    }
                )
    if len(errors) != result["failures"]:
        raise ValueError("failed E10d error count differs")
    raw = raw_inventory(evidence / "raw")
    if not referenced_paths.issubset(raw_names):
        raise ValueError("failed E10d referenced raw response is missing")
    if referenced_paths.intersection(partial_failure_paths):
        raise ValueError("failed E10d raw response has two roles")
    if referenced_paths | partial_failure_paths != raw_names:
        raise ValueError("failed E10d raw response role is unexplained")
    if (
        result.get("candidate_requests") > completed_choices
        or result.get("token_score_requests") > completed_tokens
    ):
        raise ValueError("failed E10d retained totals exceed completed evidence")
    received_responses = raw["file_count"] + len(errors)
    planned_responses = contract["workload"]["expected_summary"][
        "token_score_requests"
    ]
    if received_responses > planned_responses:
        raise ValueError("failed E10d response count exceeds frozen workload")
    return {
        "errors": errors,
        "probe_result": result,
        "task_results": {
            task["task"]: task["result"] for task in tasks
        },
        "completed_choice_records": completed_choices,
        "completed_token_records": completed_tokens,
        "referenced_raw_responses": len(referenced_paths),
        "unreferenced_partial_raw_responses": raw["file_count"]
        - len(referenced_paths),
        "received_response_count_including_unretained_failures": received_responses,
        "unattempted_frozen_token_requests": planned_responses - received_responses,
        "raw_inventory": raw,
    }


def build_manifest(
    evidence: Path,
    contract_path: Path,
    root: Path,
    model_name: str,
    run_id: str,
    run_attempt: int,
    artifact_name: str,
    artifact_id: str,
) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    models = {model["candidate"]: model for model in contract["models"]}
    if model_name not in models:
        raise ValueError("failed E10d model is not frozen")
    model = models[model_name]
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("failed E10d evidence is not native Arm64")
    runtime = validate_source_and_build(evidence, contract)
    validate_recipe(load_object(evidence / "recipe.json"), contract, model)
    prepared = validate_prepared(
        load_object(evidence / "prepared.json"),
        contract,
        load_object(evidence / "sample-map.json"),
    )
    preflight = validate_preflight(evidence, contract)
    partial = validate_partial_probe(
        evidence, load_object(evidence / "probe.json"), prepared, model, contract
    )
    strict_error = None
    try:
        cell_summary(evidence, contract_path, root, model_name)
    except (KeyError, OSError, TypeError, ValueError) as error:
        strict_error = f"{type(error).__name__}: {error}"
    if strict_error is None:
        raise ValueError("E10d failure ingester was used on a valid cell")
    process = parse_time_output((evidence / "server-time.log").read_text())
    return {
        "schema_version": 1,
        "experiment_id": "E10d",
        "status": "invalid_external_holdout_cell_retained",
        "contract_sha256": sha256_file(contract_path),
        "github": {
            "run_id": run_id,
            "run_attempt": run_attempt,
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "artifact_name": artifact_name,
            "artifact_id": artifact_id,
        },
        "model": model,
        "platform": platform,
        "runtime": runtime,
        "prepared_sha256": sha256_file(evidence / "prepared.json"),
        "preflight": {
            "status": preflight["status"],
            "maximum_repeat_sum_logprob_delta": preflight[
                "maximum_repeat_sum_logprob_delta"
            ],
            "maximum_repeat_token_logprob_delta": preflight[
                "maximum_repeat_token_logprob_delta"
            ],
        },
        "server_process": process,
        "strict_ingest_error": strict_error,
        "partial_evidence": partial,
        "decision": {
            "cell_valid": False,
            "aggregate_valid": False,
            "metrics_comparable": False,
            "e11a_exact_prerequisite_satisfied": False,
            "e12b_exact_prerequisite_satisfied": False,
            "negative_result_retained": True,
        },
        "claim_boundary": "This manifest retains a failed frozen E10d cell. Partial metrics are descriptive only and cannot support a model comparison, frontier, promotion, performance, energy, or cost claim.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = build_manifest(
        args.evidence_dir,
        args.contract,
        args.root,
        args.model,
        args.run_id,
        args.run_attempt,
        args.artifact_name,
        args.artifact_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
