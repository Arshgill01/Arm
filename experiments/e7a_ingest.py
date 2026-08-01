#!/usr/bin/env python3
"""Validate the E7a LTO service and runtime-footprint ablation."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e2_ingest import elapsed_seconds
    from experiments.e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from experiments.e5j_ingest import validate_process_cpu
    from experiments.e6f_ingest import expected_server_argv, validate_timed_invocation
    from experiments.e7a_runtime_closure import parse_ldd_paths
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e2_ingest import elapsed_seconds
    from e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from e5j_ingest import validate_process_cpu
    from e6f_ingest import expected_server_argv, validate_timed_invocation
    from e7a_runtime_closure import parse_ldd_paths


ARTIFACT_INPUTS = {
    "manifest": "selected-manifest.json",
    "models": "models-manifest.json",
    "tasks": "tasks-manifest.json",
}


def validate_runtime_closure(path: Path) -> dict[str, Any]:
    closure = load_object(path)
    files = closure.get("files")
    dependencies = closure.get("runtime_dependencies")
    build_root = Path(str(closure.get("build_root", "")))
    server_path = Path(str(closure.get("server_path", "")))
    server_relative = closure.get("server_relative_path")
    if (
        closure.get("schema_version") != 1
        or not isinstance(files, list)
        or not files
        or not isinstance(dependencies, list)
        or not build_root.is_absolute()
        or not server_path.is_absolute()
        or not server_path.is_relative_to(build_root)
        or server_path.relative_to(build_root).as_posix() != server_relative
        or closure.get("file_count") != len(files)
        or closure.get("system_dependencies_excluded") is not True
        or server_relative
        not in {item.get("relative_path") for item in files if isinstance(item, dict)}
    ):
        raise ValueError("runtime closure metadata is invalid")
    parsed_dependencies = parse_ldd_paths(str(closure.get("ldd_output", "")))
    if len(parsed_dependencies) != len(dependencies):
        raise ValueError("runtime closure dependency inventory differs from ldd")
    expected_local_paths = {str(server_relative)}
    for parsed, dependency in zip(parsed_dependencies, dependencies):
        if not isinstance(dependency, dict):
            raise TypeError("runtime closure dependency record is invalid")
        resolved = Path(str(dependency.get("resolved_path", "")))
        build_local = resolved.is_absolute() and resolved.is_relative_to(build_root)
        if (
            dependency.get("ldd_path") != parsed.as_posix()
            or dependency.get("build_local") is not build_local
        ):
            raise ValueError("runtime closure dependency record differs from ldd")
        if build_local:
            expected_local_paths.add(resolved.relative_to(build_root).as_posix())
    total = 0
    relative_paths: set[str] = set()
    artifact_paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise TypeError("runtime closure file record is invalid")
        relative = Path(str(item.get("relative_path", "")))
        artifact_relative = Path(str(item.get("artifact_relative_path", "")))
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if (
            relative.is_absolute()
            or artifact_relative.is_absolute()
            or not relative.parts
            or not artifact_relative.parts
            or ".." in relative.parts
            or ".." in artifact_relative.parts
            or type(size) is not int
            or size <= 0
            or not isinstance(digest, str)
            or len(digest) != 64
            or relative.as_posix() in relative_paths
            or artifact_relative.as_posix() in artifact_paths
        ):
            raise ValueError("runtime closure file record is invalid")
        artifact = (path.parent / artifact_relative).resolve()
        if (
            not artifact.is_relative_to(path.parent.resolve())
            or not artifact.is_file()
            or artifact.stat().st_size != size
            or sha256_file(artifact) != digest
        ):
            raise ValueError("runtime closure artifact differs from metadata")
        relative_paths.add(relative.as_posix())
        artifact_paths.add(artifact_relative.as_posix())
        total += size
    if total != closure.get("total_size_bytes"):
        raise ValueError("runtime closure total size differs")
    if relative_paths != expected_local_paths:
        raise ValueError("runtime closure files differ from build-local dependencies")
    return closure


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
        raise ValueError("E7a source proof differs from the frozen runtime")

    builds: dict[str, Any] = {}
    for profile_name, profile in contract["build"]["profiles"].items():
        build_dir = evidence_dir / "builds" / profile_name
        cache_lines = set(
            (build_dir / "CMakeCache.txt").read_text(errors="replace").splitlines()
        )
        expected_lto = "ON" if profile["ggml_lto"] else "OFF"
        if (
            not set(contract["build"]["common_cmake_cache_entries"]).issubset(
                cache_lines
            )
            or f"GGML_LTO:BOOL={expected_lto}" not in cache_lines
        ):
            raise ValueError(f"{profile_name} CMake cache differs from E7a")
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
            "ggml_lto": profile["ggml_lto"],
            "server_version": version.strip(),
            "build_process": build_process,
            "runtime_closure": closure,
        }
    return source, builds


def validate_recipe(
    recipe: dict[str, Any],
    profile_name: str,
    contract: dict[str, Any],
) -> None:
    experiment_id = contract["experiment_id"]
    selected = contract["selected"]
    service = contract["service"]
    model = recipe.get("model", {})
    server_path = recipe.get("server_path")
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != experiment_id
        or recipe.get("profile_name") != profile_name
        or recipe.get("build_profile")
        != contract["build"]["profiles"][profile_name]
        or recipe.get("runtime") != contract["runtime"]
        or recipe.get("service") != service
        or model.get("sha256") != selected["model_sha256"]
        or model.get("size_bytes") != selected["model_size_bytes"]
        or not isinstance(server_path, str)
        or not server_path.endswith("/bin/llama-server")
        or not isinstance(model_path, str)
        or not model_path.endswith(".gguf")
        or contract["runtime"]["commit"][:9]
        not in recipe.get("server_version", "")
    ):
        raise ValueError(f"{profile_name} recipe differs from {experiment_id}")
    expected = expected_server_argv(
        server_path,
        model_path,
        candidate=selected["candidate"],
        service=service,
    )
    if recipe.get("argv") != expected or "--no-repack" in expected:
        raise ValueError(f"{profile_name} server argv differs from {experiment_id}")


def validate_cell(
    cell_dir: Path,
    profile_name: str,
    repetition: int,
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> dict[str, Any]:
    recipe = load_object(cell_dir / "recipe.json")
    validate_recipe(recipe, profile_name, contract)
    validate_timed_invocation(cell_dir, recipe)
    readiness = load_object(cell_dir / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not math.isfinite(ready_ms)
        or ready_ms < 0
    ):
        raise ValueError(f"{cell_dir.name} readiness is invalid")
    raw_probe = load_object(cell_dir / "probe.json")
    probe = validate_probe(
        raw_probe,
        configuration=profile_name,
        repetition=repetition,
        config=contract["service"],
        contract=contract,
        tasks=tasks,
        references=references,
        require_selected_quality=False,
    )
    process_cpu = validate_process_cpu(
        raw_probe,
        cell_dir=cell_dir,
        measured_requests=contract["request"]["measured_tasks"],
    )
    process = parse_time_output((cell_dir / "server-time.log").read_text())
    shell_exit = int((cell_dir / "server-shell-exit.txt").read_text().strip())
    slots = json.loads((cell_dir / "slots.json").read_text())
    if (
        shell_exit not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process.get("maximum_rss_kib") is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
        or not isinstance(slots, list)
        or len(slots) != contract["service"]["server_parallel_slots"]
        or "llamacpp:" not in (cell_dir / "metrics.txt").read_text()
    ):
        raise ValueError(
            f"{cell_dir.name} process evidence missed {contract['experiment_id']}"
        )
    return {
        "profile": profile_name,
        "repetition": repetition,
        "ready_ms": float(ready_ms),
        "probe": probe,
        "server_process_cpu": process_cpu,
        "process": process,
        "server_shell_exit_status": shell_exit,
        "slots_observed": len(slots),
    }


def summarize_service_performance(
    cells: list[dict[str, Any]],
    cell_paths: dict[tuple[str, int], Path],
    profile_names: tuple[str, str],
    correct: int,
) -> tuple[dict[str, Any], int]:
    performance: dict[str, Any] = {}
    maximum_prompt_tokens = 0
    for profile_name in profile_names:
        profile_cells = [cell for cell in cells if cell["profile"] == profile_name]
        probes = [
            load_object(cell_paths[(profile_name, cell["repetition"])] / "probe.json")
            for cell in profile_cells
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
        performance[profile_name] = {
            "quality": {
                "correct_per_repetition": [
                    cell["probe"]["correct"] for cell in profile_cells
                ],
                "reference_prediction_mismatches_per_repetition": [
                    cell["probe"]["reference_prediction_mismatches"]
                    for cell in profile_cells
                ],
                "predictions_stable_between_repetitions": all(
                    item == prediction_maps[0] for item in prediction_maps[1:]
                ),
                "exact_selected_predictions": all(
                    cell["probe"]["correct"] == correct
                    and cell["probe"]["reference_prediction_mismatches"] == 0
                    for cell in profile_cells
                ),
            },
            "repetitions": profile_cells,
            "requests_per_second": summarize(
                [cell["probe"]["requests_per_second"] for cell in profile_cells]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in raw_cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in raw_cases]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in raw_cases]),
            "cached_tokens": summarize(
                [float(case["cached_tokens"]) for case in raw_cases]
            ),
            "prompt_tokens": summarize([float(value) for value in prompt_tokens]),
            "server_cpu_seconds_per_request": summarize(
                [
                    float(cell["server_process_cpu"]["seconds_per_request"])
                    for cell in profile_cells
                ]
            ),
            "average_server_cores_used": summarize(
                [
                    float(cell["server_process_cpu"]["average_cores_used"])
                    for cell in profile_cells
                ]
            ),
            "ready_ms": summarize([cell["ready_ms"] for cell in profile_cells]),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in profile_cells]
            ),
        }
    return performance, maximum_prompt_tokens


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
        raise ValueError("E7a baseline contains a non-positive metric")
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
    quality_passed = candidate["quality"]["exact_selected_predictions"]
    latency_passed = (
        median_latency_ratio
        <= acceptance["maximum_median_http_latency_ratio"]
        and p95_latency_ratio <= acceptance["maximum_p95_http_latency_ratio"]
    )
    cpu_passed = cpu_ratio <= acceptance["maximum_cpu_seconds_per_request_ratio"]
    ready_passed = ready_ratio <= acceptance["maximum_ready_time_ratio"]
    rss_passed = rss_increase <= acceptance["maximum_candidate_rss_increase_kib"]
    build_passed = build_ratio <= acceptance["maximum_build_seconds_ratio"]
    performance_branch = (
        throughput_ratio
        >= acceptance["performance_branch_minimum_throughput_ratio"]
        and closure_ratio
        <= acceptance["performance_branch_maximum_runtime_closure_ratio"]
    )
    footprint_branch = (
        throughput_ratio >= acceptance["footprint_branch_minimum_throughput_ratio"]
        and closure_ratio
        <= acceptance["footprint_branch_maximum_runtime_closure_ratio"]
    )
    common_guardrails = all(
        (quality_passed, latency_passed, cpu_passed, ready_passed, rss_passed, build_passed)
    )
    passed = common_guardrails and (performance_branch or footprint_branch)
    return {
        "passed": passed,
        "baseline_profile": baseline_profile,
        "candidate_profile": candidate_profile,
        "selected_profile": candidate_profile if passed else baseline_profile,
        "common_guardrails_passed": common_guardrails,
        "quality_passed": quality_passed,
        "latency_guardrail_passed": latency_passed,
        "cpu_time_guardrail_passed": cpu_passed,
        "readiness_guardrail_passed": ready_passed,
        "rss_guardrail_passed": rss_passed,
        "build_cost_guardrail_passed": build_passed,
        "performance_branch_passed": performance_branch,
        "footprint_branch_passed": footprint_branch,
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
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E7a":
        raise ValueError("invalid E7a contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E7a")
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
            raise ValueError(f"E7a {name} input hash differs")
    for patch in contract["runtime"]["patches"]:
        if (
            sha256_file(patch_root / patch["path"]) != patch["sha256"]
            or sha256_file(evidence_dir / "patches" / Path(patch["path"]).name)
            != patch["sha256"]
        ):
            raise ValueError(f"E7a patch {patch['name']} hash differs")
    source, builds = validate_source_and_builds(evidence_dir, contract)

    selected_manifest = load_object(manifest_path)
    tasks = load_tasks(load_object(tasks_path))
    candidate = contract["selected"]["candidate"]
    references = reference_predictions(selected_manifest, candidate)
    correct = sum(references[task["id"]] == task["answer"] for task in tasks)
    if (
        set(references) != {task["id"] for task in tasks}
        or correct != contract["selected"]["reference_correct"]
        or len(tasks) != contract["selected"]["reference_total"]
    ):
        raise ValueError("E7a selected quality differs from E3f")

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
        raise ValueError("E7a execution order does not cover every cell once")
    provenance = load_object(evidence_dir / "provenance.json")
    if (
        provenance.get("experiment_id") != "E7a"
        or provenance.get("baseline_profile") != baseline
        or provenance.get("candidate_profile") != candidate_profile
    ):
        raise ValueError("E7a provenance differs")

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
        raise ValueError("E7a baseline failed to reproduce selected quality")
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
        "experiment_id": "E7a",
        "status": (
            "valid_lto_upgrade_candidate"
            if hypothesis["passed"]
            else "valid_lto_no_win"
        ),
        "scope": "Exact patched b10216 native Arm fast-service LTO ablation",
        "source": {
            "artifact_name": (
                f"e7a-lto-service-{run_id}-{provenance['github_run_attempt']}"
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
            "candidate": candidate,
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
            "lto_build_mechanism_verified": True,
            "transitive_runtime_closures_hashed": True,
            "fresh_server_per_cell": True,
            "server_pid_bound_in_every_probe": True,
            "measured_window_process_cpu_validated": True,
            "cached_prefix_observed_in_every_measured_request": True,
            "quality_drift_treated_as_rejection": True,
            "lto_optimization_claim_allowed": hypothesis["passed"],
            "automatic_product_promotion_allowed": False,
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
