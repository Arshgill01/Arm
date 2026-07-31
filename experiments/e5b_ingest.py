#!/usr/bin/env python3
"""Validate native E5b selected-model inference-serving evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize


LETTERS = {"A", "B", "C", "D"}
ARTIFACT_INPUTS = {
    "manifest": "selected-manifest.json",
    "policy": "deployment-policy.json",
    "models": "models-manifest.json",
    "runtime_contract": "runtime-contract.json",
    "tasks": "tasks-manifest.json",
}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reference_predictions(manifest: dict[str, Any], candidate: str) -> dict[str, str]:
    application = manifest.get("application", {}).get(candidate, {})
    repetitions = application.get("quality_repetitions")
    if not isinstance(repetitions, list) or len(repetitions) != 2:
        raise ValueError("selected manifest lacks two quality repetitions")
    predictions = [item.get("predictions") for item in repetitions]
    if (
        not all(isinstance(item, dict) for item in predictions)
        or predictions[0] != predictions[1]
        or any(value not in LETTERS for value in predictions[0].values())
    ):
        raise ValueError("selected manifest predictions are not stable answer letters")
    return dict(predictions[0])


def load_tasks(tasks_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = tasks_manifest.get("tasks")
    if tasks_manifest.get("schema_version") != 1 or not isinstance(tasks, list):
        raise ValueError("invalid task manifest")
    ids = [task.get("id") for task in tasks if isinstance(task, dict)]
    if len(ids) != len(tasks) or len(set(ids)) != len(ids):
        raise ValueError("task manifest has invalid or duplicate IDs")
    return tasks


def validate_case(
    case: dict[str, Any],
    *,
    index: int,
    task: dict[str, Any],
    reference: str,
    acceptance: dict[str, Any],
    max_output_tokens: int,
) -> None:
    predicted = case.get("predicted")
    if (
        case.get("index") != index
        or case.get("id") != task["id"]
        or case.get("category") != task["category"]
        or case.get("expected") != task["answer"]
        or case.get("reference_prediction") != reference
        or case.get("status") != acceptance["http_status"]
        or case.get("response") not in LETTERS
        or predicted != case.get("response")
        or case.get("correct") is not (predicted == task["answer"])
        or case.get("reference_match") is not (predicted == reference)
        or case.get("termination_reason") != acceptance["termination_reason"]
        or case.get("error") is not None
    ):
        raise ValueError(f"invalid inference response for {task['id']}")
    generated_tokens = case.get("generated_tokens")
    if (
        not isinstance(generated_tokens, int)
        or generated_tokens <= 0
        or generated_tokens > max_output_tokens
    ):
        raise ValueError(f"invalid generated-token count for {task['id']}")
    for name in ("encode_ms", "decode_ms", "http_ms"):
        value = case.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"invalid {name} for {task['id']}")


def validate_probe(
    probe: dict[str, Any],
    *,
    configuration: str,
    repetition: int,
    config: dict[str, Any],
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
    require_selected_quality: bool = True,
) -> dict[str, Any]:
    request_contract = contract["request"]
    parameters = probe.get("parameters")
    cases = probe.get("cases")
    warmups = probe.get("warmups")
    result = probe.get("result")
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != contract["experiment_id"]
        or not isinstance(parameters, dict)
        or not isinstance(cases, list)
        or not isinstance(warmups, list)
        or not isinstance(result, dict)
    ):
        raise ValueError("invalid E5b probe structure")
    expected_parameters = {
        "candidate": contract["selected"]["candidate"],
        "configuration": configuration,
        "repetition": repetition,
        "warmup_task_ids": request_contract["warmup_task_ids"],
        "measured_tasks": request_contract["measured_tasks"],
        "client_concurrency": config["client_concurrency"],
        "max_output_tokens": request_contract["max_output_tokens"],
        "instruction_role": request_contract["instruction_role"],
        "chat_template_mode": request_contract["chat_template_mode"],
        "temperature": request_contract["temperature"],
        "seed": request_contract["seed"],
        "timeout_seconds": request_contract["timeout_seconds"],
    }
    for key, expected in expected_parameters.items():
        if parameters.get(key) != expected:
            raise ValueError(f"probe parameter {key} differs from the contract")
    if (
        "warmup_slot_ids" in config
        and parameters.get("warmup_slot_ids") != config["warmup_slot_ids"]
    ):
        raise ValueError("probe warmup slot IDs differ from the contract")
    if (
        "prompt_cache" in config
        and parameters.get("prompt_cache") is not config["prompt_cache"]
    ):
        raise ValueError("probe prompt cache setting differs from the contract")
    task_by_id = {task["id"]: task for task in tasks}
    if len(warmups) != len(request_contract["warmup_task_ids"]):
        raise ValueError("warmup count differs from the contract")
    for index, task_id in enumerate(request_contract["warmup_task_ids"]):
        validate_case(
            warmups[index],
            index=index,
            task=task_by_id[task_id],
            reference=references[task_id],
            acceptance=contract["acceptance"],
            max_output_tokens=request_contract["max_output_tokens"],
        )
    if len(cases) != len(tasks) or len(cases) != request_contract["measured_tasks"]:
        raise ValueError("measured task count differs from the contract")
    for index, (case, task) in enumerate(zip(cases, tasks)):
        if not isinstance(case, dict):
            raise ValueError("inference case must be an object")
        validate_case(
            case,
            index=index,
            task=task,
            reference=references[task["id"]],
            acceptance=contract["acceptance"],
            max_output_tokens=request_contract["max_output_tokens"],
        )

    correct = sum(case["correct"] for case in cases)
    mismatches = sum(not case["reference_match"] for case in cases)
    failures = sum(
        case["status"] != contract["acceptance"]["http_status"]
        or case["error"] is not None
        or case["predicted"] is None
        for case in cases
    )
    elapsed = result.get("elapsed_seconds")
    if (
        not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed <= 0
    ):
        raise ValueError("probe has invalid elapsed time")
    observed_summaries = {
        "http_ms": summarize([float(case["http_ms"]) for case in cases]),
        "encode_ms": summarize([float(case["encode_ms"]) for case in cases]),
        "decode_ms": summarize([float(case["decode_ms"]) for case in cases]),
    }
    if "prompt_cache" in config:
        cached_tokens = [case.get("cached_tokens") for case in cases]
        evaluated_tokens = [case.get("evaluated_prompt_tokens") for case in cases]
        if any(type(value) is not int or value < 0 for value in cached_tokens):
            raise ValueError("probe has invalid cached-token evidence")
        if any(type(value) is not int or value <= 0 for value in evaluated_tokens):
            raise ValueError("probe has invalid evaluated-prompt-token evidence")
        minimum_cached = contract["acceptance"].get(
            "minimum_candidate_cached_tokens_per_request", 1
        )
        if config["prompt_cache"]:
            if any(value < minimum_cached for value in cached_tokens):
                raise ValueError("prompt-cache cell did not reuse the frozen prefix")
        elif any(value != 0 for value in cached_tokens):
            raise ValueError("no-cache cell unexpectedly reused prompt tokens")
        observed_summaries.update(
            {
                "cached_tokens": summarize([float(value) for value in cached_tokens]),
                "evaluated_prompt_tokens": summarize(
                    [float(value) for value in evaluated_tokens]
                ),
            }
        )
    for key, value in observed_summaries.items():
        if result.get(key) != value:
            raise ValueError(f"probe {key} summary differs from raw cases")
    expected_status_counts = {str(contract["acceptance"]["http_status"]): len(cases)}
    if (
        result.get("correct") != correct
        or result.get("total") != len(cases)
        or result.get("accuracy") != correct / len(cases)
        or result.get("failures") != failures
        or result.get("reference_prediction_mismatches") != mismatches
        or result.get("status_counts") != expected_status_counts
        or not math.isclose(
            float(result.get("requests_per_second", 0)),
            len(cases) / float(elapsed),
            rel_tol=1e-12,
        )
    ):
        raise ValueError("probe result differs from raw cases")
    selected = contract["selected"]
    acceptance = contract["acceptance"]
    if (
        len(cases) != selected["reference_total"]
        or failures != acceptance["request_failures"]
    ):
        raise ValueError("probe does not reproduce selected E3f quality")
    if require_selected_quality and (
        correct != selected["reference_correct"]
        or correct / len(cases) != selected["reference_accuracy"]
        or mismatches != acceptance["reference_prediction_mismatches"]
    ):
        raise ValueError("probe does not reproduce selected E3f quality")
    return {
        "correct": correct,
        "total": len(cases),
        "accuracy": correct / len(cases),
        "failures": failures,
        "reference_prediction_mismatches": mismatches,
        "elapsed_seconds": float(elapsed),
        "requests_per_second": float(result["requests_per_second"]),
        **observed_summaries,
    }


def validate_recipe(
    recipe: dict[str, Any],
    *,
    config: dict[str, Any],
    contract: dict[str, Any],
) -> None:
    selected = contract["selected"]
    inputs = contract["inputs"]
    recipe_inputs = recipe.get("inputs", {})
    model = recipe.get("model", {})
    runtime = recipe.get("runtime", {})
    files = model.get("files")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("service") != "Pareto64"
        or recipe.get("status") != "ready_to_launch"
        or recipe.get("selected_candidate") != selected["candidate"]
        or recipe.get("selection", {}).get("plan_status") != "selected"
        or recipe.get("weighted_score_used") is not False
    ):
        raise ValueError("launch recipe does not preserve the selected plan")
    recipe_input_names = {
        "manifest": "manifest",
        "policy": "constraints",
        "models": "models",
        "runtime_contract": "contract",
    }
    for name, recipe_name in recipe_input_names.items():
        if recipe_inputs.get(f"{recipe_name}_sha256") != inputs[f"{name}_sha256"]:
            raise ValueError(f"launch recipe {name} hash differs from the contract")
    if (
        not isinstance(files, list)
        or len(files) != 1
        or files[0].get("sha256") != selected["model_sha256"]
        or files[0].get("size_bytes") != selected["model_size_bytes"]
    ):
        raise ValueError("launch recipe model package differs from selected evidence")
    slots = config["server_parallel_slots"]
    context_per_slot = config.get("context_per_slot", 2048)
    if (
        runtime.get("llama_cpp_commit") != selected["llama_cpp_commit"]
        or selected["llama_cpp_commit"][:9] not in runtime.get("server_version", "")
        or runtime.get("threads") != 4
        or runtime.get("parallel_slots") != slots
        or runtime.get("context_per_slot") != context_per_slot
        or runtime.get("context_total") != context_per_slot * slots
    ):
        raise ValueError("launch recipe runtime differs from the frozen configuration")
    argv = runtime.get("argv")
    prompt_cache = config.get("prompt_cache", False)
    prompt_cache_argument = "--cache-prompt" if prompt_cache else "--no-cache-prompt"
    forbidden_cache_argument = "--no-cache-prompt" if prompt_cache else "--cache-prompt"
    required_arguments = {
        "--cont-batching",
        prompt_cache_argument,
        "--metrics",
        "--slots",
        "--jinja",
    }
    if (
        not isinstance(argv, list)
        or not required_arguments.issubset(argv)
        or forbidden_cache_argument in argv
        or (
            "prompt_cache" in config and runtime.get("prompt_cache") is not prompt_cache
        )
    ):
        raise ValueError("launch recipe lacks required serving arguments")
    if "context_per_slot" in config and (
        argv.count("--ctx-size") != 1
        or argv.index("--ctx-size") == len(argv) - 1
        or argv[argv.index("--ctx-size") + 1] != str(context_per_slot * slots)
    ):
        raise ValueError("launch recipe context argument differs from the contract")
    for field, argument in (
        ("kv_cache_type_k", "--cache-type-k"),
        ("kv_cache_type_v", "--cache-type-v"),
        ("flash_attention", "--flash-attn"),
    ):
        if field not in config:
            continue
        expected = config[field]
        if (
            runtime.get(field) != expected
            or argv.count(argument) != 1
            or argv.index(argument) == len(argv) - 1
            or argv[argv.index(argument) + 1] != expected
        ):
            raise ValueError("launch recipe KV cache type differs from the contract")
    if "batch_size" in config:
        batch_size = config["batch_size"]
        micro_batch_size = config["micro_batch_size"]
        explicit = config["explicit_batch_arguments"]
        if (
            runtime.get("batch_size") != batch_size
            or runtime.get("micro_batch_size") != micro_batch_size
            or runtime.get("batch_size_requested") != (batch_size if explicit else None)
            or runtime.get("micro_batch_size_requested")
            != (micro_batch_size if explicit else None)
        ):
            raise ValueError("launch recipe batch sizes differ from the contract")
        for argument, expected in (
            ("--batch-size", batch_size),
            ("--ubatch-size", micro_batch_size),
        ):
            if explicit and (
                argv.count(argument) != 1
                or argv.index(argument) == len(argv) - 1
                or argv[argv.index(argument) + 1] != str(expected)
            ):
                raise ValueError("launch recipe lacks explicit batch arguments")
            if not explicit and argument in argv:
                raise ValueError("baseline recipe unexpectedly pins batch arguments")
    if "weight_repack" in config:
        weight_repack = config["weight_repack"]
        if (
            not isinstance(weight_repack, bool)
            or runtime.get("weight_repack") is not weight_repack
            or (weight_repack and "--no-repack" in argv)
            or (not weight_repack and argv.count("--no-repack") != 1)
        ):
            raise ValueError("launch recipe weight repack differs from the contract")


def validate_cell(
    cell_dir: Path,
    *,
    configuration: str,
    repetition: int,
    config: dict[str, Any],
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
    require_selected_quality: bool = True,
) -> dict[str, Any]:
    validate_recipe(
        load_object(cell_dir / "recipe.json"), config=config, contract=contract
    )
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
    probe = validate_probe(
        load_object(cell_dir / "probe.json"),
        configuration=configuration,
        repetition=repetition,
        config=config,
        contract=contract,
        tasks=tasks,
        references=references,
        require_selected_quality=require_selected_quality,
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
    if not isinstance(slots, list) or len(slots) != config["server_parallel_slots"]:
        raise ValueError(f"{cell_dir.name} slot count differs from the contract")
    metrics = (cell_dir / "metrics.txt").read_text(encoding="utf-8")
    if "llamacpp:" not in metrics:
        raise ValueError(f"{cell_dir.name} lacks server metrics")
    return {
        "configuration": configuration,
        "repetition": repetition,
        "ready_ms": float(ready_ms),
        "probe": probe,
        "process": process,
        "server_shell_exit_status": shell_exit,
        "slots_observed": len(slots),
    }


def evaluate_hypothesis(
    performance: dict[str, Any], acceptance: dict[str, Any]
) -> dict[str, Any]:
    throughput_ratio = (
        performance["concurrent_2"]["requests_per_second"]["median"]
        / performance["baseline"]["requests_per_second"]["median"]
    )
    concurrent_http = performance["concurrent_2"]["http_ms"]
    throughput_passed = (
        throughput_ratio >= acceptance["minimum_throughput_improvement_ratio"]
    )
    latency_passed = (
        concurrent_http["median"]
        <= acceptance["maximum_concurrent_median_http_latency_ms"]
        and concurrent_http["p95"]
        <= acceptance["maximum_concurrent_p95_http_latency_ms"]
    )
    return {
        "passed": throughput_passed and latency_passed,
        "throughput_improvement_passed": throughput_passed,
        "latency_ceilings_passed": latency_passed,
        "throughput_improvement_ratio": throughput_ratio,
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
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E5b":
        raise ValueError("unsupported E5b contract")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E5b contract")
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
        raise ValueError("contract selected quality differs from the retained manifest")

    configurations = contract["execution"]["configurations"]
    order = contract["execution"]["order"]
    expected_pairs = {
        (name, repetition)
        for name in configurations
        for repetition in range(
            1, contract["execution"]["repetitions_per_configuration"] + 1
        )
    }
    observed_pairs = {
        (item.get("configuration"), item.get("repetition")) for item in order
    }
    if len(order) != len(expected_pairs) or observed_pairs != expected_pairs:
        raise ValueError("execution order does not cover each frozen cell once")
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
            )
        )

    performance: dict[str, Any] = {}
    for name in configurations:
        config_cells = [cell for cell in cells if cell["configuration"] == name]
        all_http = [
            float(case["http_ms"])
            for cell in config_cells
            for case in load_object(
                cell_paths[(name, cell["repetition"])] / "probe.json"
            )["cases"]
        ]
        performance[name] = {
            "server_parallel_slots": configurations[name]["server_parallel_slots"],
            "client_concurrency": configurations[name]["client_concurrency"],
            "repetitions": config_cells,
            "requests_per_second": summarize(
                [cell["probe"]["requests_per_second"] for cell in config_cells]
            ),
            "http_ms": summarize(all_http),
            "ready_ms": summarize([cell["ready_ms"] for cell in config_cells]),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in config_cells]
            ),
        }
    acceptance = contract["acceptance"]
    hypothesis = evaluate_hypothesis(performance, acceptance)

    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E5b":
        raise ValueError("provenance does not identify E5b")
    run_id = str(provenance["github_run_id"])
    artifact_name = (
        f"{contract['artifact_name_prefix']}-{run_id}-"
        f"{provenance['github_run_attempt']}"
    )
    return {
        "schema_version": 1,
        "experiment_id": "E5b",
        "status": (
            "valid_selected_inference_concurrency"
            if hypothesis["passed"]
            else "valid_selected_inference_no_concurrency_win"
        ),
        "scope": contract["scope"],
        "source": {
            "artifact_name": artifact_name,
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
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
        },
        "validation": {
            "all_input_hashes_match": True,
            "launch_recomputed_selected_plan": True,
            "exact_model_and_runtime_verified": True,
            "all_responses_match_selected_e3f_predictions": True,
            "selected_quality_reproduced_in_every_cell": True,
            "zero_request_failures": True,
            "fresh_server_per_cell": True,
            "runtime_buffer_proof_observed": True,
            "throughput_improvement_passed": hypothesis[
                "throughput_improvement_passed"
            ],
            "latency_ceilings_passed": hypothesis["latency_ceilings_passed"],
            "readiness_ceiling_passed": True,
            "rss_ceiling_passed": True,
            "inference_server_claim_allowed": True,
            "two_slot_optimization_claim_allowed": hypothesis["passed"],
        },
        "performance": performance,
        "runtime_buffer_patterns_observed": required_patterns,
        "hypothesis": hypothesis,
        "throughput_improvement_ratio": hypothesis["throughput_improvement_ratio"],
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
