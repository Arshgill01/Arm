#!/usr/bin/env python3
"""Validate E9c native Arm prompt-cache generalization evidence."""

from __future__ import annotations

import argparse
import hashlib
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
    )
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e9a_ingest import expected_server_argv
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
    )
    from e7a_ingest import validate_runtime_closure
    from e9a_ingest import expected_server_argv


ARTIFACT_INPUTS = {
    "selected_manifest": "selected-manifest.json",
    "models": "models-manifest.json",
    "tasks": "tasks-manifest.json",
    "e9a_contract": "e9a-contract.json",
    "e9b_blocker": "e9b-blocker.json",
}


def validate_source_and_build(
    evidence_dir: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    service = contract["service"]
    source = load_object(evidence_dir / "source.json")
    if (
        source.get("commit") != service["source_commit"]
        or source.get("tag") != service["source_tag"]
        or source.get("patches_applied")
        != [patch.name for patch in sorted((evidence_dir / "patches").iterdir())]
        or sha256_file(evidence_dir / "source-diff.patch")
        != service["source_diff_sha256"]
    ):
        raise ValueError("E9c source proof differs from the frozen service")
    expected_changed = load_object(evidence_dir / "e9a-contract.json")["profiles"][
        "e7c_final"
    ]["source"]["changed_files"]
    if (
        evidence_dir / "patched-files.txt"
    ).read_text().splitlines() != expected_changed:
        raise ValueError("E9c changed-file proof differs from E7c")

    build_dir = evidence_dir / "build"
    e9a_profile = load_object(evidence_dir / "e9a-contract.json")["profiles"][
        "e7c_final"
    ]
    command = load_object(build_dir / "configure-command.json")
    if command.get("cmake_arguments") != e9a_profile["build"]["cmake_arguments"]:
        raise ValueError("E9c build arguments differ from E7c")
    cache_lines = (
        (build_dir / "CMakeCache.txt").read_text(errors="replace").splitlines()
    )
    for argument in e9a_profile["build"]["cmake_arguments"]:
        if not argument.startswith("-D") or "=" not in argument:
            continue
        name, value = argument[2:].split("=", 1)
        if value in {"ON", "OFF"} and not any(
            line.startswith(f"{name}:") and line.endswith(f"={value}")
            for line in cache_lines
        ):
            raise ValueError(f"E9c CMake cache differs for {name}")
    version = (build_dir / "server-version.txt").read_text(errors="replace").strip()
    if service["source_commit"][:9] not in version:
        raise ValueError("E9c server version differs from E7c")
    closure = validate_runtime_closure(build_dir / "runtime-closure.json")
    dependencies = sorted(
        {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
    )
    if {"libcrypto.so.3", "libssl.so.3"}.intersection(dependencies):
        raise ValueError("E9c runtime closure unexpectedly contains OpenSSL")
    build_process = parse_time_output((build_dir / "build-time.log").read_text())
    if build_process["maximum_rss_kib"] is None:
        raise ValueError("E9c build process evidence is incomplete")
    return {
        "configure_command": command,
        "cmake_cache_sha256": sha256_file(build_dir / "CMakeCache.txt"),
        "server_version": version,
        "build_process": build_process,
        "runtime_closure": closure,
        "dynamic_dependency_basenames": dependencies,
    }


def validate_recipe(
    recipe: dict[str, Any],
    contract: dict[str, Any],
) -> None:
    model = recipe.get("model", {})
    server = recipe.get("server_path")
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E9c"
        or recipe.get("profile_name") != "e7c_final"
        or recipe.get("source") != contract["service"]
        or recipe.get("service") != contract["service"]
        or model.get("sha256") != contract["selected"]["model_sha256"]
        or model.get("size_bytes") != contract["selected"]["model_size_bytes"]
        or not isinstance(server, str)
        or not server.endswith("/bin/llama-server")
        or not isinstance(model_path, str)
        or not model_path.endswith(".gguf")
        or contract["service"]["source_commit"][:9]
        not in recipe.get("server_version", "")
    ):
        raise ValueError("E9c recipe differs from the frozen E7c service")
    expected = expected_server_argv(
        server,
        model_path,
        candidate=contract["selected"]["candidate"],
        profile_name="e7c_final",
    )
    if recipe.get("argv") != expected:
        raise ValueError("E9c server argv differs from E7c")


def validate_process_cpu(
    value: Any,
    *,
    server_pid: int,
    requests: int,
    elapsed_seconds: float,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("E9c probe lacks process CPU evidence")
    integer_fields = (
        "pid",
        "clock_ticks_per_second",
        "user_ticks",
        "system_ticks",
        "total_ticks",
    )
    if any(type(value.get(name)) is not int for name in integer_fields):
        raise ValueError("E9c process CPU counters are not integers")
    if (
        value["pid"] != server_pid
        or value["clock_ticks_per_second"] <= 0
        or value["user_ticks"] < 0
        or value["system_ticks"] < 0
        or value["total_ticks"] <= 0
        or value["total_ticks"] != value["user_ticks"] + value["system_ticks"]
    ):
        raise ValueError("E9c process CPU counters are invalid")
    total = value["total_ticks"] / value["clock_ticks_per_second"]
    expected = {
        "user_seconds": value["user_ticks"] / value["clock_ticks_per_second"],
        "system_seconds": value["system_ticks"] / value["clock_ticks_per_second"],
        "total_seconds": total,
        "seconds_per_request": total / requests,
        "average_cores_used": total / elapsed_seconds,
    }
    for name, expected_value in expected.items():
        observed = value.get(name)
        if (
            not isinstance(observed, (int, float))
            or not math.isfinite(observed)
            or not math.isclose(float(observed), expected_value, rel_tol=1e-12)
        ):
            raise ValueError(f"E9c process CPU {name} differs")
    return {**value, **expected}


def validate_case(
    case: dict[str, Any],
    *,
    index: int,
    task_id: str,
    marker: str,
    marker_index: int,
    reference: str,
    maximum_prompt_tokens: int,
) -> None:
    if (
        case.get("index") != index
        or case.get("task_id") != task_id
        or case.get("prefix_marker") != marker
        or case.get("prefix_marker_index") != marker_index
        or case.get("reference_prediction") != reference
        or type(case.get("prompt_tokens")) is not int
        or not 0 < case["prompt_tokens"] <= maximum_prompt_tokens
        or not isinstance(case.get("prompt_sha256"), str)
        or len(case["prompt_sha256"]) != 64
    ):
        raise ValueError("E9c case identity differs from the contract")
    for name in (
        "http_ms",
        "encode_ms",
        "decode_ms",
        "cached_tokens",
        "evaluated_prompt_tokens",
        "response_tokens_cached",
        "response_tokens_evaluated",
    ):
        value = case.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"E9c case has invalid {name}")


def validate_cell(
    cell_dir: Path,
    *,
    contract: dict[str, Any],
    point_index: int,
    cell_index: int,
    cardinality: int,
    shared_tokens: int,
    cache_prompt: bool,
    repetition: int,
    references: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    recipe = load_object(cell_dir / "recipe.json")
    validate_recipe(recipe, contract)
    timed = (cell_dir / "server-time.log").read_text(errors="replace")
    commands = [line for line in timed.splitlines() if "Command being timed:" in line]
    if len(commands) != 1 or not all(
        argument in commands[0] for argument in recipe["argv"]
    ):
        raise ValueError(f"{cell_dir.name} timed command differs from its recipe")
    readiness = load_object(cell_dir / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not math.isfinite(ready_ms)
        or not 0 <= ready_ms <= contract["validity"]["maximum_ready_ms"]
    ):
        raise ValueError(f"{cell_dir.name} readiness evidence is invalid")

    probe = load_object(cell_dir / "probe.json")
    parameters = probe.get("parameters", {})
    workload = contract["workload"]
    expected_parameters = {
        "prefix_cardinality": cardinality,
        "shared_prefix_tokens": shared_tokens,
        "cache_prompt": cache_prompt,
        "repetition": repetition,
        "measured_requests": len(workload["measured_task_ids"]),
        "client_concurrency": workload["client_concurrency"],
        "seed": workload["seed"],
        "maximum_output_tokens": workload["maximum_output_tokens"],
    }
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E9c"
        or any(
            parameters.get(name) != value for name, value in expected_parameters.items()
        )
        or type(parameters.get("server_pid")) is not int
        or parameters["server_pid"] <= 0
    ):
        raise ValueError(f"{cell_dir.name} probe parameters differ")
    pid = int((cell_dir / "server-pid.txt").read_text().strip())
    if parameters["server_pid"] != pid:
        raise ValueError(f"{cell_dir.name} server PID binding differs")

    construction = contract["prompt_construction"]
    expected_repetitions = construction["tokenizer_preflight"][
        "native_endpoint_common_filler_repetitions_by_target"
    ][str(shared_tokens)]
    prefix = probe.get("prefix_recipe", {})
    prefix_ids = prefix.get("common_prefix_token_ids")
    if (
        prefix.get("target_shared_prefix_tokens") != shared_tokens
        or not isinstance(prefix.get("common_filler_repetitions"), int)
        or prefix["common_filler_repetitions"] != expected_repetitions
        or not isinstance(prefix_ids, list)
        or len(prefix_ids) != shared_tokens
        or any(type(token) is not int for token in prefix_ids)
        or prefix.get("variant_marker_token_ids")
        != construction["variant_marker_token_ids"]
        or prefix.get("common_prefix_sha256")
        != hashlib.sha256(
            json.dumps(prefix_ids, separators=(",", ":")).encode()
        ).hexdigest()
    ):
        raise ValueError(f"{cell_dir.name} prefix construction differs")

    active_markers = construction["variant_markers"][:cardinality]
    warmups = probe.get("warmups")
    if not isinstance(warmups, list) or len(warmups) != cardinality:
        raise ValueError(f"{cell_dir.name} warmup count differs")
    for index, warmup in enumerate(warmups):
        validate_case(
            warmup,
            index=index,
            task_id=workload["warmup_task_id"],
            marker=active_markers[index],
            marker_index=index,
            reference=references[workload["warmup_task_id"]],
            maximum_prompt_tokens=construction["maximum_prompt_tokens"],
        )

    cases = probe.get("cases")
    if not isinstance(cases, list) or len(cases) != len(workload["measured_task_ids"]):
        raise ValueError(f"{cell_dir.name} measured case count differs")
    for index, (case, task_id) in enumerate(zip(cases, workload["measured_task_ids"])):
        marker_index = index % cardinality
        validate_case(
            case,
            index=index,
            task_id=task_id,
            marker=active_markers[marker_index],
            marker_index=marker_index,
            reference=references[task_id],
            maximum_prompt_tokens=construction["maximum_prompt_tokens"],
        )

    result = probe.get("result", {})
    elapsed = result.get("elapsed_seconds")
    requests_per_second = result.get("requests_per_second")
    if (
        not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed <= 0
        or not isinstance(requests_per_second, (int, float))
        or not math.isclose(
            requests_per_second,
            len(cases) / elapsed,
            rel_tol=1e-12,
        )
    ):
        raise ValueError(f"{cell_dir.name} throughput evidence differs")
    process_cpu = validate_process_cpu(
        probe.get("process_cpu"),
        server_pid=pid,
        requests=len(cases),
        elapsed_seconds=elapsed,
    )
    process = parse_time_output(timed)
    shell_exit = int((cell_dir / "server-shell-exit.txt").read_text().strip())
    slots = json.loads((cell_dir / "slots.json").read_text())
    if (
        shell_exit not in contract["validity"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"] > contract["validity"]["maximum_process_rss_kib"]
        or not isinstance(slots, list)
        or len(slots) != contract["service"]["server_parallel_slots"]
        or "llamacpp:" not in (cell_dir / "metrics.txt").read_text()
    ):
        raise ValueError(f"{cell_dir.name} process evidence differs")

    failures = sum(
        case.get("http_status") != 200 or case.get("error") is not None
        for case in cases
    )
    invalid_predictions = sum(
        case.get("prediction") not in {"A", "B", "C", "D"} for case in cases
    )
    mismatches = sum(
        case.get("prediction") != case["reference_prediction"] for case in cases
    )
    if (
        result.get("failures") != failures
        or result.get("invalid_prediction_responses") != invalid_predictions
        or result.get("reference_prediction_mismatches") != mismatches
    ):
        raise ValueError(f"{cell_dir.name} result counts differ from raw cases")
    return (
        {
            "point_index": point_index,
            "cell_index": cell_index,
            "prefix_cardinality": cardinality,
            "shared_prefix_tokens": shared_tokens,
            "cache_prompt": cache_prompt,
            "repetition": repetition,
            "ready_ms": float(ready_ms),
            "requests_per_second": float(requests_per_second),
            "server_process_cpu": process_cpu,
            "process": process,
            "server_shell_exit_status": shell_exit,
            "failures": failures,
            "invalid_prediction_responses": invalid_predictions,
            "reference_prediction_mismatches": mismatches,
        },
        cases,
    )


def build_policy(
    eligible_lengths: list[int], tested_lengths: list[int]
) -> dict[str, Any]:
    eligible = sorted(set(eligible_lengths))
    tested = sorted(set(tested_lengths))
    if not eligible:
        return {"mode": "disabled", "eligible_shared_prefix_tokens": []}
    threshold = min(eligible)
    if eligible == [value for value in tested if value >= threshold]:
        return {
            "mode": "minimum_shared_prefix_tokens",
            "minimum_shared_prefix_tokens": threshold,
            "eligible_shared_prefix_tokens": eligible,
        }
    return {
        "mode": "tested_lengths_only",
        "eligible_shared_prefix_tokens": eligible,
    }


def summarize_point(
    *,
    cardinality: int,
    shared_tokens: int,
    cells: list[dict[str, Any]],
    samples: dict[tuple[bool, int], list[dict[str, Any]]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    performance: dict[str, Any] = {}
    for cache_prompt, name in ((False, "cache_off"), (True, "cache_on")):
        state_cells = [cell for cell in cells if cell["cache_prompt"] is cache_prompt]
        raw = [
            case
            for repetition in (1, 2)
            for case in samples[(cache_prompt, repetition)]
        ]
        performance[name] = {
            "cache_prompt": cache_prompt,
            "repetitions": state_cells,
            "requests_per_second": summarize(
                [cell["requests_per_second"] for cell in state_cells]
            ),
            "repetition_encode_median_ms": summarize(
                [
                    summarize(
                        [
                            float(case["encode_ms"])
                            for case in samples[(cache_prompt, repetition)]
                        ]
                    )["median"]
                    for repetition in (1, 2)
                ]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in raw]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in raw]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in raw]),
            "cached_tokens": summarize([float(case["cached_tokens"]) for case in raw]),
            "evaluated_prompt_tokens": summarize(
                [float(case["evaluated_prompt_tokens"]) for case in raw]
            ),
            "prompt_tokens": summarize([float(case["prompt_tokens"]) for case in raw]),
            "server_cpu_seconds_per_request": summarize(
                [
                    cell["server_process_cpu"]["seconds_per_request"]
                    for cell in state_cells
                ]
            ),
            "ready_ms": summarize([cell["ready_ms"] for cell in state_cells]),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in state_cells]
            ),
            "failures": sum(cell["failures"] for cell in state_cells),
            "reference_prediction_mismatches": sum(
                cell["reference_prediction_mismatches"] for cell in state_cells
            ),
            "invalid_prediction_responses": sum(
                cell["invalid_prediction_responses"] for cell in state_cells
            ),
        }

    paired_mismatches = 0
    for repetition in (1, 2):
        off = samples[(False, repetition)]
        on = samples[(True, repetition)]
        paired_mismatches += sum(
            left.get("prediction") != right.get("prediction")
            for left, right in zip(off, on)
        )
    off = performance["cache_off"]
    on = performance["cache_on"]
    ratios = {
        "throughput": on["requests_per_second"]["median"]
        / off["requests_per_second"]["median"],
        "prompt_encode_speedup": off["repetition_encode_median_ms"]["median"]
        / on["repetition_encode_median_ms"]["median"],
        "p95_http_latency": on["http_ms"]["p95"] / off["http_ms"]["p95"],
        "cpu_seconds_per_request": on["server_cpu_seconds_per_request"]["median"]
        / off["server_cpu_seconds_per_request"]["median"],
    }
    validity = contract["validity"]
    break_even = contract["break_even"]
    gates = {
        "zero_request_failures": off["failures"] == on["failures"] == 0,
        "exact_reference_outputs": off["reference_prediction_mismatches"]
        == on["reference_prediction_mismatches"]
        == 0,
        "paired_cache_outputs_equal": paired_mismatches == 0,
        "cache_mechanism_observed": off["cached_tokens"]["max"]
        == validity["required_cache_off_tokens_per_request"]
        and on["cached_tokens"]["min"] >= shared_tokens,
        "scheduler_dispersion_passed": max(
            off["requests_per_second"]["coefficient_of_variation"],
            on["requests_per_second"]["coefficient_of_variation"],
        )
        <= validity["maximum_throughput_coefficient_of_variation"],
        "throughput_gate_passed": ratios["throughput"]
        >= break_even["minimum_throughput_ratio"],
        "prompt_encode_gate_passed": ratios["prompt_encode_speedup"]
        >= break_even["minimum_prompt_encode_speedup_ratio"],
        "p95_latency_gate_passed": ratios["p95_http_latency"]
        <= break_even["maximum_p95_http_latency_ratio"],
        "cpu_time_gate_passed": ratios["cpu_seconds_per_request"]
        <= break_even["maximum_cpu_seconds_per_request_ratio"],
    }
    return {
        "prefix_cardinality": cardinality,
        "shared_prefix_tokens": shared_tokens,
        "eligible": all(gates.values()),
        "paired_cache_output_mismatches": paired_mismatches,
        "gates": gates,
        "ratios": ratios,
        "performance": performance,
        "samples": {
            f"cache_{'on' if cache else 'off'}_r{repetition}": samples[
                (cache, repetition)
            ]
            for cache in (False, True)
            for repetition in (1, 2)
        },
    }


