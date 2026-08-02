#!/usr/bin/env python3
"""Validate the E9a compounded E5b-versus-E7c native service comparison."""

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
    from experiments.e7a_ingest import validate_runtime_closure
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
    from e7a_ingest import validate_runtime_closure


ARTIFACT_INPUTS = {
    "manifest": "selected-manifest.json",
    "models": "models-manifest.json",
    "tasks": "tasks-manifest.json",
    "e5b_manifest": "e5b-manifest.json",
    "e5b_report": "e5b-report.md",
    "e5b_contract": "e5b-contract.json",
    "e7c_manifest": "e7c-manifest.json",
    "e7c_contract": "e7c-contract.json",
    "e7c_runtime_contract": "e7c-runtime-contract.json",
}


def expected_server_argv(
    server: str,
    model: str,
    *,
    candidate: str,
    profile_name: str,
) -> list[str]:
    """Return the exact historically derived E5b or E7c service argv."""
    common = [
        server,
        "--model",
        model,
        "--alias",
        candidate,
        "--threads",
        "4",
        "--threads-batch",
        "4",
    ]
    if profile_name == "e5b_earliest":
        return common + [
            "--ctx-size",
            "2048",
            "--parallel",
            "1",
            "--cont-batching",
            "--no-cache-prompt",
            "--host",
            "127.0.0.1",
            "--port",
            "18081",
            "--no-webui",
            "--metrics",
            "--slots",
            "--jinja",
            "--temp",
            "0.0",
            "--seed",
            "424242",
            "--log-colors",
            "off",
        ]
    if profile_name == "e7c_final":
        return common + [
            "--ctx-size",
            "256",
            "--cache-type-k",
            "f16",
            "--cache-type-v",
            "f16",
            "--flash-attn",
            "auto",
            "--parallel",
            "1",
            "--cont-batching",
            "--cache-prompt",
            "--host",
            "127.0.0.1",
            "--port",
            "18081",
            "--no-webui",
            "--metrics",
            "--slots",
            "--jinja",
            "--temp",
            "0.0",
            "--seed",
            "424242",
            "--log-colors",
            "off",
            "--batch-size",
            "64",
            "--ubatch-size",
            "64",
        ]
    raise ValueError(f"unknown E9a profile: {profile_name}")


def validate_recipe(recipe: dict[str, Any], profile_name: str, contract: dict[str, Any]) -> None:
    profile = contract["profiles"][profile_name]
    selected = contract["selected"]
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E9a"
        or recipe.get("profile_name") != profile_name
        or recipe.get("source") != profile["source"]
        or recipe.get("build") != profile["build"]
        or recipe.get("service") != profile["service"]
        or model.get("sha256") != selected["model_sha256"]
        or model.get("size_bytes") != selected["model_size_bytes"]
        or not isinstance(server, str)
        or not server.endswith("/bin/llama-server")
        or not isinstance(model_path, str)
        or not model_path.endswith(".gguf")
        or profile["source"]["commit"][:9] not in recipe.get("server_version", "")
    ):
        raise ValueError(f"{profile_name} recipe differs from the frozen contract")
    expected = expected_server_argv(
        server,
        model_path,
        candidate=selected["candidate"],
        profile_name=profile_name,
    )
    if recipe.get("argv") != expected:
        raise ValueError(f"{profile_name} argv differs from the historical recipe")


