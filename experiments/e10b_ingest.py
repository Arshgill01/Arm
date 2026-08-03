#!/usr/bin/env python3
"""Validate E10b native Arm exact-token probability evidence."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e9a_ingest import expected_server_argv
    from experiments.e9c_ingest import validate_process_cpu
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure
    from e9a_ingest import expected_server_argv
    from e9c_ingest import validate_process_cpu


ARTIFACT_INPUTS = {
    "e9a_contract": "e9a-contract.json",
    "e10a_contract": "e10a-contract.json",
    "models": "models-manifest.json",
    "tasks": "tasks-manifest.json",
    "selected_manifest": "selected-manifest.json",
    "primitive_patch": "patches/0004-server-select-exact-token-probabilities.patch",
}
CHANGED_FILES = [
    "common/reasoning-budget.cpp",
    "ggml/src/ggml-cpu/CMakeLists.txt",
    "ggml/src/ggml-cpu/arch/arm/quants.c",
    "tests/test-reasoning-budget.cpp",
    "tools/server/README.md",
    "tools/server/server-context.cpp",
    "tools/server/server-schema.cpp",
    "tools/server/server-task.cpp",
    "tools/server/server-task.h",
    "tools/server/tests/unit/test_completion.py",
]


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E10b":
        raise ValueError("contract does not identify E10b")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E10b contract")
    inputs = contract["inputs"]
    for key, artifact_path in ARTIFACT_INPUTS.items():
        source_path = root / inputs[f"{key}_path"]
        expected = inputs[f"{key}_sha256"]
        if (
            sha256_file(source_path) != expected
            or sha256_file(evidence / artifact_path) != expected
        ):
            raise ValueError(f"E10b input hash differs for {key}")
    for key in ("probe", "ingest"):
        if sha256_file(root / inputs[f"{key}_path"]) != inputs[f"{key}_sha256"]:
            raise ValueError(f"E10b implementation hash differs for {key}")
    return contract


def validate_source_and_build(
    evidence: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    service = contract["service"]
    source = load_object(evidence / "source.json")
    patches = sorted(path.name for path in (evidence / "patches").iterdir())
    if (
        source.get("commit") != service["source_commit"]
        or source.get("tag") != service["source_tag"]
        or source.get("patches_applied") != patches
        or len(patches) != 4
        or sha256_file(evidence / "source-diff.patch") != service["source_diff_sha256"]
        or (evidence / "patched-files.txt").read_text().splitlines() != CHANGED_FILES
    ):
        raise ValueError("E10b source proof differs from the frozen patch set")
    build_dir = evidence / "build"
    e9a = load_object(evidence / "e9a-contract.json")
    cmake_arguments = e9a["profiles"]["e7c_final"]["build"]["cmake_arguments"]
    command = load_object(build_dir / "configure-command.json")
    if command.get("cmake_arguments") != cmake_arguments:
        raise ValueError("E10b CMake arguments differ from E7c")
    cache = (build_dir / "CMakeCache.txt").read_text(errors="replace")
    for argument in cmake_arguments:
        if argument.startswith("-D") and "=" in argument:
            name, value = argument[2:].split("=", 1)
            if value in {"ON", "OFF"} and not any(
                line.startswith(f"{name}:") and line.endswith(f"={value}")
                for line in cache.splitlines()
            ):
                raise ValueError(f"E10b CMake cache differs for {name}")
    version = (build_dir / "server-version.txt").read_text(errors="replace").strip()
    if service["source_commit"][:9] not in version:
        raise ValueError("E10b server version differs from b10216")
    closure = validate_runtime_closure(build_dir / "runtime-closure.json")
    dependencies = sorted(
        {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
    )
    if {"libcrypto.so.3", "libssl.so.3"}.intersection(dependencies):
        raise ValueError("E10b runtime closure unexpectedly contains OpenSSL")
    build_process = parse_time_output((build_dir / "build-time.log").read_text())
    if build_process["maximum_rss_kib"] is None:
        raise ValueError("E10b build process evidence is incomplete")
    return {
        "configure_command": command,
        "cmake_cache_sha256": sha256_file(build_dir / "CMakeCache.txt"),
        "server_version": version,
        "build_process": build_process,
        "runtime_closure": closure,
        "dynamic_dependency_basenames": dependencies,
    }


def validate_recipe(recipe: dict[str, Any], contract: dict[str, Any]) -> None:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E10b"
        or recipe.get("profile_name") != contract["service"]["profile"]
        or recipe.get("service") != contract["service"]
        or model.get("sha256") != contract["selected"]["model_sha256"]
        or model.get("size_bytes") != contract["selected"]["model_size_bytes"]
        or not isinstance(server, str)
        or not isinstance(model_path, str)
    ):
        raise ValueError("E10b recipe differs from the frozen service")
    expected = expected_server_argv(
        server,
        model_path,
        candidate=contract["selected"]["candidate"],
        profile_name="e7c_final",
    )
    if recipe.get("argv") != expected:
        raise ValueError("E10b server argv differs from E7c")


def validate_raw_response(cell_dir: Path, record: dict[str, Any]) -> None:
    raw_path = cell_dir / "raw" / record["path"]
    compressed = raw_path.read_bytes()
    raw = gzip.decompress(compressed)
    if (
        len(raw) != record["bytes"]
        or hashlib.sha256(raw).hexdigest() != record["sha256"]
        or len(compressed) != record["gzip_bytes"]
        or hashlib.sha256(compressed).hexdigest() != record["gzip_sha256"]
    ):
        raise ValueError(f"{raw_path} raw response integrity differs")


def validate_case(
    cell_dir: Path,
    case: dict[str, Any],
    *,
    mode: str,
    candidate_ids: list[int],
    n_vocab: int,
    prompt_sha256: str,
    acceptance: dict[str, Any],
) -> None:
    scores = case.get("candidate_logprobs")
    expected_count = n_vocab if mode == "full_vocab" else len(candidate_ids)
    if (
        case.get("http_status") != 200
        or case.get("error") is not None
        or case.get("mode") != mode
        or case.get("candidate_token_ids") != candidate_ids
        or case.get("prompt_sha256") != prompt_sha256
        or case.get("probability_entries") != expected_count
        or not isinstance(scores, dict)
        or set(scores) != {str(token_id) for token_id in candidate_ids}
        or any(
            not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in scores.values()
        )
        or not isinstance(case.get("response_bytes"), int)
        or case["response_bytes"] <= 0
        or case.get("cached_tokens") != 0
    ):
        raise ValueError(f"{cell_dir.name} case differs from E10b")
    if mode == "selected" and case.get("returned_selected_order") != candidate_ids:
        raise ValueError("selected probability order differs from request order")
    for name in ("http_ms", "encode_ms", "decode_ms", "evaluated_prompt_tokens"):
        value = case.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"{cell_dir.name} has invalid {name}")
    raw_record = case.get("raw_response")
    if not isinstance(raw_record, dict):
        raise TypeError(f"{cell_dir.name} lacks raw response record")
    validate_raw_response(cell_dir, raw_record)
    if (
        mode == "full_vocab"
        and case["probability_entries"] < acceptance["minimum_full_vocab_entries"]
    ):
        raise ValueError("full-vocabulary response is smaller than the frozen minimum")
    if (
        mode == "selected"
        and case["probability_entries"] > acceptance["maximum_selected_entries"]
    ):
        raise ValueError("selected response exceeds the frozen bound")


def validate_cell(
    cell_dir: Path,
    *,
    contract: dict[str, Any],
    mode: str,
    repetition: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    recipe = load_object(cell_dir / "recipe.json")
    validate_recipe(recipe, contract)
    timed = (cell_dir / "server-time.log").read_text(errors="replace")
    command_lines = [
        line for line in timed.splitlines() if "Command being timed:" in line
    ]
    if len(command_lines) != 1 or not all(
        argument in command_lines[0] for argument in recipe["argv"]
    ):
        raise ValueError(f"{cell_dir.name} timed command differs")
    readiness = load_object(cell_dir / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not 0 <= ready_ms <= contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError(f"{cell_dir.name} readiness is invalid")
    process = parse_time_output(timed)
    if (
        process["exit_status"]
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
    ):
        raise ValueError(f"{cell_dir.name} process evidence is invalid")
    probe = load_object(cell_dir / "probe.json")
    parameters = probe.get("parameters", {})
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E10b"
        or parameters.get("mode") != mode
        or parameters.get("repetition") != repetition
        or parameters.get("task_id") != contract["workload"]["task_id"]
        or parameters.get("cache_prompt") is not False
        or parameters.get("measured_requests")
        != contract["workload"]["measured_requests_per_cell"]
    ):
        raise ValueError(f"{cell_dir.name} probe parameters differ")
    pid = int((cell_dir / "server-pid.txt").read_text().strip())
    if parameters.get("server_pid") != pid:
        raise ValueError(f"{cell_dir.name} PID binding differs")
    candidate_ids = parameters.get("candidate_token_ids")
    n_vocab = parameters.get("n_vocab")
    if (
        not isinstance(candidate_ids, list)
        or len(candidate_ids) != 4
        or len(set(candidate_ids)) != 4
        or any(type(token_id) is not int for token_id in candidate_ids)
        or type(n_vocab) is not int
        or n_vocab < contract["acceptance"]["minimum_full_vocab_entries"]
    ):
        raise ValueError(f"{cell_dir.name} token identity differs")
    cases = probe.get("cases")
    if (
        not isinstance(cases, list)
        or len(cases) != contract["workload"]["measured_requests_per_cell"]
    ):
        raise ValueError(f"{cell_dir.name} case count differs")
    prompt_hashes = {case.get("prompt_sha256") for case in cases}
    if len(prompt_hashes) != 1 or None in prompt_hashes:
        raise ValueError(f"{cell_dir.name} prompt identity differs")
    prompt_sha256 = next(iter(prompt_hashes))
    for case in cases:
        validate_case(
            cell_dir,
            case,
            mode=mode,
            candidate_ids=candidate_ids,
            n_vocab=n_vocab,
            prompt_sha256=prompt_sha256,
            acceptance=contract["acceptance"],
        )
    result = probe.get("result", {})
    elapsed = result.get("elapsed_seconds")
    if (
        result.get("failures") != 0
        or not isinstance(elapsed, (int, float))
        or elapsed <= 0
        or not math.isclose(
            result.get("requests_per_second", -1), len(cases) / elapsed, rel_tol=1e-12
        )
    ):
        raise ValueError(f"{cell_dir.name} result summary differs")
    process_cpu = validate_process_cpu(
        probe.get("process_cpu"),
        server_pid=pid,
        requests=len(cases),
        elapsed_seconds=float(elapsed),
    )
    return {
        "mode": mode,
        "repetition": repetition,
        "ready_ms": ready_ms,
        "process": process,
        "process_cpu": process_cpu,
        "result": result,
        "candidate_token_ids": candidate_ids,
        "n_vocab": n_vocab,
        "prompt_sha256": prompt_sha256,
    }, cases


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    build = validate_source_and_build(evidence, contract)
    cells: list[dict[str, Any]] = []
    cases_by_key: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for index, spec in enumerate(contract["execution"]["cell_order"], start=1):
        mode = spec["mode"]
        repetition = spec["repetition"]
        cell_dir = evidence / "cells" / f"{index:02d}-{mode}-r{repetition}"
        cell, cases = validate_cell(
            cell_dir, contract=contract, mode=mode, repetition=repetition
        )
        cells.append(cell)
        cases_by_key[(mode, repetition)] = cases
    if len(cells) != contract["execution"]["total_fresh_process_cells"]:
        raise ValueError("E10b cell count differs")

    pairs: list[dict[str, Any]] = []
    for repetition in (1, 2):
        full_cases = cases_by_key[("full_vocab", repetition)]
        selected_cases = cases_by_key[("selected", repetition)]
        for index, (full, selected) in enumerate(zip(full_cases, selected_cases)):
            if (
                full["prompt_sha256"] != selected["prompt_sha256"]
                or full["candidate_token_ids"] != selected["candidate_token_ids"]
            ):
                raise ValueError("paired E10b request identities differ")
            deltas = {
                token_id: abs(
                    full["candidate_logprobs"][token_id]
                    - selected["candidate_logprobs"][token_id]
                )
                for token_id in full["candidate_logprobs"]
            }
            pairs.append(
                {
                    "repetition": repetition,
                    "index": index,
                    "prompt_sha256": full["prompt_sha256"],
                    "candidate_token_ids": full["candidate_token_ids"],
                    "full_vocab_candidate_logprobs": full["candidate_logprobs"],
                    "selected_candidate_logprobs": selected["candidate_logprobs"],
                    "absolute_logprob_deltas": deltas,
                    "maximum_absolute_logprob_delta": max(deltas.values()),
                    "full_vocab_ranking": full["candidate_ranking"],
                    "selected_ranking": selected["candidate_ranking"],
                    "prediction_equal": full["candidate_ranking"][0]
                    == selected["candidate_ranking"][0],
                    "sampled_content_equal": full["sampled_content"]
                    == selected["sampled_content"],
                    "sampled_tokens_equal": full["sampled_tokens"]
                    == selected["sampled_tokens"],
                    "full_vocab_response_bytes": full["response_bytes"],
                    "selected_response_bytes": selected["response_bytes"],
                }
            )
    full = [
        case
        for key, values in cases_by_key.items()
        if key[0] == "full_vocab"
        for case in values
    ]
    selected = [
        case
        for key, values in cases_by_key.items()
        if key[0] == "selected"
        for case in values
    ]
    full_http = summarize([case["http_ms"] for case in full])
    selected_http = summarize([case["http_ms"] for case in selected])
    full_bytes = summarize([float(case["response_bytes"]) for case in full])
    selected_bytes = summarize([float(case["response_bytes"]) for case in selected])
    maximum_delta = max(pair["maximum_absolute_logprob_delta"] for pair in pairs)
    parity = (
        maximum_delta
        <= contract["acceptance"]["maximum_absolute_log_probability_delta"]
    )
    predictions_equal = all(pair["prediction_equal"] for pair in pairs)
    samples_equal = all(
        pair["sampled_content_equal"] and pair["sampled_tokens_equal"] for pair in pairs
    )
    response_ratio = selected_bytes["median"] / full_bytes["median"]
    latency_ratio = selected_http["median"] / full_http["median"]
    payload_pass = (
        response_ratio
        <= contract["acceptance"]["maximum_selected_to_full_response_bytes_ratio"]
    )
    latency_pass = (
        latency_ratio
        <= contract["acceptance"]["maximum_selected_to_full_median_http_latency_ratio"]
    )
    promoted = (
        parity and predictions_equal and samples_equal and payload_pass and latency_pass
    )
    provenance = load_object(evidence / "provenance.json")
    if provenance.get("experiment_id") != "E10b":
        raise ValueError("E10b provenance differs")
    return {
        "schema_version": 1,
        "experiment_id": "E10b",
        "status": "valid_exact_token_primitive"
        if promoted
        else "valid_primitive_rejected",
        "promote_exact_token_primitive": promoted,
        "source": {
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{provenance['github_run_id']}",
            "artifact_name": f"e10b-exact-token-probabilities-{provenance['github_run_id']}-{provenance['github_run_attempt']}",
            "artifact_retention_days": 90,
        },
        "provenance": provenance,
        "platform": {
            "uname": (evidence / "uname.txt").read_text().strip(),
            "lscpu": parse_lscpu((evidence / "lscpu.txt").read_text()),
            "environment": load_object(evidence / "environment.json"),
        },
        "contract": contract,
        "build": build,
        "cells": cells,
        "pairs": pairs,
        "aggregate": {
            "paired_requests": len(pairs),
            "maximum_absolute_logprob_delta": maximum_delta,
            "all_candidate_predictions_equal": predictions_equal,
            "all_sampled_outputs_equal": samples_equal,
            "full_vocab_http_ms": full_http,
            "selected_http_ms": selected_http,
            "selected_to_full_median_http_latency_ratio": latency_ratio,
            "full_vocab_response_bytes": full_bytes,
            "selected_response_bytes": selected_bytes,
            "selected_to_full_median_response_bytes_ratio": response_ratio,
        },
        "validation": {
            "native_arm64_same_job": True,
            "exact_b10216_base_service": True,
            "primitive_patch_applied": True,
            "fresh_server_per_cell": True,
            "cache_disabled_per_request": True,
            "zero_request_failures": True,
            "full_vocab_mechanism_observed": True,
            "selected_id_order_exact": True,
            "logprob_parity_pass": parity,
            "candidate_prediction_parity_pass": predictions_equal,
            "sampled_output_parity_pass": samples_equal,
            "response_payload_gate_pass": payload_pass,
            "latency_non_regression_gate_pass": latency_pass,
            "external_holdout_observed": False,
            "complete_candidate_scorer_claim_allowed": False,
            "energy_claim_allowed": False,
            "claim_scope": contract["claim_boundary"],
        },
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
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
