#!/usr/bin/env python3
"""Validate E18a's workload-trained GCC PGO service comparison."""

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
        validate_probe,
    )
    from experiments.e7a_ingest import (
        summarize_service_performance,
        validate_cell,
        validate_runtime_closure,
    )
    from experiments.e18a_freeze import INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e2_ingest import elapsed_seconds
    from e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from e7a_ingest import (
        summarize_service_performance,
        validate_cell,
        validate_runtime_closure,
    )
    from e18a_freeze import INPUT_PATHS


def validate_profile_inventory(evidence: Path, contract: dict[str, Any]) -> dict:
    inventory = load_object(evidence / "pgo-profile-inventory.json")
    files = inventory.get("files")
    if (
        inventory.get("schema_version") != 1
        or inventory.get("format") != "GCC gcda"
        or not isinstance(files, list)
        or len(files) < contract["training"]["minimum_gcda_files"]
        or inventory.get("file_count") != len(files)
    ):
        raise ValueError("E18a PGO profile inventory differs")
    total = 0
    paths: set[str] = set()
    for item in files:
        relative = Path(str(item.get("path", "")))
        path = evidence / "pgo-data" / relative
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or relative.as_posix() in paths
            or not path.is_file()
            or type(size) is not int
            or size <= 0
            or path.stat().st_size != size
            or sha256_file(path) != digest
        ):
            raise ValueError("E18a PGO profile file differs")
        paths.add(relative.as_posix())
        total += size
    if total != inventory.get("total_size_bytes"):
        raise ValueError("E18a PGO profile byte total differs")
    return inventory


def timed_build(path: Path) -> dict[str, Any]:
    process = parse_time_output(path.read_text())
    seconds = elapsed_seconds(process["elapsed"])
    if process["exit_status"] != 0 or seconds <= 0:
        raise ValueError(f"invalid E18a build timing: {path}")
    process["elapsed_seconds"] = seconds
    return process


def validate_source_and_builds(
    evidence: Path, contract: dict[str, Any]
) -> tuple[dict, dict, dict]:
    source = load_object(evidence / "source.json")
    runtime = contract["runtime"]
    if (
        source.get("commit") != runtime["commit"]
        or source.get("tag") != runtime["tag"]
        or source.get("patches_applied")
        != [patch["name"] for patch in runtime["patches"]]
        or sha256_file(evidence / "source-diff.patch")
        != runtime["source_diff_sha256"]
        or (evidence / "patched-files.txt").read_text().splitlines()
        != runtime["changed_files"]
    ):
        raise ValueError("E18a source proof differs")

    generate_commands = (evidence / "training/generate-build-commands.txt").read_text(
        errors="replace"
    )
    generate_flag = contract["training"]["profile_generate_flags"]
    if generate_flag not in generate_commands or "-fprofile-use=" in generate_commands:
        raise ValueError("E18a profile-generate build commands differ")
    generate_cache = (evidence / "training/generate-CMakeCache.txt").read_text(
        errors="replace"
    )
    if generate_flag not in generate_cache:
        raise ValueError("E18a profile-generate cache differs")
    generate_process = timed_build(evidence / "training/generate-build-time.log")

    builds: dict[str, Any] = {}
    for profile, definition in contract["build"]["profiles"].items():
        directory = evidence / "builds" / profile
        cache_lines = set(
            (directory / "CMakeCache.txt").read_text(errors="replace").splitlines()
        )
        if not set(contract["build"]["common_cmake_cache_entries"]).issubset(
            cache_lines
        ):
            raise ValueError(f"E18a {profile} CMake cache differs")
        commands = (directory / "build-commands.txt").read_text(errors="replace")
        if any(pattern not in commands for pattern in definition["required_command_patterns"]):
            raise ValueError(f"E18a {profile} build lacks required PGO flags")
        if any(pattern in commands for pattern in definition["forbidden_command_patterns"]):
            raise ValueError(f"E18a {profile} build contains forbidden PGO flags")
        version = (directory / "server-version.txt").read_text(errors="replace")
        if runtime["commit"][:9] not in version:
            raise ValueError(f"E18a {profile} server version differs")
        closure = validate_runtime_closure(directory / "runtime-closure.json")
        builds[profile] = {
            "pgo": definition["pgo"],
            "server_version": version.strip(),
            "build_process": timed_build(directory / "build-time.log"),
            "runtime_closure": closure,
            "cmake_cache_sha256": sha256_file(directory / "CMakeCache.txt"),
            "build_commands_sha256": sha256_file(directory / "build-commands.txt"),
            "build_log_sha256": sha256_file(directory / "build.log"),
        }
    return source, builds, generate_process


