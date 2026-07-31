#!/usr/bin/env python3
"""Validate native E5f prompt batch and microbatch profile evidence."""

from __future__ import annotations

import argparse
import json
import math
import re
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
        validate_recipe,
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
        validate_recipe,
    )


BATCH_PATTERN = re.compile(r"llama_context:\s+n_batch\s*=\s*(\d+)")
MICRO_BATCH_PATTERN = re.compile(r"llama_context:\s+n_ubatch\s*=\s*(\d+)")
COMPUTE_BUFFER_PATTERN = re.compile(r"CPU compute buffer size\s*=\s*([0-9.]+)\s+MiB")


def unique_match(pattern: re.Pattern[str], text: str, label: str) -> str:
    matches = pattern.findall(text)
    if not matches or any(value != matches[0] for value in matches[1:]):
        raise ValueError(f"mechanism log lacks one consistent {label}")
    return matches[0]


def parse_batch_mechanism(
    text: str,
    *,
    config: dict[str, Any],
) -> dict[str, Any]:
    result = {
        "batch_size": int(unique_match(BATCH_PATTERN, text, "logical batch size")),
        "micro_batch_size": int(
            unique_match(MICRO_BATCH_PATTERN, text, "physical microbatch size")
        ),
        "compute_buffer_mib": float(
            unique_match(COMPUTE_BUFFER_PATTERN, text, "CPU compute-buffer size")
        ),
    }
    if (
        result["batch_size"] != config["batch_size"]
        or result["micro_batch_size"] != config["micro_batch_size"]
        or not math.isfinite(result["compute_buffer_mib"])
        or result["compute_buffer_mib"] <= 0
    ):
        raise ValueError("mechanism log differs from the frozen batch profile")
    return result


