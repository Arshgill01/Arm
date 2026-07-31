#!/usr/bin/env python3
"""Validate native E5i Arm Flash Attention ablation evidence."""

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


FLASH_MODE_PATTERN = re.compile(r"llama_context:\s+flash_attn\s*=\s*(\w+)")
COMPUTE_BUFFER_PATTERN = re.compile(
    r"CPU compute buffer size\s*=\s*([0-9.]+)\s+MiB"
)


def validate_pareto64_invocation(cell_dir: Path, config: dict[str, Any]) -> None:
    time_log = (cell_dir / "server-time.log").read_text(
        encoding="utf-8", errors="replace"
    )
    commands = [
        line for line in time_log.splitlines() if "Command being timed:" in line
    ]
    if len(commands) != 1:
        raise ValueError(f"{cell_dir.name} lacks one timed launcher command")
    explicit = config["explicit_flash_argument"]
    has_argument = " --flash-attention off" in commands[0]
    if has_argument is not explicit or " --flash-attention on" in commands[0]:
        raise ValueError(f"{cell_dir.name} Pareto64 flash invocation differs")


def parse_flash_mechanism(text: str, *, config: dict[str, Any]) -> dict[str, Any]:
    modes = FLASH_MODE_PATTERN.findall(text)
    buffers = COMPUTE_BUFFER_PATTERN.findall(text)
    if len(modes) != 1 or len(buffers) != 1:
        raise ValueError("mechanism log lacks one flash mode and compute buffer")
    expected_mode = "auto" if config["flash_attention"] == "auto" else "disabled"
    if modes[0] != expected_mode:
        raise ValueError("mechanism log flash mode differs from the contract")
    resolved_enabled = "resolve_fused_ops: Flash Attention enabled" in text
    if resolved_enabled is not (config["flash_attention"] == "auto"):
        raise ValueError("resolved Flash Attention mechanism differs from the contract")
    compute_buffer_mib = float(buffers[0])
    if not math.isfinite(compute_buffer_mib) or compute_buffer_mib <= 0:
        raise ValueError("invalid compute-buffer mechanism evidence")
    return {
        "declared_mode": config["flash_attention"],
        "logged_mode": modes[0],
        "resolved_enabled": resolved_enabled,
        "compute_buffer_mib": compute_buffer_mib,
    }