def validate_training(
    evidence: Path,
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> dict[str, Any]:
    training = evidence / "training"
    version = (training / "server-version.txt").read_text(errors="replace")
    if contract["runtime"]["commit"][:9] not in version:
        raise ValueError("E18a training server version differs")
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if len(model_line) != 2 or model_line[0] != contract["selected"]["model_sha256"]:
        raise ValueError("E18a training model differs")
    raw = load_object(training / "probe.json")
    probe = validate_probe(
        raw,
        configuration="pgo_training",
        repetition=1,
        config=contract["service"],
        contract=contract,
        tasks=tasks,
        references=references,
        require_selected_quality=True,
    )
    process = parse_time_output((training / "server-time.log").read_text())
    if (
        process["exit_status"]
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or probe["correct"] != contract["selected"]["reference_correct"]
        or probe["reference_prediction_mismatches"] != 0
        or probe["failures"] != 0
    ):
        raise ValueError("E18a training pass differs")
    return {
        "server_version": version.strip(),
        "probe": probe,
        "process": process,
        "probe_sha256": sha256_file(training / "probe.json"),
        "performance_claim_allowed": False,
    }


def evaluate(
    performance: dict[str, Any], builds: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    baseline_name = contract["execution"]["baseline_profile"]
    candidate_name = contract["execution"]["candidate_profile"]
    baseline = performance[baseline_name]
    candidate = performance[candidate_name]
    acceptance = contract["acceptance"]
    ratios = {
        "throughput": candidate["requests_per_second"]["median"]
        / baseline["requests_per_second"]["median"],
        "median_http_latency": candidate["http_ms"]["median"]
        / baseline["http_ms"]["median"],
        "p95_http_latency": candidate["http_ms"]["p95"]
        / baseline["http_ms"]["p95"],
        "cpu_seconds_per_request": candidate["server_cpu_seconds_per_request"]["median"]
        / baseline["server_cpu_seconds_per_request"]["median"],
        "ready_time": candidate["ready_ms"]["median"] / baseline["ready_ms"]["median"],
        "maximum_rss": candidate["maximum_rss_kib"]["max"]
        / baseline["maximum_rss_kib"]["max"],
        "runtime_closure": builds[candidate_name]["runtime_closure"]["total_size_bytes"]
        / builds[baseline_name]["runtime_closure"]["total_size_bytes"],
    }
    gates = {
        "quality": candidate["quality"]["exact_selected_predictions"],
        "throughput": ratios["throughput"] >= acceptance["minimum_throughput_ratio"],
        "median_http_latency": ratios["median_http_latency"]
        <= acceptance["maximum_median_http_latency_ratio"],
        "p95_http_latency": ratios["p95_http_latency"]
        <= acceptance["maximum_p95_http_latency_ratio"],
        "cpu_seconds_per_request": ratios["cpu_seconds_per_request"]
        <= acceptance["maximum_cpu_seconds_per_request_ratio"],
        "ready_time": ratios["ready_time"] <= acceptance["maximum_ready_time_ratio"],
        "maximum_rss": ratios["maximum_rss"] <= acceptance["maximum_candidate_rss_ratio"],
        "runtime_closure": ratios["runtime_closure"]
        <= acceptance["maximum_runtime_closure_ratio"],
        "throughput_dispersion": candidate["requests_per_second"][
            "coefficient_of_variation"
        ]
        <= acceptance["maximum_candidate_throughput_cv"],
    }
    return {
        "passed": all(gates.values()),
        "selected_profile": candidate_name if all(gates.values()) else baseline_name,
        "ratios": ratios,
        "gates": gates,
        "weighted_score_used": False,
    }


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("experiment_id") != "E18a" or load_object(evidence / "contract.json") != contract:
        raise ValueError("E18a contract differs")
    for name, relative in INPUT_PATHS.items():
        if (
            sha256_file(root / relative) != contract["inputs"][f"{name}_sha256"]
            or sha256_file(evidence / "frozen-inputs" / relative)
            != contract["inputs"][f"{name}_sha256"]
        ):
            raise ValueError(f"E18a input differs for {name}")
    source, builds, generate_process = validate_source_and_builds(evidence, contract)
    profile_inventory = validate_profile_inventory(evidence, contract)
    tasks = load_tasks(load_object(root / INPUT_PATHS["tasks"]))
    references = reference_predictions(
        load_object(root / INPUT_PATHS["manifest"]), contract["selected"]["candidate"]
    )
    correct = sum(references[task["id"]] == task["answer"] for task in tasks)
    if correct != contract["selected"]["reference_correct"]:
        raise ValueError("E18a selected quality differs")
    training = validate_training(evidence, contract, tasks, references)

    execution = contract["execution"]
    order = execution["order"]
    expected = {
        (profile, repetition)
        for profile in (execution["baseline_profile"], execution["candidate_profile"])
        for repetition in range(1, execution["repetitions_per_profile"] + 1)
    }
    if len(order) != len(expected) or {
        (item.get("profile"), item.get("repetition")) for item in order
    } != expected:
        raise ValueError("E18a execution order differs")
    cells = []
    paths: dict[tuple[str, int], Path] = {}
    for index, item in enumerate(order, start=1):
        directory = evidence / "cells" / (
            f"{index:02d}-{item['profile']}-r{item['repetition']}"
        )
        paths[(item["profile"], item["repetition"])] = directory
        cells.append(
            validate_cell(
                directory,
                item["profile"],
                item["repetition"],
                contract,
                tasks,
                references,
            )
        )
    performance, maximum_prompt_tokens = summarize_service_performance(
        cells,
        paths,
        (execution["baseline_profile"], execution["candidate_profile"]),
        correct,
    )
    if not performance[execution["baseline_profile"]]["quality"][
        "exact_selected_predictions"
    ]:
        raise ValueError("E18a control quality differs")
    hypothesis = evaluate(performance, builds, contract)
    provenance = load_object(evidence / "provenance.json")
    if provenance.get("experiment_id") != "E18a":
        raise ValueError("E18a provenance differs")
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E18a",
        "status": "valid_workload_pgo_win" if hypothesis["passed"] else "valid_workload_pgo_no_win",
        "contract_sha256": sha256_file(contract_path),
        "source": source,
        "platform": {
            **parse_lscpu((evidence / "lscpu.txt").read_text()),
            "uname": (evidence / "uname.txt").read_text().strip(),
            "compiler": (evidence / "compiler.txt").read_text().strip(),
        },
        "github": {
            "run_id": run_id,
            "run_attempt": provenance["github_run_attempt"],
            "run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "artifact_name": f"e18a-workload-pgo-{run_id}-{provenance['github_run_attempt']}",
        },
        "selection": contract["selected"],
        "training": {
            **training,
            "profile_inventory": profile_inventory,
            "generate_build_process": generate_process,
        },
        "builds": builds,
        "performance": performance,
        "hypothesis": hypothesis,
        "maximum_observed_prompt_tokens": maximum_prompt_tokens,
        "validation": {
            "native_arm64": True,
            "exact_source_and_patch_series": True,
            "openssl_off_in_both_measured_builds": True,
            "profile_generate_and_use_mechanisms_verified": True,
            "exact_training_pass_completed": True,
            "all_profile_data_hashed": True,
            "six_reverse_balanced_repetitions_per_profile": True,
            "fresh_process_per_cell": True,
            "exact_quality_before_performance": True,
            "automatic_product_promotion_allowed": False,
        },
        "claim_boundary": contract["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"], "hypothesis": manifest["hypothesis"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