def validate_mechanisms(
    evidence_dir: Path,
    *,
    configurations: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    mechanism_contract = contract["mechanism"]
    observed: dict[str, dict[str, Any]] = {}
    for name, config in configurations.items():
        proof_dir = evidence_dir / "mechanisms" / name
        recipe = load_object(proof_dir / "recipe.json")
        validate_recipe(recipe, config=config, contract=contract)
        runtime = recipe["runtime"]
        argv = runtime["argv"]
        verbosity = mechanism_contract["proof_log_verbosity"]
        if (
            runtime.get("log_verbosity") != verbosity
            or argv.count("--log-verbosity") != 1
            or argv.index("--log-verbosity") == len(argv) - 1
            or argv[argv.index("--log-verbosity") + 1] != str(verbosity)
        ):
            raise ValueError(f"{name} mechanism recipe lacks frozen log verbosity")
        log = (proof_dir / "server.stderr.log").read_text(
            encoding="utf-8", errors="replace"
        )
        for pattern in mechanism_contract["required_log_patterns"]:
            if pattern not in log:
                raise ValueError(f"{name} mechanism log lacks {pattern}")
        observed[name] = parse_batch_mechanism(log, config=config)

    return observed


def compute_buffers_microbatch_monotonic(
    observed: dict[str, dict[str, Any]],
    configurations: dict[str, dict[str, Any]],
) -> bool:
    ordered = sorted(
        observed,
        key=lambda name: configurations[name]["micro_batch_size"],
        reverse=True,
    )
    return len(ordered) == 3 and all(
        observed[left]["compute_buffer_mib"] > observed[right]["compute_buffer_mib"]
        for left, right in zip(ordered, ordered[1:])
    )


def evaluate_profiles(
    performance: dict[str, Any],
    *,
    acceptance: dict[str, Any],
    baseline_configuration: str,
) -> dict[str, Any]:
    baseline = performance[baseline_configuration]
    baseline_throughput = baseline["requests_per_second"]["median"]
    baseline_median_latency = baseline["http_ms"]["median"]
    baseline_p95_latency = baseline["http_ms"]["p95"]
    baseline_rss = baseline["maximum_rss_kib"]["max"]
    baseline_buffer = baseline["mechanism"]["compute_buffer_mib"]
    if (
        min(
            baseline_throughput,
            baseline_median_latency,
            baseline_p95_latency,
            baseline_rss,
            baseline_buffer,
        )
        <= 0
    ):
        raise ValueError("baseline batch profile contains a non-positive value")

    gates: dict[str, dict[str, Any]] = {}
    eligible: list[str] = []
    for name, profile in performance.items():
        throughput_ratio = (
            profile["requests_per_second"]["median"] / baseline_throughput
        )
        median_latency_ratio = profile["http_ms"]["median"] / baseline_median_latency
        p95_latency_ratio = profile["http_ms"]["p95"] / baseline_p95_latency
        buffer_reduction = baseline_buffer - profile["mechanism"]["compute_buffer_mib"]
        rss_reduction = baseline_rss - profile["maximum_rss_kib"]["max"]
        quality_passed = profile["quality"]["exact_selected_predictions"]
        throughput_passed = (
            throughput_ratio >= acceptance["minimum_throughput_retention_ratio"]
        )
        latency_passed = (
            median_latency_ratio <= acceptance["maximum_median_http_latency_ratio"]
            and p95_latency_ratio <= acceptance["maximum_p95_http_latency_ratio"]
        )
        buffer_passed = (
            buffer_reduction >= acceptance["minimum_compute_buffer_reduction_mib"]
        )
        memory_passed = rss_reduction >= acceptance["minimum_process_rss_reduction_kib"]
        profile_eligible = (
            name != baseline_configuration
            and quality_passed
            and throughput_passed
            and latency_passed
            and buffer_passed
            and memory_passed
        )
        gates[name] = {
            "eligible": profile_eligible,
            "quality_passed": quality_passed,
            "throughput_retention_passed": throughput_passed,
            "latency_retention_passed": latency_passed,
            "compute_buffer_reduction_passed": buffer_passed,
            "process_rss_reduction_passed": memory_passed,
            "throughput_retention_ratio": throughput_ratio,
            "median_http_latency_ratio": median_latency_ratio,
            "p95_http_latency_ratio": p95_latency_ratio,
            "compute_buffer_reduction_mib": buffer_reduction,
            "process_rss_reduction_kib": rss_reduction,
        }
        if profile_eligible:
            eligible.append(name)

    selected = (
        min(
            eligible,
            key=lambda name: (
                performance[name]["maximum_rss_kib"]["max"],
                performance[name]["micro_batch_size"],
                performance[name]["batch_size"],
                name,
            ),
        )
        if eligible
        else None
    )
    return {
        "passed": selected is not None,
        "baseline_configuration": baseline_configuration,
        "selected_configuration": selected,
        "eligible_configurations": sorted(eligible),
        "profile_gates": gates,
        "weighted_score_used": False,
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
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E5f":
        raise ValueError("unsupported E5f contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E5f contract")

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

    execution = contract["execution"]
    configurations = execution["configurations"]
    baseline_configuration = execution["baseline_configuration"]
    if baseline_configuration not in configurations:
        raise ValueError("baseline configuration is absent")
    order = execution["order"]
    expected_pairs = {
        (name, repetition)
        for name in configurations
        for repetition in range(1, execution["repetitions_per_configuration"] + 1)
    }
    observed_pairs = {
        (item.get("configuration"), item.get("repetition")) for item in order
    }
    if len(order) != len(expected_pairs) or observed_pairs != expected_pairs:
        raise ValueError("execution order does not cover every frozen cell once")

    mechanisms = validate_mechanisms(
        evidence_dir,
        configurations=configurations,
        contract=contract,
    )
    mechanism_monotonic = compute_buffers_microbatch_monotonic(
        mechanisms,
        configurations,
    )
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
                require_selected_quality=False,
            )
        )

    performance: dict[str, Any] = {}
    maximum_prompt_tokens = 0
    for name, configuration in configurations.items():
        config_cells = [cell for cell in cells if cell["configuration"] == name]
        probes = [
            load_object(cell_paths[(name, cell["repetition"])] / "probe.json")
            for cell in config_cells
        ]
        raw_cases = [case for probe in probes for case in probe["cases"]]
        prompt_tokens = [
            int(case["cached_tokens"]) + int(case["evaluated_prompt_tokens"])
            for case in raw_cases
        ]
        maximum_prompt_tokens = max(maximum_prompt_tokens, max(prompt_tokens))
        prediction_maps = [
            {case["id"]: case["predicted"] for case in probe["cases"]}
            for probe in probes
        ]
        exact_selected_predictions = all(
            cell["probe"]["correct"] == contract["selected"]["reference_correct"]
            and cell["probe"]["reference_prediction_mismatches"]
            == contract["acceptance"]["reference_prediction_mismatches"]
            for cell in config_cells
        )
        performance[name] = {
            "server_parallel_slots": configuration["server_parallel_slots"],
            "client_concurrency": configuration["client_concurrency"],
            "prompt_cache": configuration["prompt_cache"],
            "context_per_slot": configuration["context_per_slot"],
            "kv_cache_type_k": configuration["kv_cache_type_k"],
            "kv_cache_type_v": configuration["kv_cache_type_v"],
            "flash_attention": configuration["flash_attention"],
            "batch_size": configuration["batch_size"],
            "micro_batch_size": configuration["micro_batch_size"],
            "explicit_batch_arguments": configuration["explicit_batch_arguments"],
            "mechanism": mechanisms[name],
            "quality": {
                "correct_per_repetition": [
                    cell["probe"]["correct"] for cell in config_cells
                ],
                "reference_prediction_mismatches_per_repetition": [
                    cell["probe"]["reference_prediction_mismatches"]
                    for cell in config_cells
                ],
                "predictions_stable_between_repetitions": all(
                    item == prediction_maps[0] for item in prediction_maps[1:]
                ),
                "exact_selected_predictions": exact_selected_predictions,
            },
            "repetitions": config_cells,
            "requests_per_second": summarize(
                [cell["probe"]["requests_per_second"] for cell in config_cells]
            ),
            "repetition_encode_median_ms": summarize(
                [cell["probe"]["encode_ms"]["median"] for cell in config_cells]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in raw_cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in raw_cases]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in raw_cases]),
            "cached_tokens": summarize(
                [float(case["cached_tokens"]) for case in raw_cases]
            ),
            "evaluated_prompt_tokens": summarize(
                [float(case["evaluated_prompt_tokens"]) for case in raw_cases]
            ),
            "prompt_tokens": summarize([float(value) for value in prompt_tokens]),
            "ready_ms": summarize([cell["ready_ms"] for cell in config_cells]),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in config_cells]
            ),
        }

    if (
        maximum_prompt_tokens
        != contract["prior_evidence"]["maximum_observed_prompt_tokens"]
    ):
        raise ValueError("observed prompt bound differs from the retained E5e evidence")
    baseline_buffer = mechanisms[baseline_configuration]["compute_buffer_mib"]
    if not math.isclose(
        baseline_buffer,
        contract["prior_evidence"]["baseline_compute_buffer_mib"],
        abs_tol=0.01,
    ):
        raise ValueError("baseline compute buffer differs from retained E5e evidence")

    hypothesis = evaluate_profiles(
        performance,
        acceptance=contract["acceptance"],
        baseline_configuration=baseline_configuration,
    )
    for name, profile in performance.items():
        profile["gates"] = hypothesis["profile_gates"][name]

    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E5f":
        raise ValueError("provenance does not identify E5f")
    if provenance.get("promoted_default_configuration") != baseline_configuration:
        raise ValueError("provenance does not bind the promoted batch default")
    run_id = str(provenance["github_run_id"])
    artifact_name = (
        f"{contract['artifact_name_prefix']}-{run_id}-"
        f"{provenance['github_run_attempt']}"
    )
    return {
        "schema_version": 1,
        "experiment_id": "E5f",
        "status": (
            "valid_selected_inference_batch_profile"
            if hypothesis["passed"]
            else "valid_selected_inference_no_batch_profile_win"
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
            "configuration": hypothesis["selected_configuration"],
        },
        "validation": {
            "all_input_hashes_match": True,
            "launch_recomputed_selected_plan": True,
            "exact_model_and_runtime_verified": True,
            "zero_request_failures": True,
            "fresh_server_per_cell": True,
            "runtime_buffer_proof_observed": True,
            "batch_arguments_and_effective_values_bound_in_every_recipe": True,
            "batch_and_compute_buffer_mechanism_observed_for_every_profile": True,
            "compute_buffer_sizes_microbatch_monotonic": mechanism_monotonic,
            "cached_prefix_observed_in_every_measured_request": True,
            "quality_drift_treated_as_profile_ineligibility": True,
            "readiness_ceiling_passed": True,
            "rss_ceiling_passed": True,
            "batch_profile_claim_allowed": hypothesis["passed"],
        },
        "maximum_observed_prompt_tokens": maximum_prompt_tokens,
        "performance": performance,
        "runtime_buffer_patterns_observed": required_patterns,
        "hypothesis": hypothesis,
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
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
