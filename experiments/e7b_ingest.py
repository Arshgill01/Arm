#!/usr/bin/env python3
"""Validate the E7b loopback HTTP OpenSSL dependency-pruning ablation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e2_ingest import elapsed_seconds
    from experiments.e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
    )
    from experiments.e7a_ingest import (
        ARTIFACT_INPUTS,
        summarize_service_performance,
        validate_cell,
        validate_runtime_closure,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e2_ingest import elapsed_seconds
    from e5b_ingest import load_object, load_tasks, reference_predictions, sha256_file
    from e7a_ingest import (
        ARTIFACT_INPUTS,
        summarize_service_performance,
        validate_cell,
        validate_runtime_closure,
    )


def dependency_basenames(
    closure: dict[str, Any], *, system_only: bool = False
) -> set[str]:
    names = set()
    for dependency in closure["runtime_dependencies"]:
        if system_only and dependency["build_local"]:
            continue
        names.add(Path(dependency["resolved_path"]).name)
    return names


def validate_source_and_builds(
    evidence_dir: Path,
    contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = load_object(evidence_dir / "source.json")
    runtime = contract["runtime"]
    if (
        source.get("commit") != runtime["commit"]
        or source.get("tag") != runtime["tag"]
        or source.get("patches_applied")
        != [patch["name"] for patch in runtime["patches"]]
        or sha256_file(evidence_dir / "source-diff.patch")
        != runtime["source_diff_sha256"]
        or (evidence_dir / "patched-files.txt").read_text().splitlines()
        != runtime["changed_files"]
    ):
        raise ValueError("E7b source proof differs from the frozen runtime")

    builds: dict[str, Any] = {}
    for profile_name, profile in contract["build"]["profiles"].items():
        build_dir = evidence_dir / "builds" / profile_name
        cache_lines = set(
            (build_dir / "CMakeCache.txt").read_text(errors="replace").splitlines()
        )
        expected_openssl = "ON" if profile["llama_openssl"] else "OFF"
        if (
            not set(contract["build"]["common_cmake_cache_entries"]).issubset(
                cache_lines
            )
            or f"LLAMA_OPENSSL:BOOL={expected_openssl}" not in cache_lines
        ):
            raise ValueError(f"{profile_name} CMake cache differs from E7b")
        commands = (build_dir / "build-commands.txt").read_text(errors="replace")
        for pattern in profile["required_command_patterns"]:
            if pattern not in commands:
                raise ValueError(f"{profile_name} build commands lack {pattern}")
        for pattern in profile["forbidden_command_patterns"]:
            if pattern in commands:
                raise ValueError(f"{profile_name} unexpectedly uses {pattern}")
        version = (build_dir / "server-version.txt").read_text(errors="replace")
        if runtime["commit"][:9] not in version:
            raise ValueError(f"{profile_name} server version differs")
        build_process = parse_time_output(
            (build_dir / "build-time.log").read_text(encoding="utf-8")
        )
        elapsed = elapsed_seconds(build_process["elapsed"])
        if elapsed <= 0:
            raise ValueError(f"{profile_name} build time is invalid")
        build_process["elapsed_seconds"] = elapsed
        closure = validate_runtime_closure(build_dir / "runtime-closure.json")
        builds[profile_name] = {
            "llama_openssl": profile["llama_openssl"],
            "server_version": version.strip(),
            "build_process": build_process,
            "runtime_closure": closure,
            "dependency_basenames": sorted(dependency_basenames(closure)),
            "system_dependency_basenames": sorted(
                dependency_basenames(closure, system_only=True)
            ),
        }
    return source, builds


def evaluate_hypothesis(
    performance: dict[str, Any],
    builds: dict[str, Any],
    acceptance: dict[str, Any],
    baseline_profile: str,
    candidate_profile: str,
) -> dict[str, Any]:
    baseline = performance[baseline_profile]
    candidate = performance[candidate_profile]
    baseline_closure = builds[baseline_profile]["runtime_closure"]["total_size_bytes"]
    candidate_closure = builds[candidate_profile]["runtime_closure"][
        "total_size_bytes"
    ]
    baseline_build = builds[baseline_profile]["build_process"]["elapsed_seconds"]
    candidate_build = builds[candidate_profile]["build_process"]["elapsed_seconds"]
    positive = (
        baseline["requests_per_second"]["median"],
        baseline["http_ms"]["median"],
        baseline["http_ms"]["p95"],
        baseline["server_cpu_seconds_per_request"]["median"],
        baseline["ready_ms"]["median"],
        baseline["maximum_rss_kib"]["max"],
        baseline_closure,
        baseline_build,
    )
    if min(positive) <= 0:
        raise ValueError("E7b baseline contains a non-positive metric")

    throughput_ratio = (
        candidate["requests_per_second"]["median"]
        / baseline["requests_per_second"]["median"]
    )
    median_latency_ratio = candidate["http_ms"]["median"] / baseline["http_ms"][
        "median"
    ]
    p95_latency_ratio = candidate["http_ms"]["p95"] / baseline["http_ms"]["p95"]
    cpu_ratio = (
        candidate["server_cpu_seconds_per_request"]["median"]
        / baseline["server_cpu_seconds_per_request"]["median"]
    )
    ready_ratio = candidate["ready_ms"]["median"] / baseline["ready_ms"]["median"]
    rss_increase = (
        candidate["maximum_rss_kib"]["max"]
        - baseline["maximum_rss_kib"]["max"]
    )
    closure_ratio = candidate_closure / baseline_closure
    build_ratio = candidate_build / baseline_build

    baseline_dependencies = set(builds[baseline_profile]["dependency_basenames"])
    candidate_dependencies = set(builds[candidate_profile]["dependency_basenames"])
    baseline_system = set(builds[baseline_profile]["system_dependency_basenames"])
    candidate_system = set(builds[candidate_profile]["system_dependency_basenames"])
    required_baseline = set(
        acceptance["required_baseline_system_dependency_basenames"]
    )
    forbidden_candidate = set(
        acceptance["forbidden_candidate_system_dependency_basenames"]
    )
    removed_dependencies = sorted(baseline_dependencies - candidate_dependencies)
    new_dependencies = sorted(candidate_dependencies - baseline_dependencies)

    dependency_pruning_passed = (
        required_baseline.issubset(baseline_system)
        and candidate_system.isdisjoint(forbidden_candidate)
        and len(new_dependencies)
        <= acceptance["maximum_new_candidate_dependency_count"]
    )
    quality_passed = candidate["quality"]["exact_selected_predictions"]
    throughput_passed = throughput_ratio >= acceptance["minimum_throughput_ratio"]
    closure_passed = closure_ratio <= acceptance["maximum_runtime_closure_ratio"]
    latency_passed = (
        median_latency_ratio
        <= acceptance["maximum_median_http_latency_ratio"]
        and p95_latency_ratio <= acceptance["maximum_p95_http_latency_ratio"]
    )
    cpu_passed = cpu_ratio <= acceptance["maximum_cpu_seconds_per_request_ratio"]
    ready_passed = ready_ratio <= acceptance["maximum_ready_time_ratio"]
    rss_passed = rss_increase <= acceptance["maximum_candidate_rss_increase_kib"]
    build_passed = build_ratio <= acceptance["maximum_build_seconds_ratio"]
    passed = all(
        (
            dependency_pruning_passed,
            quality_passed,
            throughput_passed,
            closure_passed,
            latency_passed,
            cpu_passed,
            ready_passed,
            rss_passed,
            build_passed,
        )
    )
    return {
        "passed": passed,
        "baseline_profile": baseline_profile,
        "candidate_profile": candidate_profile,
        "selected_profile": candidate_profile if passed else baseline_profile,
        "dependency_pruning_passed": dependency_pruning_passed,
        "quality_passed": quality_passed,
        "throughput_guardrail_passed": throughput_passed,
        "runtime_closure_guardrail_passed": closure_passed,
        "latency_guardrail_passed": latency_passed,
        "cpu_time_guardrail_passed": cpu_passed,
        "readiness_guardrail_passed": ready_passed,
        "rss_guardrail_passed": rss_passed,
        "build_cost_guardrail_passed": build_passed,
        "required_baseline_system_dependencies": sorted(required_baseline),
        "forbidden_candidate_system_dependencies": sorted(forbidden_candidate),
        "removed_dependencies": removed_dependencies,
        "new_candidate_dependencies": new_dependencies,
        "throughput_ratio": throughput_ratio,
        "median_http_latency_ratio": median_latency_ratio,
        "p95_http_latency_ratio": p95_latency_ratio,
        "cpu_seconds_per_request_ratio": cpu_ratio,
        "ready_time_ratio": ready_ratio,
        "candidate_rss_increase_kib": rss_increase,
        "runtime_closure_ratio": closure_ratio,
        "build_seconds_ratio": build_ratio,
        "weighted_score_used": False,
    }


def build_manifest(
    evidence_dir: Path,
    contract_path: Path,
    manifest_path: Path,
    models_path: Path,
    tasks_path: Path,
    patch_root: Path,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E7b":
        raise ValueError("invalid E7b contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E7b")
    for name, path in {
        "manifest": manifest_path,
        "models": models_path,
        "tasks": tasks_path,
    }.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if (
            sha256_file(path) != expected
            or sha256_file(evidence_dir / ARTIFACT_INPUTS[name]) != expected
        ):
            raise ValueError(f"E7b {name} input hash differs")
    for patch in contract["runtime"]["patches"]:
        if (
            sha256_file(patch_root / patch["path"]) != patch["sha256"]
            or sha256_file(evidence_dir / "patches" / Path(patch["path"]).name)
            != patch["sha256"]
        ):
            raise ValueError(f"E7b patch {patch['name']} hash differs")
    source, builds = validate_source_and_builds(evidence_dir, contract)

    selected_manifest = load_object(manifest_path)
    tasks = load_tasks(load_object(tasks_path))
    selected_candidate = contract["selected"]["candidate"]
    references = reference_predictions(selected_manifest, selected_candidate)
    correct = sum(references[task["id"]] == task["answer"] for task in tasks)
    if (
        set(references) != {task["id"] for task in tasks}
        or correct != contract["selected"]["reference_correct"]
        or len(tasks) != contract["selected"]["reference_total"]
    ):
        raise ValueError("E7b selected quality differs from E3f")

    execution = contract["execution"]
    baseline = execution["baseline_profile"]
    candidate_profile = execution["candidate_profile"]
    expected_pairs = {
        (profile, repetition)
        for profile in (baseline, candidate_profile)
        for repetition in range(1, execution["repetitions_per_profile"] + 1)
    }
    order = execution["order"]
    if (
        len(order) != len(expected_pairs)
        or {(item.get("profile"), item.get("repetition")) for item in order}
        != expected_pairs
    ):
        raise ValueError("E7b execution order does not cover every cell once")
    provenance = load_object(evidence_dir / "provenance.json")
    if (
        provenance.get("experiment_id") != "E7b"
        or provenance.get("baseline_profile") != baseline
        or provenance.get("candidate_profile") != candidate_profile
    ):
        raise ValueError("E7b provenance differs")

    cells = []
    cell_paths: dict[tuple[str, int], Path] = {}
    for index, item in enumerate(order, 1):
        profile_name = item["profile"]
        repetition = item["repetition"]
        cell_dir = evidence_dir / "cells" / f"{index:02d}-{profile_name}-r{repetition}"
        cell_paths[(profile_name, repetition)] = cell_dir
        cells.append(
            validate_cell(
                cell_dir,
                profile_name,
                repetition,
                contract,
                tasks,
                references,
            )
        )

    performance, maximum_prompt_tokens = summarize_service_performance(
        cells,
        cell_paths,
        (baseline, candidate_profile),
        correct,
    )
    for profile_name in (baseline, candidate_profile):
        performance[profile_name]["build_profile"] = contract["build"]["profiles"][
            profile_name
        ]
    if not performance[baseline]["quality"]["exact_selected_predictions"]:
        raise ValueError("E7b baseline failed to reproduce selected quality")
    hypothesis = evaluate_hypothesis(
        performance,
        builds,
        contract["acceptance"],
        baseline,
        candidate_profile,
    )
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E7b",
        "status": (
            "valid_http_dependency_pruning_candidate"
            if hypothesis["passed"]
            else "valid_http_dependency_pruning_no_win"
        ),
        "scope": "Exact patched b10216 native Arm loopback HTTP dependency ablation",
        "source": {
            "artifact_name": (
                f"e7b-openssl-service-{run_id}-{provenance['github_run_attempt']}"
            ),
            "github_run_url": (
                f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}"
            ),
            "artifact_retention_days": 90,
            "runtime_proof": source,
        },
        "contract": contract,
        "provenance": provenance,
        "platform": {
            **parse_lscpu((evidence_dir / "lscpu.txt").read_text()),
            "uname": (evidence_dir / "uname.txt").read_text().strip(),
            "python": (evidence_dir / "python-version.txt").read_text().strip(),
            "compiler": (evidence_dir / "compiler.txt").read_text().strip(),
        },
        "selection": {
            "candidate": selected_candidate,
            "correct": correct,
            "total": len(tasks),
            "accuracy": correct / len(tasks),
            "model_sha256": contract["selected"]["model_sha256"],
            "model_size_bytes": contract["selected"]["model_size_bytes"],
            "baseline_profile": baseline,
            "candidate_profile": candidate_profile,
            "selected_profile": hypothesis["selected_profile"],
        },
        "validation": {
            "all_input_hashes_match": True,
            "exact_model_verified": True,
            "exact_patch_series_verified": True,
            "matched_native_kleidiai_builds": True,
            "openssl_build_mechanism_verified": True,
            "transitive_runtime_dependencies_inventoried": True,
            "build_local_runtime_closures_hashed": True,
            "fresh_server_per_cell": True,
            "server_pid_bound_in_every_probe": True,
            "measured_window_process_cpu_validated": True,
            "cached_prefix_observed_in_every_measured_request": True,
            "quality_drift_treated_as_rejection": True,
            "http_dependency_pruning_claim_allowed": hypothesis["passed"],
            "https_deployment_supported_by_candidate": False,
            "automatic_product_promotion_allowed": False,
            "security_claim_allowed": False,
            "energy_claim_allowed": False,
            "weighted_score_used": False,
            "claim_scope": contract["claim_boundary"],
        },
        "maximum_observed_prompt_tokens": maximum_prompt_tokens,
        "build_profiles": builds,
        "performance": performance,
        "hypothesis": hypothesis,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--patch-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    manifest = build_manifest(
        arguments.evidence_dir,
        arguments.contract,
        arguments.manifest,
        arguments.models,
        arguments.tasks,
        arguments.patch_root,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
