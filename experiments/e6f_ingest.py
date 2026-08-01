#!/usr/bin/env python3
"""Validate the E6f current-runtime selected-service upgrade lane."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from experiments.e5j_ingest import validate_process_cpu
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from e5j_ingest import validate_process_cpu


ARTIFACT_INPUTS = {
    "manifest": "selected-manifest.json",
    "models": "models-manifest.json",
    "tasks": "tasks-manifest.json",
}


def expected_server_argv(
    server_path: str,
    model_path: str,
    *,
    candidate: str,
    service: dict[str, Any],
) -> list[str]:
    return [
        server_path,
        "--model",
        model_path,
        "--alias",
        candidate,
        "--threads",
        str(service["threads"]),
        "--threads-batch",
        str(service["threads"]),
        "--ctx-size",
        str(service["context_per_slot"] * service["server_parallel_slots"]),
        "--cache-type-k",
        service["kv_cache_type_k"],
        "--cache-type-v",
        service["kv_cache_type_v"],
        "--flash-attn",
        service["flash_attention"],
        "--parallel",
        str(service["server_parallel_slots"]),
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
        str(service["batch_size"]),
        "--ubatch-size",
        str(service["micro_batch_size"]),
    ]


def validate_runtime_recipe(
    recipe: dict[str, Any],
    *,
    runtime_name: str,
    contract: dict[str, Any],
) -> None:
    runtime = contract["runtimes"][runtime_name]
    selected = contract["selected"]
    service = contract["service"]
    model = recipe.get("model", {})
    server_path = recipe.get("server_path")
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E6f"
        or recipe.get("runtime_name") != runtime_name
        or recipe.get("source") != runtime
        or recipe.get("service") != service
        or model.get("sha256") != selected["model_sha256"]
        or model.get("size_bytes") != selected["model_size_bytes"]
        or not isinstance(server_path, str)
        or not server_path.endswith("/bin/llama-server")
        or not isinstance(model_path, str)
        or not model_path.endswith(".gguf")
        or runtime["commit"][:9] not in recipe.get("server_version", "")
    ):
        raise ValueError("runtime recipe differs from the frozen E6f profile")
    expected = expected_server_argv(
        server_path,
        model_path,
        candidate=selected["candidate"],
        service=service,
    )
    if recipe.get("argv") != expected or "--no-repack" in expected:
        raise ValueError("runtime recipe arguments differ from the selected service")


def validate_timed_invocation(cell_dir: Path, recipe: dict[str, Any]) -> None:
    time_log = (cell_dir / "server-time.log").read_text(
        encoding="utf-8", errors="replace"
    )
    commands = [
        line for line in time_log.splitlines() if "Command being timed:" in line
    ]
    if len(commands) != 1:
        raise ValueError(f"{cell_dir.name} lacks one timed server command")
    command = commands[0]
    required_fragments = [
        recipe["server_path"],
        f"--model {recipe['model']['path']}",
        "--threads 4",
        "--threads-batch 4",
        "--ctx-size 256",
        "--cache-type-k f16",
        "--cache-type-v f16",
        "--flash-attn auto",
        "--parallel 1",
        "--cache-prompt",
        "--batch-size 64",
        "--ubatch-size 64",
    ]
    if any(fragment not in command for fragment in required_fragments):
        raise ValueError(f"{cell_dir.name} timed service invocation differs")


def validate_source_and_builds(
    evidence_dir: Path,
    *,
    contract: dict[str, Any],
) -> dict[str, Any]:
    source = load_object(evidence_dir / "source.json")
    runtimes = contract["runtimes"]
    if (
        source.get("baseline") != {
            "commit": runtimes["baseline"]["commit"],
            "tag": runtimes["baseline"]["tag"],
            "clean": True,
        }
        or source.get("current_patched", {}).get("commit")
        != runtimes["current_patched"]["commit"]
        or source.get("current_patched", {}).get("tag")
        != runtimes["current_patched"]["tag"]
        or source.get("current_patched", {}).get("patches_applied")
        != [patch["name"] for patch in runtimes["current_patched"]["patches"]]
    ):
        raise ValueError("runtime source proof differs from the E6f contract")
    expected_files = [
        "common/reasoning-budget.cpp",
        "ggml/src/ggml-cpu/CMakeLists.txt",
        "ggml/src/ggml-cpu/arch/arm/quants.c",
        "tests/test-reasoning-budget.cpp",
    ]
    observed_files = (evidence_dir / "patched-files.txt").read_text().splitlines()
    if observed_files != expected_files:
        raise ValueError("current runtime patched file inventory differs")
    for patch in runtimes["current_patched"]["patches"]:
        artifact = evidence_dir / "patches" / Path(patch["path"]).name
        if sha256_file(artifact) != patch["sha256"]:
            raise ValueError(f"artifact patch {patch['name']} hash differs")

    build = contract["build"]
    for name, runtime in runtimes.items():
        build_dir = evidence_dir / "builds" / name
        cache = (build_dir / "CMakeCache.txt").read_text(
            encoding="utf-8", errors="replace"
        )
        required = {
            "CMAKE_BUILD_TYPE:STRING=Release",
            "GGML_CPU_KLEIDIAI:BOOL=ON",
            "GGML_NATIVE:BOOL=ON",
            "LLAMA_BUILD_SERVER:BOOL=ON",
            "LLAMA_BUILD_TESTS:BOOL=OFF",
        }
        if not required.issubset(set(cache.splitlines())) or build != {
            "type": "Release",
            "native": True,
            "kleidiai": True,
            "server": True,
            "tests": False,
            "curl": False,
        }:
            raise ValueError(f"{name} build flags differ from the E6f contract")
        version = (build_dir / "server-version.txt").read_text(encoding="utf-8")
        if runtime["commit"][:9] not in version:
            raise ValueError(f"{name} server version differs from frozen source")
        proof = (build_dir / "runtime-proof.stderr.log").read_text(
            encoding="utf-8", errors="replace"
        )
        for pattern in contract["selected"]["required_runtime_buffer_patterns"]:
            if pattern not in proof:
                raise ValueError(f"{name} runtime proof lacks {pattern}")
    return source


def validate_cell(
    cell_dir: Path,
    *,
    runtime_name: str,
    repetition: int,
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> dict[str, Any]:
    recipe = load_object(cell_dir / "recipe.json")
    validate_runtime_recipe(recipe, runtime_name=runtime_name, contract=contract)
    validate_timed_invocation(cell_dir, recipe)
    readiness = load_object(cell_dir / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not math.isfinite(ready_ms)
        or ready_ms < 0
        or ready_ms > contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError(f"{cell_dir.name} missed the readiness contract")
    raw_probe = load_object(cell_dir / "probe.json")
    probe = validate_probe(
        raw_probe,
        configuration=runtime_name,
        repetition=repetition,
        config=contract["service"],
        contract=contract,
        tasks=tasks,
        references=references,
        require_selected_quality=False,
    )
    cpu = validate_process_cpu(
        raw_probe,
        cell_dir=cell_dir,
        measured_requests=contract["request"]["measured_tasks"],
    )
    process = parse_time_output(
        (cell_dir / "server-time.log").read_text(encoding="utf-8")
    )
    shell_exit = int((cell_dir / "server-shell-exit.txt").read_text().strip())
    if (
        shell_exit not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
    ):
        raise ValueError(f"{cell_dir.name} process evidence missed the contract")
    slots = json.loads((cell_dir / "slots.json").read_text(encoding="utf-8"))
    if (
        not isinstance(slots, list)
        or len(slots) != contract["service"]["server_parallel_slots"]
    ):
        raise ValueError(f"{cell_dir.name} slot count differs from the contract")
    if "llamacpp:" not in (cell_dir / "metrics.txt").read_text(encoding="utf-8"):
        raise ValueError(f"{cell_dir.name} lacks server metrics")
    return {
        "runtime": runtime_name,
        "repetition": repetition,
        "ready_ms": float(ready_ms),
        "probe": probe,
        "server_process_cpu": cpu,
        "process": process,
        "server_shell_exit_status": shell_exit,
        "slots_observed": len(slots),
    }


def evaluate_upgrade(
    performance: dict[str, Any],
    *,
    acceptance: dict[str, Any],
    baseline_runtime: str,
    candidate_runtime: str,
) -> dict[str, Any]:
    baseline = performance[baseline_runtime]
    candidate = performance[candidate_runtime]
    if min(
        baseline["requests_per_second"]["median"],
        baseline["http_ms"]["median"],
        baseline["http_ms"]["p95"],
        baseline["server_cpu_seconds_per_request"]["median"],
        baseline["ready_ms"]["median"],
        baseline["maximum_rss_kib"]["max"],
    ) <= 0:
        raise ValueError("historical runtime contains a non-positive metric")
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
        candidate["maximum_rss_kib"]["max"] - baseline["maximum_rss_kib"]["max"]
    )
    quality_passed = candidate["quality"]["exact_selected_predictions"]
    throughput_passed = (
        throughput_ratio >= acceptance["minimum_throughput_retention_ratio"]
    )
    latency_passed = (
        median_latency_ratio <= acceptance["maximum_median_http_latency_ratio"]
        and p95_latency_ratio <= acceptance["maximum_p95_http_latency_ratio"]
    )
    cpu_passed = cpu_ratio <= acceptance["maximum_cpu_seconds_per_request_ratio"]
    ready_passed = ready_ratio <= acceptance["maximum_ready_time_ratio"]
    rss_passed = rss_increase <= acceptance["maximum_candidate_rss_increase_kib"]
    passed = all(
        (
            quality_passed,
            throughput_passed,
            latency_passed,
            cpu_passed,
            ready_passed,
            rss_passed,
        )
    )
    return {
        "passed": passed,
        "baseline_runtime": baseline_runtime,
        "candidate_runtime": candidate_runtime,
        "selected_runtime": candidate_runtime if passed else baseline_runtime,
        "quality_passed": quality_passed,
        "throughput_retention_passed": throughput_passed,
        "latency_retention_passed": latency_passed,
        "cpu_time_retention_passed": cpu_passed,
        "readiness_retention_passed": ready_passed,
        "rss_overhead_passed": rss_passed,
        "throughput_retention_ratio": throughput_ratio,
        "median_http_latency_ratio": median_latency_ratio,
        "p95_http_latency_ratio": p95_latency_ratio,
        "cpu_seconds_per_request_ratio": cpu_ratio,
        "ready_time_ratio": ready_ratio,
        "candidate_rss_increase_kib": rss_increase,
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
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E6f":
        raise ValueError("unsupported E6f contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E6f contract")
    input_paths = {"manifest": manifest_path, "models": models_path, "tasks": tasks_path}
    for name, path in input_paths.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if sha256_file(path) != expected:
            raise ValueError(f"source {name} hash differs from the contract")
        if sha256_file(evidence_dir / ARTIFACT_INPUTS[name]) != expected:
            raise ValueError(f"artifact {name} hash differs from the contract")
    for patch in contract["runtimes"]["current_patched"]["patches"]:
        if sha256_file(patch_root / patch["path"]) != patch["sha256"]:
            raise ValueError(f"source patch {patch['name']} hash differs")

    source = validate_source_and_builds(evidence_dir, contract=contract)
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
        raise ValueError("contract quality differs from retained selection")

    execution = contract["execution"]
    baseline_runtime = execution["baseline_runtime"]
    candidate_runtime = execution["candidate_runtime"]
    order = execution["order"]
    expected_pairs = {
        (name, repetition)
        for name in (baseline_runtime, candidate_runtime)
        for repetition in range(1, execution["repetitions_per_runtime"] + 1)
    }
    observed_pairs = {(item.get("runtime"), item.get("repetition")) for item in order}
    if len(order) != len(expected_pairs) or observed_pairs != expected_pairs:
        raise ValueError("execution order does not cover every runtime cell once")
    provenance = load_object(evidence_dir / "provenance.json")
    if (
        provenance.get("experiment_id") != "E6f"
        or provenance.get("baseline_runtime") != baseline_runtime
        or provenance.get("candidate_runtime") != candidate_runtime
    ):
        raise ValueError("provenance does not bind the E6f runtime pair")

    cells = []
    cell_paths: dict[tuple[str, int], Path] = {}
    for index, item in enumerate(order, 1):
        runtime_name = item["runtime"]
        repetition = item["repetition"]
        cell_dir = evidence_dir / "cells" / f"{index:02d}-{runtime_name}-r{repetition}"
        cell_paths[(runtime_name, repetition)] = cell_dir
        cells.append(
            validate_cell(
                cell_dir,
                runtime_name=runtime_name,
                repetition=repetition,
                contract=contract,
                tasks=tasks,
                references=references,
            )
        )

    performance: dict[str, Any] = {}
    maximum_prompt_tokens = 0
    for name in (baseline_runtime, candidate_runtime):
        runtime_cells = [cell for cell in cells if cell["runtime"] == name]
        probes = [
            load_object(cell_paths[(name, cell["repetition"])] / "probe.json")
            for cell in runtime_cells
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
            for cell in runtime_cells
        )
        performance[name] = {
            "source": contract["runtimes"][name],
            "quality": {
                "correct_per_repetition": [
                    cell["probe"]["correct"] for cell in runtime_cells
                ],
                "reference_prediction_mismatches_per_repetition": [
                    cell["probe"]["reference_prediction_mismatches"]
                    for cell in runtime_cells
                ],
                "predictions_stable_between_repetitions": all(
                    item == prediction_maps[0] for item in prediction_maps[1:]
                ),
                "exact_selected_predictions": exact_predictions,
            },
            "repetitions": runtime_cells,
            "requests_per_second": summarize(
                [cell["probe"]["requests_per_second"] for cell in runtime_cells]
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
                    for cell in runtime_cells
                ]
            ),
            "average_server_cores_used": summarize(
                [
                    float(cell["server_process_cpu"]["average_cores_used"])
                    for cell in runtime_cells
                ]
            ),
            "ready_ms": summarize([cell["ready_ms"] for cell in runtime_cells]),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in runtime_cells]
            ),
        }
    if not performance[baseline_runtime]["quality"]["exact_selected_predictions"]:
        raise ValueError("historical runtime failed to reproduce the selected baseline")
    upgrade = evaluate_upgrade(
        performance,
        acceptance=contract["acceptance"],
        baseline_runtime=baseline_runtime,
        candidate_runtime=candidate_runtime,
    )
    selected_runtime = upgrade["selected_runtime"]
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E6f",
        "status": (
            "valid_current_runtime_upgrade_candidate"
            if upgrade["passed"]
            else "valid_current_runtime_upgrade_rejected"
        ),
        "scope": contract["scope"],
        "source": {
            "artifact_name": (
                f"{contract['artifact_name_prefix']}-{run_id}-"
                f"{provenance['github_run_attempt']}"
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
            **parse_lscpu((evidence_dir / "lscpu.txt").read_text(encoding="utf-8")),
            "uname": (evidence_dir / "uname.txt").read_text().strip(),
            "python": (evidence_dir / "python-version.txt").read_text().strip(),
        },
        "selection": {
            "candidate": candidate,
            "correct": correct,
            "total": len(tasks),
            "accuracy": correct / len(tasks),
            "model_sha256": contract["selected"]["model_sha256"],
            "model_size_bytes": contract["selected"]["model_size_bytes"],
            "baseline_runtime": baseline_runtime,
            "candidate_runtime": candidate_runtime,
            "selected_runtime": selected_runtime,
            "selected_commit": contract["runtimes"][selected_runtime]["commit"],
        },
        "validation": {
            "all_input_hashes_match": True,
            "exact_model_verified": True,
            "source_commits_and_tags_verified": True,
            "exact_patch_series_verified": True,
            "matched_native_kleidiai_builds": True,
            "runtime_buffer_proofs_observed": True,
            "fresh_server_per_cell": True,
            "server_pid_bound_in_every_probe": True,
            "measured_window_process_cpu_validated": True,
            "cached_prefix_observed_in_every_measured_request": True,
            "historical_baseline_reproduced": True,
            "quality_drift_treated_as_upgrade_rejection": True,
            "upgrade_candidate_claim_allowed": upgrade["passed"],
            "automatic_product_promotion_allowed": False,
            "energy_claim_allowed": False,
            "weighted_score_used": False,
            "claim_scope": contract["claim_boundary"],
        },
        "maximum_observed_prompt_tokens": maximum_prompt_tokens,
        "performance": performance,
        "hypothesis": upgrade,
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
