#!/usr/bin/env python3
"""Validate native E5c selected-model prompt-cache evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, summarize
    from experiments.e5b_ingest import (
        ARTIFACT_INPUTS,
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_cell,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, summarize
    from e5b_ingest import (
        ARTIFACT_INPUTS,
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_cell,
    )


def evaluate_hypothesis(
    performance: dict[str, Any], acceptance: dict[str, Any]
) -> dict[str, Any]:
    baseline = performance["no_cache"]
    candidate = performance["prompt_cache"]
    throughput_ratio = (
        candidate["requests_per_second"]["median"]
        / baseline["requests_per_second"]["median"]
    )
    encode_ratio = (
        baseline["repetition_encode_median_ms"]["median"]
        / candidate["repetition_encode_median_ms"]["median"]
    )
    throughput_passed = (
        throughput_ratio >= acceptance["minimum_throughput_improvement_ratio"]
    )
    encode_passed = (
        encode_ratio >= acceptance["minimum_prompt_encode_improvement_ratio"]
    )
    latency_passed = (
        candidate["http_ms"]["median"]
        <= acceptance["maximum_candidate_median_http_latency_ms"]
        and candidate["http_ms"]["p95"]
        <= acceptance["maximum_candidate_p95_http_latency_ms"]
    )
    return {
        "passed": throughput_passed and encode_passed and latency_passed,
        "throughput_improvement_passed": throughput_passed,
        "prompt_encode_improvement_passed": encode_passed,
        "latency_ceilings_passed": latency_passed,
        "throughput_improvement_ratio": throughput_ratio,
        "prompt_encode_improvement_ratio": encode_ratio,
    }


def build_manifest(
    evidence_dir: Path,
    contract_path: Path,
    manifest_path: Path,
    policy_path: Path,
    models_path: Path,
    runtime_contract_path: Path,
    tasks_path: Path,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E5c":
        raise ValueError("unsupported E5c contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E5c contract")

    source_paths = {
        "manifest": manifest_path,
        "policy": policy_path,
        "models": models_path,
        "runtime_contract": runtime_contract_path,
        "tasks": tasks_path,
    }
    for name, path in source_paths.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if sha256_file(path) != expected:
            raise ValueError(f"source {name} hash differs from the contract")
        if sha256_file(evidence_dir / ARTIFACT_INPUTS[name]) != expected:
            raise ValueError(f"artifact {name} hash differs from the contract")

    runtime_proof = (evidence_dir / "runtime-proof.stderr.log").read_text(
        encoding="utf-8", errors="replace"
    )
    required_patterns = contract["selected"]["required_runtime_buffer_patterns"]
    for pattern in required_patterns:
        if pattern not in runtime_proof:
            raise ValueError(f"unmeasured runtime proof lacks buffer: {pattern}")

    selected_manifest = load_object(manifest_path)
    tasks = load_tasks(load_object(tasks_path))
    candidate = contract["selected"]["candidate"]
    references = reference_predictions(selected_manifest, candidate)
    if set(references) != {task["id"] for task in tasks}:
        raise ValueError("selected predictions and task IDs differ")
    correct = sum(references[task["id"]] == task["answer"] for task in tasks)
    if (
        correct != contract["selected"]["reference_correct"]
        or len(tasks) != contract["selected"]["reference_total"]
    ):
        raise ValueError("contract selected quality differs from retained evidence")

    configurations = contract["execution"]["configurations"]
    order = contract["execution"]["order"]
    expected_pairs = {
        (name, repetition)
        for name in configurations
        for repetition in range(
            1, contract["execution"]["repetitions_per_configuration"] + 1
        )
    }
    observed_pairs = {
        (item.get("configuration"), item.get("repetition")) for item in order
    }
    if len(order) != len(expected_pairs) or observed_pairs != expected_pairs:
        raise ValueError("execution order does not cover each frozen cell once")

    cells = []
    cell_paths: dict[tuple[str, int], Path] = {}
    for index, item in enumerate(order, 1):
        configuration = item["configuration"]
        repetition = item["repetition"]
        cell_dir = evidence_dir / "cells" / f"{index:02d}-{configuration}-r{repetition}"
        cell_paths[(configuration, repetition)] = cell_dir
        cells.append(
            validate_cell(
                cell_dir,
                configuration=configuration,
                repetition=repetition,
                config=configurations[configuration],
                contract=contract,
                tasks=tasks,
                references=references,
            )
        )

    performance: dict[str, Any] = {}
    for name, configuration in configurations.items():
        config_cells = [cell for cell in cells if cell["configuration"] == name]
        raw_cases = [
            case
            for cell in config_cells
            for case in load_object(
                cell_paths[(name, cell["repetition"])] / "probe.json"
            )["cases"]
        ]
        performance[name] = {
            "server_parallel_slots": configuration["server_parallel_slots"],
            "client_concurrency": configuration["client_concurrency"],
            "prompt_cache": configuration["prompt_cache"],
            "repetitions": config_cells,
            "requests_per_second": summarize(
                [cell["probe"]["requests_per_second"] for cell in config_cells]
            ),
            "repetition_encode_median_ms": summarize(
                [cell["probe"]["encode_ms"]["median"] for cell in config_cells]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in raw_cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in raw_cases]),
            "cached_tokens": summarize(
                [float(case["cached_tokens"]) for case in raw_cases]
            ),
            "evaluated_prompt_tokens": summarize(
                [float(case["evaluated_prompt_tokens"]) for case in raw_cases]
            ),
            "ready_ms": summarize([cell["ready_ms"] for cell in config_cells]),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in config_cells]
            ),
        }

    acceptance = contract["acceptance"]
    hypothesis = evaluate_hypothesis(performance, acceptance)
    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E5c":
        raise ValueError("provenance does not identify E5c")
    run_id = str(provenance["github_run_id"])
    artifact_name = (
        f"{contract['artifact_name_prefix']}-{run_id}-"
        f"{provenance['github_run_attempt']}"
    )
    return {
        "schema_version": 1,
        "experiment_id": "E5c",
        "status": (
            "valid_selected_inference_prompt_cache"
            if hypothesis["passed"]
            else "valid_selected_inference_no_prompt_cache_win"
        ),
        "scope": contract["scope"],
        "source": {
            "artifact_name": artifact_name,
            "github_run_url": (
                f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}"
            ),
            "artifact_retention_days": 90,
        },
        "contract": contract,
        "provenance": provenance,
        "platform": {
            **parse_lscpu((evidence_dir / "lscpu.txt").read_text(encoding="utf-8")),
            "uname": (evidence_dir / "uname.txt").read_text(encoding="utf-8").strip(),
            "python": (evidence_dir / "python-version.txt")
            .read_text(encoding="utf-8")
            .strip(),
        },
        "selection": {
            "candidate": candidate,
            "correct": correct,
            "total": len(tasks),
            "accuracy": correct / len(tasks),
            "model_sha256": contract["selected"]["model_sha256"],
            "model_size_bytes": contract["selected"]["model_size_bytes"],
        },
        "validation": {
            "all_input_hashes_match": True,
            "launch_recomputed_selected_plan": True,
            "exact_model_and_runtime_verified": True,
            "all_responses_match_selected_e3f_predictions": True,
            "selected_quality_reproduced_in_every_cell": True,
            "zero_request_failures": True,
            "fresh_server_per_cell": True,
            "runtime_buffer_proof_observed": True,
            "cache_mode_bound_in_recipe_and_request": True,
            "cached_prefix_observed_in_every_candidate_request": True,
            "no_cached_tokens_observed_in_baseline": True,
            "throughput_improvement_passed": hypothesis[
                "throughput_improvement_passed"
            ],
            "prompt_encode_improvement_passed": hypothesis[
                "prompt_encode_improvement_passed"
            ],
            "latency_ceilings_passed": hypothesis["latency_ceilings_passed"],
            "readiness_ceiling_passed": True,
            "rss_ceiling_passed": True,
            "prompt_cache_optimization_claim_allowed": hypothesis["passed"],
        },
        "performance": performance,
        "runtime_buffer_patterns_observed": required_patterns,
        "hypothesis": hypothesis,
        "throughput_improvement_ratio": hypothesis["throughput_improvement_ratio"],
        "prompt_encode_improvement_ratio": hypothesis[
            "prompt_encode_improvement_ratio"
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--runtime-contract", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    manifest = build_manifest(
        arguments.evidence_dir,
        arguments.contract,
        arguments.manifest,
        arguments.policy,
        arguments.models,
        arguments.runtime_contract,
        arguments.tasks,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