def validate_mechanisms(
    evidence_dir: Path,
    *,
    configurations: dict[str, dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    verbosity = contract["mechanism"]["proof_log_verbosity"]
    for name, config in configurations.items():
        proof_dir = evidence_dir / "mechanisms" / name
        recipe = load_object(proof_dir / "recipe.json")
        validate_recipe(recipe, config=config, contract=contract)
        validate_pareto64_invocation(proof_dir, config)
        runtime = recipe["runtime"]
        argv = runtime["argv"]
        if (
            runtime.get("log_verbosity") != verbosity
            or argv.count("--log-verbosity") != 1
            or argv.index("--log-verbosity") == len(argv) - 1
            or argv[argv.index("--log-verbosity") + 1] != str(verbosity)
        ):
            raise ValueError(f"{name} mechanism recipe lacks log verbosity")
        log = (proof_dir / "server.stderr.log").read_text(
            encoding="utf-8", errors="replace"
        )
        observed[name] = parse_flash_mechanism(log, config=config)
    return observed


def evaluate_boundary(
    performance: dict[str, Any],
    *,
    acceptance: dict[str, Any],
    baseline_configuration: str,
    candidate_configuration: str,
) -> dict[str, Any]:
    baseline = performance[baseline_configuration]
    candidate = performance[candidate_configuration]
    throughput_ratio = (
        candidate["requests_per_second"]["median"]
        / baseline["requests_per_second"]["median"]
    )
    median_ratio = candidate["http_ms"]["median"] / baseline["http_ms"]["median"]
    p95_ratio = candidate["http_ms"]["p95"] / baseline["http_ms"]["p95"]
    rss_increase = (
        candidate["maximum_rss_kib"]["max"] - baseline["maximum_rss_kib"]["max"]
    )
    quality_passed = all(
        profile["quality"]["exact_selected_predictions"]
        for profile in (baseline, candidate)
    )
    throughput_passed = (
        throughput_ratio >= acceptance["minimum_throughput_improvement_ratio"]
    )
    median_passed = median_ratio <= acceptance["maximum_median_http_ratio"]
    p95_passed = p95_ratio <= acceptance["maximum_p95_http_ratio"]
    rss_passed = (
        rss_increase <= acceptance["maximum_process_rss_increase_kib"]
    )
    eligible = (
        quality_passed
        and throughput_passed
        and median_passed
        and p95_passed
        and rss_passed
    )
    return {
        "passed": eligible,
        "baseline_configuration": baseline_configuration,
        "default_configuration": candidate_configuration,
        "validated_default_configuration": candidate_configuration if eligible else None,
        "candidate_configuration": candidate_configuration,
        "quality_passed": quality_passed,
        "throughput_improvement_passed": throughput_passed,
        "median_latency_passed": median_passed,
        "p95_latency_passed": p95_passed,
        "process_rss_overhead_passed": rss_passed,
        "throughput_improvement_ratio": throughput_ratio,
        "median_http_ratio": median_ratio,
        "p95_http_ratio": p95_ratio,
        "process_rss_increase_kib": rss_increase,
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
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E5i":
        raise ValueError("unsupported E5i contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E5i contract")

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
    candidate_configuration = execution["candidate_configuration"]
    if set(configurations) != {baseline_configuration, candidate_configuration}:
        raise ValueError("flash configurations differ from the frozen pair")
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

    provenance = load_object(evidence_dir / "provenance.json")
    if (
        provenance.get("experiment_id") != "E5i"
        or provenance.get("default_configuration") != candidate_configuration
    ):
        raise ValueError("provenance does not bind the E5i default")

    mechanisms = validate_mechanisms(
        evidence_dir,
        configurations=configurations,
        contract=contract,
    )
    auto_mechanism = mechanisms[candidate_configuration]
    if not math.isclose(
        auto_mechanism["compute_buffer_mib"],
        contract["prior_evidence"]["baseline_auto_compute_buffer_mib"],
        abs_tol=0.01,
    ):
        raise ValueError("auto compute buffer differs from prior evidence")

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
        validate_pareto64_invocation(cell_dir, configurations[configuration])

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
        exact_predictions = all(
            cell["probe"]["correct"] == contract["selected"]["reference_correct"]
            and cell["probe"]["reference_prediction_mismatches"]
            == contract["acceptance"]["reference_prediction_mismatches"]
            for cell in config_cells
        )
        performance[name] = {
            "flash_attention": configuration["flash_attention"],
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
                "exact_selected_predictions": exact_predictions,
            },
            "repetitions": config_cells,
            "requests_per_second": summarize(
                [cell["probe"]["requests_per_second"] for cell in config_cells]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in raw_cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in raw_cases]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in raw_cases]),
            "cached_tokens": summarize(
                [float(case["cached_tokens"]) for case in raw_cases]
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
        raise ValueError("observed prompt bound differs from prior evidence")
    boundary = evaluate_boundary(
        performance,
        acceptance=contract["acceptance"],
        baseline_configuration=baseline_configuration,
        candidate_configuration=candidate_configuration,
    )
    run_id = str(provenance["github_run_id"])
    artifact_name = (
        f"{contract['artifact_name_prefix']}-{run_id}-"
        f"{provenance['github_run_attempt']}"
    )
    return {
        "schema_version": 1,
        "experiment_id": "E5i",
        "status": (
            "valid_selected_inference_flash_attention"
            if boundary["passed"]
            else "valid_selected_inference_no_flash_attention_win"
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
            "default_configuration": candidate_configuration,
            "validated_default_configuration": boundary[
                "validated_default_configuration"
            ],
        },
        "validation": {
            "all_input_hashes_match": True,
            "launch_recomputed_selected_plan": True,
            "exact_model_and_runtime_verified": True,
            "zero_request_failures": True,
            "fresh_server_per_cell": True,
            "runtime_buffer_proof_observed": True,
            "flash_argument_bound_in_every_recipe": True,
            "flash_mechanism_observed_for_every_profile": True,
            "cached_prefix_observed_in_every_measured_request": True,
            "quality_drift_treated_as_profile_ineligibility": True,
            "flash_attention_claim_allowed": boundary["passed"],
        },
        "maximum_observed_prompt_tokens": maximum_prompt_tokens,
        "performance": performance,
        "runtime_buffer_patterns_observed": required_patterns,
        "hypothesis": boundary,
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