def validate_builds(evidence_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    builds: dict[str, Any] = {}
    source = load_object(evidence_dir / "source.json")
    for profile_name, profile in contract["profiles"].items():
        build_dir = evidence_dir / "builds" / profile_name
        if source.get(profile_name) != profile["source"]:
            raise ValueError(f"{profile_name} source proof differs")
        command = load_object(build_dir / "configure-command.json")
        if command.get("cmake_arguments") != profile["build"]["cmake_arguments"]:
            raise ValueError(f"{profile_name} configure command differs")
        cache = (build_dir / "CMakeCache.txt").read_text(errors="replace")
        cache_lines = cache.splitlines()
        for argument in profile["build"]["cmake_arguments"]:
            if not argument.startswith("-D") or "=" not in argument:
                continue
            name, value = argument[2:].split("=", 1)
            if value in {"ON", "OFF"} and not any(
                line.startswith(f"{name}:") and line.endswith(f"={value}")
                for line in cache_lines
            ):
                raise ValueError(f"{profile_name} CMake cache differs for {name}")
        version = (build_dir / "server-version.txt").read_text(errors="replace")
        if profile["source"]["commit"][:9] not in version:
            raise ValueError(f"{profile_name} server version differs")
        process = parse_time_output((build_dir / "build-time.log").read_text())
        process["elapsed_seconds"] = elapsed_seconds(process["elapsed"])
        if process["elapsed_seconds"] <= 0:
            raise ValueError(f"{profile_name} build duration is invalid")
        closure = validate_runtime_closure(build_dir / "runtime-closure.json")
        dependencies = sorted(
            {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
        )
        forbidden = set(profile["build"].get("forbidden_dynamic_dependency_basenames", []))
        if forbidden.intersection(dependencies):
            raise ValueError(f"{profile_name} retains a forbidden dependency")
        builds[profile_name] = {
            "configure_command": command,
            "cmake_cache_sha256": sha256_file(build_dir / "CMakeCache.txt"),
            "server_version": version.strip(),
            "build_process": process,
            "runtime_closure": closure,
            "dynamic_dependency_basenames": dependencies,
        }
    return builds


def validate_cell(
    cell_dir: Path,
    *,
    profile_name: str,
    repetition: int,
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    recipe = load_object(cell_dir / "recipe.json")
    validate_recipe(recipe, profile_name, contract)
    timed = (cell_dir / "server-time.log").read_text(errors="replace")
    commands = [line for line in timed.splitlines() if "Command being timed:" in line]
    if len(commands) != 1 or not all(argument in commands[0] for argument in recipe["argv"]):
        raise ValueError(f"{cell_dir.name} timed command differs from its recipe")
    readiness = load_object(cell_dir / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not math.isfinite(ready_ms)
        or not 0 <= ready_ms <= contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError(f"{cell_dir.name} readiness differs")
    service = contract["profiles"][profile_name]["service"]
    probe_config: dict[str, Any] = {"client_concurrency": contract["request"]["client_concurrency"]}
    request_cache = service["request_cache_prompt"]
    if request_cache is not None:
        probe_config["prompt_cache"] = request_cache
    if service["warmup_slot_ids"] is not None:
        probe_config["warmup_slot_ids"] = service["warmup_slot_ids"]
    raw_probe = load_object(cell_dir / "probe.json")
    probe = validate_probe(
        raw_probe,
        configuration=profile_name,
        repetition=repetition,
        config=probe_config,
        contract=contract,
        tasks=tasks,
        references=references,
    )
    cases = raw_probe["cases"]
    cached = [case.get("cached_tokens") for case in cases]
    if any(type(value) is not int or value < 0 for value in cached):
        raise ValueError(f"{cell_dir.name} lacks cache-token evidence")
    if profile_name == contract["execution"]["baseline_profile"]:
        if any(value != contract["acceptance"]["required_baseline_cached_tokens_per_request"] for value in cached):
            raise ValueError("E5b baseline unexpectedly reused cached tokens")
    elif any(value < contract["acceptance"]["minimum_candidate_cached_tokens_per_request"] for value in cached):
        raise ValueError("E7c final profile did not reuse the prefix")
    process_cpu = validate_process_cpu(
        raw_probe,
        cell_dir=cell_dir,
        measured_requests=contract["request"]["measured_tasks"],
    )
    process = parse_time_output(timed)
    shell_exit = int((cell_dir / "server-shell-exit.txt").read_text().strip())
    slots = json.loads((cell_dir / "slots.json").read_text())
    if (
        shell_exit not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process.get("maximum_rss_kib") is None
        or process["maximum_rss_kib"] > contract["acceptance"]["maximum_process_rss_kib"]
        or not isinstance(slots, list)
        or len(slots) != service["server_parallel_slots"]
        or "llamacpp:" not in (cell_dir / "metrics.txt").read_text()
    ):
        raise ValueError(f"{cell_dir.name} process evidence differs")
    return (
        {
            "profile": profile_name,
            "repetition": repetition,
            "ready_ms": float(ready_ms),
            "probe": probe,
            "server_process_cpu": process_cpu,
            "process": process,
            "server_shell_exit_status": shell_exit,
            "slots_observed": len(slots),
        },
        cases,
    )


def summarize_performance(
    cells: list[dict[str, Any]],
    samples: dict[str, list[dict[str, Any]]],
    profile_names: tuple[str, str],
    correct: int,
) -> dict[str, Any]:
    performance: dict[str, Any] = {}
    for profile_name in profile_names:
        profile_cells = [cell for cell in cells if cell["profile"] == profile_name]
        raw_cases = samples[profile_name]
        prediction_maps = []
        for repetition in range(1, len(profile_cells) + 1):
            prediction_maps.append(
                {
                    case["id"]: case["predicted"]
                    for case in raw_cases
                    if case["repetition"] == repetition
                }
            )
        performance[profile_name] = {
            "quality": {
                "correct_per_repetition": [cell["probe"]["correct"] for cell in profile_cells],
                "reference_prediction_mismatches_per_repetition": [
                    cell["probe"]["reference_prediction_mismatches"] for cell in profile_cells
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
            "samples": raw_cases,
            "requests_per_second": summarize([cell["probe"]["requests_per_second"] for cell in profile_cells]),
            "http_ms": summarize([float(case["http_ms"]) for case in raw_cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in raw_cases]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in raw_cases]),
            "cached_tokens": summarize([float(case["cached_tokens"]) for case in raw_cases]),
            "server_cpu_seconds_per_request": summarize(
                [float(cell["server_process_cpu"]["seconds_per_request"]) for cell in profile_cells]
            ),
            "average_server_cores_used": summarize(
                [float(cell["server_process_cpu"]["average_cores_used"]) for cell in profile_cells]
            ),
            "ready_ms": summarize([cell["ready_ms"] for cell in profile_cells]),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in profile_cells]
            ),
        }
    return performance


def evaluate_hypothesis(performance: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    baseline_name = contract["execution"]["baseline_profile"]
    candidate_name = contract["execution"]["candidate_profile"]
    baseline = performance[baseline_name]
    candidate = performance[candidate_name]
    acceptance = contract["acceptance"]
    throughput_ratio = candidate["requests_per_second"]["median"] / baseline["requests_per_second"]["median"]
    median_ratio = candidate["http_ms"]["median"] / baseline["http_ms"]["median"]
    p95_ratio = candidate["http_ms"]["p95"] / baseline["http_ms"]["p95"]
    cpu_ratio = candidate["server_cpu_seconds_per_request"]["median"] / baseline["server_cpu_seconds_per_request"]["median"]
    quality_passed = baseline["quality"]["exact_selected_predictions"] and candidate["quality"]["exact_selected_predictions"]
    dispersion_passed = all(
        performance[name]["requests_per_second"]["coefficient_of_variation"]
        <= acceptance["maximum_throughput_coefficient_of_variation"]
        for name in (baseline_name, candidate_name)
    )
    gates = {
        "quality_passed": quality_passed,
        "cache_mechanisms_passed": baseline["cached_tokens"]["max"] == 0 and candidate["cached_tokens"]["min"] >= acceptance["minimum_candidate_cached_tokens_per_request"],
        "throughput_gate_passed": throughput_ratio >= acceptance["minimum_throughput_ratio"],
        "median_latency_gate_passed": median_ratio <= acceptance["maximum_median_http_latency_ratio"],
        "p95_latency_gate_passed": p95_ratio <= acceptance["maximum_p95_http_latency_ratio"],
        "cpu_time_gate_passed": cpu_ratio <= acceptance["maximum_cpu_seconds_per_request_ratio"],
        "scheduler_dispersion_gate_passed": dispersion_passed,
    }
    passed = all(gates.values())
    return {
        "passed": passed,
        "baseline_profile": baseline_name,
        "candidate_profile": candidate_name,
        "selected_profile": candidate_name if passed else baseline_name,
        **gates,
        "throughput_ratio": throughput_ratio,
        "median_http_latency_ratio": median_ratio,
        "p95_http_latency_ratio": p95_ratio,
        "cpu_seconds_per_request_ratio": cpu_ratio,
        "ready_time_ratio": candidate["ready_ms"]["median"] / baseline["ready_ms"]["median"],
        "maximum_rss_ratio": candidate["maximum_rss_kib"]["max"] / baseline["maximum_rss_kib"]["max"],
        "weighted_score_used": False,
    }


def build_manifest(
    evidence_dir: Path,
    contract_path: Path,
    root: Path,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E9a":
        raise ValueError("invalid E9a contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E9a")
    for name, artifact_name in ARTIFACT_INPUTS.items():
        source = root / contract["inputs"][f"{name}_path"]
        expected = contract["inputs"][f"{name}_sha256"]
        if sha256_file(source) != expected or sha256_file(evidence_dir / artifact_name) != expected:
            raise ValueError(f"E9a {name} input differs")
    for commit_key, path, expected in (
        ("e5b_run_git_commit", ".github/workflows/selected-inference.yml", contract["inputs"]["e5b_historical_workflow_sha256"]),
        ("e5b_run_git_commit", "pareto64/runtime.py", contract["inputs"]["e5b_historical_launcher_sha256"]),
        ("e7c_run_git_commit", ".github/workflows/current-runtime-launch.yml", contract["inputs"]["e7c_historical_workflow_sha256"]),
    ):
        captured = evidence_dir / "historical" / f"{commit_key}-{Path(path).name}"
        if sha256_file(captured) != expected:
            raise ValueError(f"historical recipe proof differs for {path}")
    for profile in contract["profiles"].values():
        for patch in profile["source"].get("patches", []):
            if sha256_file(root / patch["path"]) != patch["sha256"]:
                raise ValueError(f"E9a patch differs: {patch['path']}")
    final_source = contract["profiles"]["e7c_final"]["source"]
    if (
        sha256_file(evidence_dir / "source-diff.patch")
        != final_source["source_diff_sha256"]
        or (evidence_dir / "patched-files.txt").read_text().splitlines()
        != final_source["changed_files"]
    ):
        raise ValueError("E9a final source diff differs")
    builds = validate_builds(evidence_dir, contract)
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["manifest_path"]),
        contract["selected"]["candidate"],
    )
    correct = sum(references[task["id"]] == task["answer"] for task in tasks)
    if correct != contract["selected"]["reference_correct"]:
        raise ValueError("E9a reference quality differs")
    execution = contract["execution"]
    profiles = (execution["baseline_profile"], execution["candidate_profile"])
    expected_pairs = {
        (name, repetition)
        for name in profiles
        for repetition in range(1, execution["repetitions_per_profile"] + 1)
    }
    order = execution["order"]
    if {(item["profile"], item["repetition"]) for item in order} != expected_pairs or len(order) != len(expected_pairs):
        raise ValueError("E9a execution order is not complete")
    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E9a":
        raise ValueError("E9a provenance differs")
    cells: list[dict[str, Any]] = []
    samples: dict[str, list[dict[str, Any]]] = {name: [] for name in profiles}
    for index, item in enumerate(order, 1):
        profile_name = item["profile"]
        repetition = item["repetition"]
        cell_dir = evidence_dir / "cells" / f"{index:02d}-{profile_name}-r{repetition}"
        cell, raw_cases = validate_cell(
            cell_dir,
            profile_name=profile_name,
            repetition=repetition,
            contract=contract,
            tasks=tasks,
            references=references,
        )
        cells.append(cell)
        samples[profile_name].extend(
            {"repetition": repetition, **case} for case in raw_cases
        )
    performance = summarize_performance(cells, samples, profiles, correct)
    hypothesis = evaluate_hypothesis(performance, contract)
    platform = {
        **parse_lscpu((evidence_dir / "lscpu.txt").read_text()),
        "uname": (evidence_dir / "uname.txt").read_text().strip(),
        "python": (evidence_dir / "python-version.txt").read_text().strip(),
        "compiler": (evidence_dir / "compiler.txt").read_text().strip(),
        "environment": load_object(evidence_dir / "environment.json"),
    }
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E9a did not run on the frozen native architecture")
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E9a",
        "status": "valid_final_service_win" if hypothesis["passed"] else "valid_final_service_no_win",
        "scope": contract["scope"],
        "source": {
            "artifact_name": f"e9a-final-service-{run_id}-{provenance['github_run_attempt']}",
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "artifact_retention_days": 90,
        },
        "contract": contract,
        "provenance": provenance,
        "platform": platform,
        "selection": {
            "candidate": contract["selected"]["candidate"],
            "correct": correct,
            "total": len(tasks),
            "accuracy": correct / len(tasks),
            "model_sha256": contract["selected"]["model_sha256"],
            "model_size_bytes": contract["selected"]["model_size_bytes"],
        },
        "validation": {
            "all_input_hashes_match": True,
            "historical_recipes_reconstructed_from_retained_commits": True,
            "native_arm64_same_job": True,
            "fresh_server_per_cell": True,
            "reverse_balanced_four_repetitions": True,
            "raw_answers_retained_in_manifest": True,
            "measured_window_process_cpu_validated": True,
            "binary_and_dependency_closures_hashed": True,
            "compounded_result_only": True,
            "single_mechanism_attribution_allowed": False,
            "energy_claim_allowed": False,
            "weighted_score_used": False,
            "claim_scope": contract["claim_boundary"],
        },
        "builds": builds,
        "performance": performance,
        "hypothesis": hypothesis,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    manifest = build_manifest(arguments.evidence_dir, arguments.contract, arguments.root)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