def build_manifest(
    evidence_dir: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E9c":
        raise ValueError("unsupported E9c contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E9c contract")
    for name, artifact_name in ARTIFACT_INPUTS.items():
        source = root / contract["inputs"][f"{name}_path"]
        expected = contract["inputs"][f"{name}_sha256"]
        if (
            sha256_file(source) != expected
            or sha256_file(evidence_dir / artifact_name) != expected
        ):
            raise ValueError(f"E9c {name} input differs")
    for patch in load_object(evidence_dir / "e9a-contract.json")["profiles"][
        "e7c_final"
    ]["source"]["patches"]:
        if sha256_file(root / patch["path"]) != patch["sha256"]:
            raise ValueError(f"E9c patch differs: {patch['path']}")

    build = validate_source_and_build(evidence_dir, contract)
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["selected_manifest_path"]),
        contract["selected"]["candidate"],
    )
    task_ids = {task["id"] for task in tasks}
    workload = contract["workload"]
    if not set(workload["measured_task_ids"] + [workload["warmup_task_id"]]).issubset(
        task_ids
    ):
        raise ValueError("E9c workload contains an unknown task")

    order = contract["execution"]["point_order"]
    cell_order = contract["execution"]["within_point_order"]
    if (
        len(order) * len(cell_order)
        != contract["execution"]["total_fresh_process_cells"]
    ):
        raise ValueError("E9c cell count differs from its execution contract")
    points = []
    all_cells = []
    for point_index, point in enumerate(order, 1):
        cardinality = point["prefix_cardinality"]
        shared_tokens = point["shared_prefix_tokens"]
        cells = []
        samples: dict[tuple[bool, int], list[dict[str, Any]]] = {}
        for within_index, spec in enumerate(cell_order, 1):
            cache = spec["cache_prompt"]
            repetition = spec["repetition"]
            global_index = (point_index - 1) * len(cell_order) + within_index
            name = (
                f"{global_index:02d}-p{cardinality}-l{shared_tokens}-"
                f"cache_{'on' if cache else 'off'}-r{repetition}"
            )
            cell, raw = validate_cell(
                evidence_dir / "cells" / name,
                contract=contract,
                point_index=point_index,
                cell_index=global_index,
                cardinality=cardinality,
                shared_tokens=shared_tokens,
                cache_prompt=cache,
                repetition=repetition,
                references=references,
            )
            cells.append(cell)
            all_cells.append(cell)
            samples[(cache, repetition)] = raw
        points.append(
            summarize_point(
                cardinality=cardinality,
                shared_tokens=shared_tokens,
                cells=cells,
                samples=samples,
                contract=contract,
            )
        )

    policies = {}
    tested_lengths = contract["workload"]["shared_prefix_tokens"]
    for cardinality in contract["workload"]["prefix_cardinalities"]:
        eligible = [
            point["shared_prefix_tokens"]
            for point in points
            if point["prefix_cardinality"] == cardinality and point["eligible"]
        ]
        policies[str(cardinality)] = build_policy(eligible, tested_lengths)
    total_failures = sum(cell["failures"] for cell in all_cells)
    total_reference_mismatches = sum(
        cell["reference_prediction_mismatches"] for cell in all_cells
    )
    total_invalid_predictions = sum(
        cell["invalid_prediction_responses"] for cell in all_cells
    )
    total_paired_mismatches = sum(
        point["paired_cache_output_mismatches"] for point in points
    )
    exact_outputs = (
        total_failures == total_reference_mismatches == total_paired_mismatches == 0
    )
    any_eligible = any(point["eligible"] for point in points)
    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E9c":
        raise ValueError("E9c provenance differs")
    platform = {
        **parse_lscpu((evidence_dir / "lscpu.txt").read_text()),
        "uname": (evidence_dir / "uname.txt").read_text().strip(),
        "python": (evidence_dir / "python-version.txt").read_text().strip(),
        "compiler": (evidence_dir / "compiler.txt").read_text().strip(),
        "environment": load_object(evidence_dir / "environment.json"),
    }
    if platform["architecture"] != contract["validity"]["required_architecture"]:
        raise ValueError("E9c did not run on native Arm64")
    run_id = str(provenance["github_run_id"])
    status = (
        "valid_cache_generalization_policy"
        if exact_outputs and any_eligible
        else "valid_cache_generalization_no_break_even"
        if exact_outputs
        else "valid_cache_generalization_output_regression"
    )
    return {
        "schema_version": 1,
        "experiment_id": "E9c",
        "status": status,
        "scope": contract["scope"],
        "source": {
            "artifact_name": (
                f"e9c-prompt-cache-{run_id}-{provenance['github_run_attempt']}"
            ),
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "artifact_retention_days": 90,
        },
        "contract": contract,
        "provenance": provenance,
        "platform": platform,
        "selection": {
            "candidate": contract["selected"]["candidate"],
            "model_sha256": contract["selected"]["model_sha256"],
            "model_size_bytes": contract["selected"]["model_size_bytes"],
        },
        "build": build,
        "validation": {
            "all_input_hashes_match": True,
            "native_arm64_same_job": True,
            "exact_e7c_service": True,
            "fresh_server_per_cell": True,
            "bounded_predeclared_matrix": True,
            "raw_answers_retained_in_manifest": True,
            "total_request_failures": total_failures,
            "total_invalid_prediction_responses": total_invalid_predictions,
            "total_reference_prediction_mismatches": total_reference_mismatches,
            "total_paired_cache_output_mismatches": total_paired_mismatches,
            "exact_outputs": exact_outputs,
            "energy_claim_allowed": False,
            "weighted_score_used": False,
            "claim_scope": contract["claim_boundary"],
        },
        "points": points,
        "cache_enablement_policy_by_prefix_cardinality": policies,
        "any_cache_eligible_point": any_eligible,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
