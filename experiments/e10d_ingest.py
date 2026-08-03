#!/usr/bin/env python3
"""Validate E10d native Arm external-holdout evidence."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e9a_ingest import expected_server_argv
    from experiments.e9c_ingest import validate_process_cpu
    from experiments.e10b_ingest import CHANGED_FILES
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure
    from e9a_ingest import expected_server_argv
    from e9c_ingest import validate_process_cpu
    from e10b_ingest import CHANGED_FILES


ARTIFACT_INPUTS = {
    "e9a_contract": "e9a-contract.json",
    "e9b_plan": "e9b-plan.json",
    "models": "models-manifest.json",
    "e10b_manifest": "e10b-manifest.json",
    "e10c_negative_manifest": "e10c-negative-manifest.json",
    "sample_map": "sample-map.json",
    "sample_generator": "e9b-samples.py",
    "task_arc_easy": "tasks/e9b_arc_easy.yaml",
    "task_hellaswag": "tasks/e9b_hellaswag.yaml",
    "task_winogrande": "tasks/e9b_winogrande.yaml",
    "task_utils": "tasks/e9b_utils.py",
    "requirements": "requirements.txt",
    "primitive_patch": "patches/0004-server-select-exact-token-probabilities.patch",
}


def finite(value: Any, *, nonnegative: bool = False) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected a finite number")
    result = float(value)
    if nonnegative and result < 0:
        raise ValueError("expected a nonnegative number")
    return result


def object_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
    ).hexdigest()


def tokens_sha256(tokens: list[int]) -> str:
    return hashlib.sha256(
        json.dumps(tokens, separators=(",", ":")).encode()
    ).hexdigest()


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E10d":
        raise ValueError("contract does not identify E10d")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E10d contract")
    inputs = contract["inputs"]
    for key, artifact_path in ARTIFACT_INPUTS.items():
        source = root / inputs[f"{key}_path"]
        expected = inputs[f"{key}_sha256"]
        if (
            sha256_file(source) != expected
            or sha256_file(evidence / artifact_path) != expected
        ):
            raise ValueError(f"E10d input hash differs for {key}")
    for key in ("prepare", "preflight", "probe", "ingest", "test"):
        if sha256_file(root / inputs[f"{key}_path"]) != inputs[f"{key}_sha256"]:
            raise ValueError(f"E10d implementation hash differs for {key}")
    return contract


def validate_source_and_build(
    evidence: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    service = contract["service"]
    source = load_object(evidence / "source.json")
    patch_names = sorted(path.name for path in (evidence / "patches").iterdir())
    if (
        source.get("commit") != service["source_commit"]
        or source.get("tag") != service["source_tag"]
        or source.get("patches_applied") != patch_names
        or len(patch_names) != 4
        or sha256_file(evidence / "source-diff.patch") != service["source_diff_sha256"]
        or (evidence / "patched-files.txt").read_text().splitlines() != CHANGED_FILES
    ):
        raise ValueError("E10d source proof differs from E7c plus E10b")

    build = evidence / "build"
    e9a = load_object(evidence / "e9a-contract.json")
    cmake_arguments = e9a["profiles"]["e7c_final"]["build"]["cmake_arguments"]
    configure = load_object(build / "configure-command.json")
    if configure.get("cmake_arguments") != cmake_arguments:
        raise ValueError("E10d CMake arguments differ from E7c")
    cache = (build / "CMakeCache.txt").read_text(errors="replace").splitlines()
    for argument in cmake_arguments:
        if argument.startswith("-D") and "=" in argument:
            name, value = argument[2:].split("=", 1)
            if value in {"ON", "OFF"} and not any(
                line.startswith(f"{name}:") and line.endswith(f"={value}")
                for line in cache
            ):
                raise ValueError(f"E10d CMake cache differs for {name}")
    version = (build / "server-version.txt").read_text(errors="replace").strip()
    if service["source_commit"][:9] not in version:
        raise ValueError("E10d server version differs from b10216")
    closure = validate_runtime_closure(build / "runtime-closure.json")
    dependencies = sorted(
        {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
    )
    if {"libcrypto.so.3", "libssl.so.3"}.intersection(dependencies):
        raise ValueError("E10d runtime closure unexpectedly contains OpenSSL")
    build_process = parse_time_output((build / "build-time.log").read_text())
    if build_process["maximum_rss_kib"] is None:
        raise ValueError("E10d build process evidence is incomplete")
    return {
        "configure_command": configure,
        "cmake_cache_sha256": sha256_file(build / "CMakeCache.txt"),
        "server_version": version,
        "build_process": build_process,
        "runtime_closure": closure,
        "dynamic_dependency_basenames": dependencies,
    }


def validate_recipe(
    recipe: dict[str, Any], contract: dict[str, Any], model: dict[str, Any]
) -> None:
    server = recipe.get("server_path")
    model_value = recipe.get("model", {})
    model_path = model_value.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E10d"
        or recipe.get("profile_name") != "e7c_final_plus_probability_ids"
        or recipe.get("service") != contract["service"]
        or model_value.get("candidate") != model["candidate"]
        or model_value.get("sha256") != model["sha256"]
        or model_value.get("size_bytes") != model["size_bytes"]
        or not isinstance(server, str)
        or not isinstance(model_path, str)
    ):
        raise ValueError("E10d recipe differs from the frozen service")
    expected = expected_server_argv(
        server,
        model_path,
        candidate=model["candidate"],
        profile_name="e7c_final",
    )
    if recipe.get("argv") != expected:
        raise ValueError("E10d server argv differs from exact E7c")


def validate_raw_response(raw_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    path = raw_dir / str(record.get("path", ""))
    compressed = path.read_bytes()
    raw = gzip.decompress(compressed)
    if (
        len(raw) != record.get("bytes")
        or hashlib.sha256(raw).hexdigest() != record.get("sha256")
        or len(compressed) != record.get("gzip_bytes")
        or hashlib.sha256(compressed).hexdigest() != record.get("gzip_sha256")
    ):
        raise ValueError(f"raw response integrity differs for {path}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError(f"raw response is not an object for {path}")
    return value


def validate_prepared(
    prepared: dict[str, Any], contract: dict[str, Any], selected: dict[str, Any]
) -> dict[str, Any]:
    workload = contract["workload"]
    plan = contract["external_holdout"]
    if (
        prepared.get("schema_version") != 1
        or prepared.get("experiment_id") != "E10d"
        or prepared.get("harness") != plan["harness"]
        or prepared.get("tokenizer") != plan["tokenizer"]
        or prepared.get("max_length") != workload["max_length"]
        or prepared.get("fewshot") != workload["fewshot"]
        or prepared.get("apply_chat_template") is not True
        or prepared.get("fewshot_as_multiturn") is not False
        or prepared.get("seed") != workload["seed"]
        or prepared.get("tokenizer_parity_checked") is not True
        or prepared.get("task_order") != list(workload["tasks"])
        or prepared.get("summary") != workload["expected_summary"]
    ):
        raise ValueError("prepared workload differs from frozen E10d")

    tasks = prepared.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != len(workload["tasks"]):
        raise ValueError("prepared task list differs")
    expected_indices = selected
    for task, task_name in zip(tasks, workload["tasks"], strict=True):
        shape = workload["task_shapes"][task_name]
        samples = task.get("samples")
        if (
            task.get("task") != task_name
            or task.get("metrics") != shape["metrics"]
            or task.get("sample_count") != shape["samples"]
            or task.get("choice_count") != shape["choices"]
            or task.get("serial_candidate_requests") != shape["choices"]
            or task.get("token_score_requests") != shape["token_score_requests"]
            or not isinstance(samples, list)
            or len(samples) != shape["samples"]
            or [sample.get("source_index") for sample in samples]
            != expected_indices[task_name]
        ):
            raise ValueError(f"prepared {task_name} shape differs")
        choices = 0
        token_requests = 0
        for ordinal, sample in enumerate(samples):
            requests = sample.get("requests")
            if (
                sample.get("sample_ordinal") != ordinal
                or not isinstance(sample.get("source_document_sha256"), str)
                or len(sample["source_document_sha256"]) != 64
                or type(sample.get("gold_index")) is not int
                or not isinstance(requests, list)
                or not 2 <= len(requests) <= 4
                or sample.get("choice_text_lengths") is None
                or len(sample["choice_text_lengths"]) != len(requests)
                or len(sample.get("choice_text_bytes", [])) != len(requests)
                or not 0 <= sample["gold_index"] < len(requests)
            ):
                raise ValueError(f"prepared {task_name} sample differs")
            for choice_index, request in enumerate(requests):
                prompt = request.get("prompt_tokens")
                candidate = request.get("candidate_tokens")
                if (
                    request.get("choice_index") != choice_index
                    or not isinstance(prompt, list)
                    or not isinstance(candidate, list)
                    or not prompt
                    or not candidate
                    or any(type(token) is not int for token in prompt + candidate)
                    or request.get("prompt_sha256") != tokens_sha256(prompt)
                    or request.get("candidate_sha256") != tokens_sha256(candidate)
                    or request.get("input_tokens") != len(prompt) + len(candidate)
                    or request.get("input_tokens") != workload["max_length"]
                    or not shape["minimum_candidate_tokens"]
                    <= len(candidate)
                    <= shape["maximum_candidate_tokens"]
                    or request.get("left_truncated_tokens", 0) <= 0
                ):
                    raise ValueError(f"prepared {task_name} request differs")
                token_requests += len(candidate)
            choices += len(requests)
        if (
            choices != shape["choices"]
            or token_requests != shape["token_score_requests"]
        ):
            raise ValueError(f"prepared {task_name} totals differ")
    return prepared


def validate_choice(
    choice: dict[str, Any], request: dict[str, Any], raw_dir: Path
) -> None:
    candidate = request["candidate_tokens"]
    token_logprobs = choice.get("token_logprobs")
    sampled = choice.get("sampled_tokens")
    cached = choice.get("cached_tokens")
    raw = choice.get("raw_responses")
    if (
        choice.get("choice_index") != request["choice_index"]
        or choice.get("prompt_sha256") != request["prompt_sha256"]
        or choice.get("candidate_sha256") != request["candidate_sha256"]
        or not isinstance(token_logprobs, list)
        or len(token_logprobs) != len(candidate)
        or any(not math.isfinite(float(value)) for value in token_logprobs)
        or not math.isclose(
            sum(token_logprobs), choice.get("sum_logprob"), rel_tol=1e-12, abs_tol=1e-12
        )
        or not isinstance(sampled, list)
        or len(sampled) != len(candidate)
        or any(type(token) is not int for token in sampled)
        or choice.get("is_greedy") is not (sampled == candidate)
        or not isinstance(cached, list)
        or len(cached) != len(candidate)
        or cached[0] != 0
        or any(
            type(value) is not int
            or value <= 0
            or value > len(request["prompt_tokens"]) + index
            for index, value in enumerate(cached[1:], start=1)
        )
        or choice.get("token_score_requests") != len(candidate)
        or not isinstance(raw, list)
        or len(raw) != len(candidate)
    ):
        raise ValueError("E10d choice evidence differs")
    for name in ("http_ms", "prompt_ms", "predicted_ms", "response_bytes"):
        finite(choice.get(name), nonnegative=True)
    if choice["response_bytes"] != sum(record["bytes"] for record in raw):
        raise ValueError("E10d retained response byte total differs")
    for token, logprob, sampled_token, cache_n, record in zip(
        candidate, token_logprobs, sampled, cached, raw, strict=True
    ):
        response = validate_raw_response(raw_dir, record)
        probabilities = response.get("completion_probabilities")
        entry = (
            probabilities[0]
            if isinstance(probabilities, list) and len(probabilities) == 1
            else None
        )
        selected = entry.get("selected_logprobs") if isinstance(entry, dict) else None
        item = (
            selected[0] if isinstance(selected, list) and len(selected) == 1 else None
        )
        timings = response.get("timings")
        if (
            not isinstance(item, dict)
            or item.get("id") != token
            or item.get("logprob") != logprob
            or response.get("tokens") != [sampled_token]
            or not isinstance(timings, dict)
            or int(timings.get("cache_n", -1)) != cache_n
        ):
            raise ValueError("E10d raw response content differs from retained score")


def validate_preflight(evidence: Path, contract: dict[str, Any]) -> dict[str, Any]:
    preflight = load_object(evidence / "preflight.json")
    raw_dir = evidence / "preflight-raw"
    synthetic = preflight.get("synthetic_inputs")
    repetitions = preflight.get("repetitions")
    if (
        preflight.get("schema_version") != 1
        or preflight.get("experiment_id") != "E10d-preflight"
        or preflight.get("status") != "pass"
        or preflight.get("parameters") != contract["scoring"]["preflight_parameters"]
        or not all(preflight.get("validation", {}).values())
        or preflight.get("predictions", [None, None])[0]
        != preflight.get("predictions", [None, None])[1]
        or not isinstance(synthetic, dict)
        or synthetic.get("prompt_token_sha256")
        != tokens_sha256(synthetic.get("prompt_tokens", []))
        or synthetic.get("candidate_token_sha256")
        != [tokens_sha256(tokens) for tokens in synthetic.get("candidate_tokens", [])]
        or len(synthetic.get("candidate_tokens", [])) != 2
        or any(not 2 <= len(tokens) <= 16 for tokens in synthetic["candidate_tokens"])
        or not isinstance(repetitions, list)
        or len(repetitions) != 2
        or finite(preflight.get("maximum_repeat_sum_logprob_delta"), nonnegative=True)
        > contract["acceptance"]["maximum_preflight_repeat_delta"]
        or finite(preflight.get("maximum_repeat_token_logprob_delta"), nonnegative=True)
        > contract["acceptance"]["maximum_preflight_repeat_delta"]
    ):
        raise ValueError("E10d compatibility preflight failed")
    calculated_predictions = []
    for repetition_index, repetition in enumerate(repetitions, start=1):
        results = repetition.get("results")
        if (
            repetition.get("repetition") != repetition_index
            or not isinstance(results, list)
            or len(results) != 2
            or repetition.get("scores")
            != [result.get("sum_logprob") for result in results]
        ):
            raise ValueError("E10d preflight repetition differs")
        calculated_predictions.append(
            max(range(2), key=lambda index: (repetition["scores"][index], -index))
        )
        for result, candidate in zip(
            results, synthetic["candidate_tokens"], strict=True
        ):
            token_scores = result.get("token_logprobs")
            cached = result.get("cached_tokens")
            records = result.get("raw_responses")
            if (
                not isinstance(token_scores, list)
                or len(token_scores) != len(candidate)
                or any(not math.isfinite(float(value)) for value in token_scores)
                or not math.isclose(
                    sum(token_scores),
                    result.get("sum_logprob"),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                or not isinstance(cached, list)
                or len(cached) != len(candidate)
                or cached[0] != 0
                or any(value <= 0 for value in cached[1:])
                or not isinstance(records, list)
                or len(records) != len(candidate)
            ):
                raise ValueError("E10d preflight score evidence differs")
            for record in records:
                validate_raw_response(raw_dir, record)
    if calculated_predictions != preflight["predictions"]:
        raise ValueError("E10d preflight prediction differs")
    return preflight


def validate_probe(
    evidence: Path,
    probe: dict[str, Any],
    prepared: dict[str, Any],
    model: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    parameters = probe.get("parameters")
    result = probe.get("result")
    tasks = probe.get("tasks")
    expected_parameters = contract["scoring"]["probe_parameters"]
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E10d"
        or probe.get("model") != model["candidate"]
        or probe.get("model_sha256") != model["sha256"]
        or parameters != expected_parameters
        or not isinstance(result, dict)
        or result.get("failures") != 0
        or result.get("samples") != contract["workload"]["expected_summary"]["samples"]
        or result.get("candidate_requests")
        != contract["workload"]["expected_summary"]["choices"]
        or result.get("token_score_requests")
        != contract["workload"]["expected_summary"]["token_score_requests"]
        or not isinstance(tasks, list)
        or len(tasks) != len(prepared["tasks"])
    ):
        raise ValueError("E10d probe header or totals differ")
    elapsed = finite(result.get("elapsed_seconds"))
    if elapsed <= 0 or not math.isclose(
        result.get("samples_per_second"), 300 / elapsed, rel_tol=1e-12
    ):
        raise ValueError("E10d elapsed-time evidence differs")
    server_pid = probe.get("server_pid")
    if type(server_pid) is not int:
        raise ValueError("E10d probe PID is invalid")
    process_cpu = validate_process_cpu(
        probe.get("process_cpu"),
        server_pid=server_pid,
        requests=result["token_score_requests"],
        elapsed_seconds=elapsed,
    )

    raw_dir = evidence / "raw"
    metric_summary: dict[str, dict[str, float]] = {}
    retained_tasks: list[dict[str, Any]] = []
    for measured_task, source_task in zip(tasks, prepared["tasks"], strict=True):
        task_name = source_task["task"]
        samples = measured_task.get("samples")
        task_result = measured_task.get("result")
        if (
            measured_task.get("task") != task_name
            or measured_task.get("metrics") != source_task["metrics"]
            or not isinstance(samples, list)
            or len(samples) != len(source_task["samples"])
            or not isinstance(task_result, dict)
            or task_result.get("sample_count") != len(samples)
            or task_result.get("valid_samples") != len(samples)
            or task_result.get("failures") != 0
            or task_result.get("candidate_requests") != source_task["choice_count"]
            or task_result.get("token_score_requests")
            != source_task["token_score_requests"]
        ):
            raise ValueError(f"E10d {task_name} result differs")
        correct = {metric: 0 for metric in source_task["metrics"]}
        retained_samples = []
        for measured, source in zip(samples, source_task["samples"], strict=True):
            choices = measured.get("choices")
            if (
                measured.get("sample_ordinal") != source["sample_ordinal"]
                or measured.get("source_index") != source["source_index"]
                or measured.get("source_document_sha256")
                != source["source_document_sha256"]
                or measured.get("gold_index") != source["gold_index"]
                or measured.get("choice_text_lengths") != source["choice_text_lengths"]
                or measured.get("error") is not None
                or not isinstance(choices, list)
                or len(choices) != len(source["requests"])
            ):
                raise ValueError(f"E10d {task_name} sample identity differs")
            for choice, request in zip(choices, source["requests"], strict=True):
                validate_choice(choice, request, raw_dir)
            scores = [choice["sum_logprob"] for choice in choices]
            normalized = [
                score / length
                for score, length in zip(
                    scores, source["choice_text_lengths"], strict=True
                )
            ]
            prediction = max(
                range(len(scores)), key=lambda index: (scores[index], -index)
            )
            prediction_norm = max(
                range(len(normalized)), key=lambda index: (normalized[index], -index)
            )
            if (
                measured.get("choice_sum_logprobs") != scores
                or measured.get("choice_normalized_logprobs") != normalized
                or measured.get("prediction") != prediction
                or measured.get("prediction_norm") != prediction_norm
                or measured.get("acc") != int(prediction == source["gold_index"])
                or measured.get("acc_norm")
                != int(prediction_norm == source["gold_index"])
            ):
                raise ValueError(f"E10d {task_name} prediction differs")
            for metric in correct:
                correct[metric] += int(measured[metric])
            retained_samples.append(
                {
                    "source_index": source["source_index"],
                    "gold_index": source["gold_index"],
                    "prediction": prediction,
                    "prediction_norm": prediction_norm,
                }
            )
        metrics = {metric: correct[metric] / len(samples) for metric in correct}
        if task_result.get("metrics") != metrics:
            raise ValueError(f"E10d {task_name} metrics differ")
        metric_summary[task_name] = metrics
        retained_tasks.append({"task": task_name, "samples": retained_samples})
    return {
        "metrics": metric_summary,
        "tasks": retained_tasks,
        "process_cpu": process_cpu,
        "elapsed_seconds": elapsed,
        "samples_per_second": result["samples_per_second"],
        "candidate_requests": result["candidate_requests"],
        "token_score_requests": result["token_score_requests"],
        "request_failures": result["failures"],
    }


def compare_models(models: list[dict[str, Any]]) -> dict[str, Any]:
    if len(models) != 2:
        raise ValueError("E10d comparison requires exactly two models")
    primary, control = models
    if set(primary["metrics"]) != set(control["metrics"]):
        raise ValueError("E10d model task sets differ")
    deltas: dict[str, dict[str, float]] = {}
    for task in primary["metrics"]:
        if set(primary["metrics"][task]) != set(control["metrics"][task]):
            raise ValueError("E10d model metric sets differ")
        deltas[task] = {
            metric: primary["metrics"][task][metric] - control["metrics"][task][metric]
            for metric in primary["metrics"][task]
        }
    primary_samples = {
        (task["task"], sample["source_index"]): sample
        for task in primary["tasks"]
        for sample in task["samples"]
    }
    control_samples = {
        (task["task"], sample["source_index"]): sample
        for task in control["tasks"]
        for sample in task["samples"]
    }
    if set(primary_samples) != set(control_samples) or not primary_samples:
        raise ValueError("E10d paired sample identities differ")
    prediction_matches = sum(
        primary_samples[key]["prediction"] == control_samples[key]["prediction"]
        for key in primary_samples
    )
    normalized_matches = sum(
        primary_samples[key]["prediction_norm"]
        == control_samples[key]["prediction_norm"]
        for key in primary_samples
    )
    return {
        "primary_minus_control_metric_deltas": deltas,
        "paired_samples": len(primary_samples),
        "paired_prediction_agreement": prediction_matches / len(primary_samples),
        "paired_normalized_prediction_agreement": normalized_matches
        / len(primary_samples),
    }


def cell_summary(
    evidence: Path, contract_path: Path, root: Path, model_name: str
) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    models = {model["candidate"]: model for model in contract["models"]}
    if model_name not in models:
        raise ValueError("E10d model is not frozen")
    model = models[model_name]
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E10d evidence is not native Arm64")
    source_build = validate_source_and_build(evidence, contract)
    validate_recipe(load_object(evidence / "recipe.json"), contract, model)
    readiness = load_object(evidence / "readiness.json")
    ready_ms = finite(readiness.get("ready_ms"), nonnegative=True)
    if (
        readiness.get("status") != "ok"
        or ready_ms > contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError("E10d readiness differs")
    process = parse_time_output((evidence / "server-time.log").read_text())
    if (
        process["exit_status"]
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
    ):
        raise ValueError("E10d server process evidence differs")
    model_file = evidence / "model-sha256.txt"
    model_line = model_file.read_text().strip().split()
    if len(model_line) != 2 or model_line[0] != model["sha256"]:
        raise ValueError("E10d model file identity differs")
    prepared = validate_prepared(
        load_object(evidence / "prepared.json"),
        contract,
        load_object(evidence / "sample-map.json"),
    )
    preflight = validate_preflight(evidence, contract)
    probe = validate_probe(
        evidence,
        load_object(evidence / "probe.json"),
        prepared,
        model,
        contract,
    )
    return {
        "schema_version": 1,
        "experiment_id": "E10d",
        "status": "valid_external_holdout_cell",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": sha256_file(evidence / "prepared.json"),
        "model": model,
        "platform": platform,
        "runtime": source_build,
        "readiness_ms": ready_ms,
        "server_process": process,
        "preflight": {
            "status": preflight["status"],
            "maximum_repeat_sum_logprob_delta": preflight[
                "maximum_repeat_sum_logprob_delta"
            ],
            "maximum_repeat_token_logprob_delta": preflight[
                "maximum_repeat_token_logprob_delta"
            ],
        },
        **probe,
        "validation": {
            "native_arm64": True,
            "exact_e7c_service_plus_e10b_primitive": True,
            "tokenizer_parity": True,
            "synthetic_preflight": True,
            "all_raw_responses_retained": True,
            "zero_request_failures": True,
            "minimum_quality_gate_used": False,
        },
        "claim_boundary": contract["claim_boundary"],
    }


def aggregate_summary(
    contract_path: Path, primary_path: Path, control_path: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    primary = load_object(primary_path)
    control = load_object(control_path)
    expected = contract["models"]
    if (
        primary.get("status") != "valid_external_holdout_cell"
        or control.get("status") != "valid_external_holdout_cell"
        or primary.get("contract_sha256") != sha256_file(contract_path)
        or control.get("contract_sha256") != sha256_file(contract_path)
        or primary.get("prepared_sha256") != control.get("prepared_sha256")
        or primary.get("model") != expected[0]
        or control.get("model") != expected[1]
        or primary.get("request_failures") != 0
        or control.get("request_failures") != 0
    ):
        raise ValueError("E10d cell summaries differ from frozen aggregate")
    comparison = compare_models([primary, control])
    return {
        "schema_version": 1,
        "experiment_id": "E10d",
        "status": "valid_external_holdout",
        "contract_sha256": sha256_file(contract_path),
        "prepared_sha256": primary["prepared_sha256"],
        "models": [primary, control],
        "comparison": comparison,
        "validation": {
            "native_arm64": True,
            "same_frozen_workload": True,
            "both_models_complete": True,
            "zero_request_failures": True,
            "per_sample_logs_retained": True,
            "minimum_quality_gate_used": False,
            "original_admission_contract_rewritten": False,
        },
        "claim_boundary": contract["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    cell = subparsers.add_parser("cell")
    cell.add_argument("--evidence-dir", type=Path, required=True)
    cell.add_argument("--contract", type=Path, required=True)
    cell.add_argument("--root", type=Path, required=True)
    cell.add_argument("--model", required=True)
    cell.add_argument("--output", type=Path, required=True)
    aggregate = subparsers.add_parser("aggregate")
    aggregate.add_argument("--contract", type=Path, required=True)
    aggregate.add_argument("--primary", type=Path, required=True)
    aggregate.add_argument("--control", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "cell":
        output = cell_summary(args.evidence_dir, args.contract, args.root, args.model)
    else:
        output = aggregate_summary(args.contract, args.primary, args.control)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
