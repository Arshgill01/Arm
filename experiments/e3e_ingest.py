#!/usr/bin/env python3
"""Validate E3e bounded-reasoning evidence and derive its quality frontier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e3_score import build_summary, load_object, sha256_file
    from experiments.e3b_ingest import (
        normalize_quality_sources,
        pareto_front,
        validate_execution_order,
    )
    from experiments.e3d_ingest import validate_runtime_proof
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e3_score import build_summary, load_object, sha256_file
    from e3b_ingest import normalize_quality_sources, pareto_front, validate_execution_order
    from e3d_ingest import validate_runtime_proof


def validate_inputs(
    evidence_dir: Path, contract_path: Path, models_path: Path, tasks_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_object(contract_path)
    models = load_object(models_path)
    provenance = load_object(evidence_dir / "provenance.json")
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E3e":
        raise ValueError("contract does not identify schema-1 E3e")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E3e contract")
    if load_object(evidence_dir / "models-manifest.json") != models:
        raise ValueError("artifact model manifest differs from frozen E3e models")
    source = models.get("source_model")
    repository = models.get("quantization_repository")
    model = models.get("shared_model")
    if (
        not isinstance(source, dict)
        or source.get("license") != "Apache-2.0"
        or not isinstance(repository, dict)
        or repository.get("license") != "Apache-2.0"
        or repository.get("base_model") != source.get("repository")
        or not isinstance(model, dict)
        or model.get("repository") != repository.get("repository")
        or model.get("revision") != repository.get("revision")
        or model.get("license") != "Apache-2.0"
        or model.get("quantization") != "Q4_0"
    ):
        raise ValueError("E3e model provenance is invalid")
    variants = models.get("variants")
    if not isinstance(variants, dict) or list(variants) != contract["variants"]:
        raise ValueError("E3e model variants differ from the contract")
    observed_budgets: list[int] = []
    for variant in variants.values():
        budget = variant.get("reasoning_budget_tokens")
        cap = variant.get("max_output_tokens")
        if (
            variant.get("framework") != "llama.cpp"
            or not isinstance(budget, int)
            or isinstance(budget, bool)
            or budget < 0
            or not isinstance(cap, int)
            or isinstance(cap, bool)
            or cap != budget + 8
        ):
            raise ValueError("E3e variant budget configuration is invalid")
        observed_budgets.append(budget)
    if observed_budgets != [0, 16, 32, 48]:
        raise ValueError("E3e reasoning budgets differ from the frozen frontier")
    if sha256_file(tasks_path) != contract["quality"]["tasks_sha256"]:
        raise ValueError("task manifest checksum differs from E3e contract")
    if sha256_file(evidence_dir / "tasks-manifest.json") != sha256_file(tasks_path):
        raise ValueError("artifact task manifest differs")
    policy = contract["deployment_policy"]
    policy_path = Path(policy["path"])
    if (
        sha256_file(policy_path) != policy["sha256"]
        or sha256_file(evidence_dir / policy["artifact_path"]) != policy["sha256"]
    ):
        raise ValueError("deployment policy differs from E3e frozen input")
    expected_provenance = {
        "experiment_id": "E3e",
        "llama_cpp_commit": contract["upstream"]["llama_cpp_commit"],
        "llama_cpp_tag": contract["upstream"]["llama_cpp_tag"],
        "kleidiai_release": contract["upstream"]["kleidiai_release"],
        "kleidiai_archive_md5": contract["upstream"]["kleidiai_archive_md5"],
        "execution_order": contract["execution_order"],
        "controlled_difference": contract["controlled_difference"],
        "calibration_evidence": contract["calibration_evidence"],
        "deployment_policy_sha256": policy["sha256"],
        "source_model_revision": source["revision"],
        "quantization_revision": repository["revision"],
    }
    for key, value in expected_provenance.items():
        if provenance.get(key) != value:
            raise ValueError(f"provenance {key} differs from E3e contract")
    if (evidence_dir / "build-exit.txt").read_text().strip() != "0":
        raise ValueError("E3e build failed")
    configure_log = (evidence_dir / "configure.log").read_text(encoding="utf-8")
    if "Using KleidiAI optimized kernels if applicable" not in configure_log:
        raise ValueError("E3e configure log does not prove KleidiAI enabled")
    cache = (evidence_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    for setting in (
        "GGML_CPU_KLEIDIAI:BOOL=ON",
        "GGML_NATIVE:BOOL=ON",
        "LLAMA_BUILD_SERVER:BOOL=ON",
    ):
        if setting not in cache:
            raise ValueError(f"E3e build cache lacks {setting}")
    if not re.search(r"^LLAMA_CURL:(?:BOOL|UNINITIALIZED)=OFF$", cache, re.MULTILINE):
        raise ValueError("E3e build cache lacks LLAMA_CURL=OFF")
    return contract, models, provenance


def validate_model_artifact(evidence_dir: Path, model: dict[str, Any]) -> int:
    files = model.get("files")
    if not isinstance(files, list) or len(files) != 1:
        raise ValueError("E3e requires one shared model file")
    item = files[0]
    expected_size = f"{item['path']} {item['size_bytes']} bytes"
    if (evidence_dir / "model-files.txt").read_text().splitlines() != [expected_size]:
        raise ValueError("E3e model size evidence differs")
    lines = (evidence_dir / "model-sha256.txt").read_text().splitlines()
    if len(lines) != 1:
        raise ValueError("E3e model checksum evidence differs")
    fields = lines[0].split(maxsplit=1)
    if (
        len(fields) != 2
        or fields[0] != item["sha256"]
        or not fields[1].endswith(f"/{item['path']}")
    ):
        raise ValueError("E3e model checksum differs")
    return int(item["size_bytes"])


def build_manifest(
    evidence_dir: Path, contract_path: Path, models_path: Path, tasks_path: Path
) -> dict[str, Any]:
    contract, models, provenance = validate_inputs(
        evidence_dir, contract_path, models_path, tasks_path
    )
    variants = contract["variants"]
    order = validate_execution_order(
        contract["execution_order"], variants, contract["quality"]["repetitions"]
    )
    model = models["shared_model"]
    package_size = validate_model_artifact(evidence_dir, model)
    quality = build_summary(models_path, tasks_path, evidence_dir)
    quality["experiment_id"] = "E3e"
    normalize_quality_sources(quality, variants)
    expected_quality = contract["quality"]
    if quality["acceptance_policy"] != {
        "repetitions": expected_quality["repetitions"],
        "prediction_parser": expected_quality["prediction_parser"],
        "predictions_must_be_stable": expected_quality["predictions_must_be_stable"],
        "absolute_accuracy_floor": expected_quality["absolute_accuracy_floor"],
        "maximum_task_deficit_from_best": expected_quality[
            "maximum_task_deficit_from_best"
        ],
    }:
        raise ValueError("E3e quality scorer policy differs from the contract")

    application: dict[str, Any] = {}
    build_commit = contract["upstream"]["llama_cpp_commit"][:9]
    for variant in variants:
        variant_config = models["variants"][variant]
        variant_dir = evidence_dir / "variants" / variant
        loads: list[float] = []
        rss_values: list[float] = []
        processes: list[dict[str, Any]] = []
        runtime_evidence: set[str] = set()
        for round_number, round_order in enumerate(order, start=1):
            position = round_order.index(variant) + 1
            round_dir = variant_dir / f"round-{round_number}-position-{position}"
            validate_runtime_proof(
                round_dir,
                f"/{model['entrypoint']}",
                build_commit,
                contract["configuration"]["threads"],
            )
            readiness = load_object(round_dir / "readiness.json")
            if readiness.get("status") != "ok" or float(readiness.get("ready_ms", -1)) < 0:
                raise ValueError(f"{variant} round {round_number} lacks readiness evidence")
            loads.append(float(readiness["ready_ms"]))
            runtime_log = "\n".join(
                (round_dir / name).read_text(encoding="utf-8")
                for name in (
                    "runtime-proof.stderr.log",
                    "server.core.log",
                    "server.stdout.log",
                    "server.stderr.log",
                )
            )
            matches = {
                pattern
                for pattern in model["runtime_buffer_patterns"]
                if pattern in runtime_log
            }
            if not matches:
                raise ValueError(f"{variant} round {round_number} lacks KleidiAI proof")
            runtime_evidence.update(matches)
            process = parse_time_output((round_dir / "server.time.log").read_text())
            if process["exit_status"] not in {0, 130, 143} or process["maximum_rss_kib"] is None:
                raise ValueError(f"{variant} round {round_number} process evidence is invalid")
            processes.append(process)
            rss_values.append(float(process["maximum_rss_kib"]))

        raw_runs = [
            load_object(variant_dir / f"quality-repeat-{repetition}.json")
            for repetition in range(1, expected_quality["repetitions"] + 1)
        ]
        reasoning_values: list[float] = []
        encode_ms: list[float] = []
        decode_ms: list[float] = []
        http_ms: list[float] = []
        generated_tokens: list[float] = []
        for repetition, run in enumerate(raw_runs, start=1):
            if (
                run.get("framework") != "llama.cpp"
                or run.get("transport") != "OpenAI-compatible HTTP"
                or run.get("threads") != contract["configuration"]["threads"]
                or run.get("context_size") != contract["configuration"]["context"]
                or run.get("reasoning_budget_tokens")
                != variant_config["reasoning_budget_tokens"]
                or run.get("max_output_tokens") != variant_config["max_output_tokens"]
                or run.get("chat_template_mode")
                != contract["configuration"]["chat_template_mode"]
                or run.get("reasoning_format")
                != contract["configuration"]["reasoning_format"]
                or run.get("temperature") != contract["configuration"]["temperature"]
                or run.get("seed") != contract["configuration"]["seed"]
                or float(run.get("model_load_ms", -1)) != loads[repetition - 1]
                or not str(run.get("model_path", "")).endswith(
                    f"/{model['entrypoint']}"
                )
            ):
                raise ValueError(f"quality runtime parameters differ for {variant}")
            for case in run.get("cases", []):
                reasoning = case.get("reasoning_content")
                characters = case.get("reasoning_characters")
                tokens = case.get("generated_tokens")
                if (
                    reasoning is not None
                    and not isinstance(reasoning, str)
                    or not isinstance(characters, int)
                    or characters != (len(reasoning) if reasoning is not None else 0)
                    or not isinstance(tokens, int)
                    or tokens < 0
                    or tokens > variant_config["max_output_tokens"]
                ):
                    raise ValueError(f"invalid reasoning evidence for {variant}")
                reasoning_values.append(float(characters))
                generated_tokens.append(float(tokens))
                encode_ms.append(float(case["encode_ms"]))
                decode_ms.append(float(case["decode_ms"]))
                http_ms.append(float(case["http_ms"]))
        budget = variant_config["reasoning_budget_tokens"]
        if budget == 0 and any(value != 0 for value in reasoning_values):
            raise ValueError("zero-budget candidate emitted reasoning content")
        if budget > 0 and not any(value > 0 for value in reasoning_values):
            raise ValueError(f"{variant} did not exercise bounded reasoning")
        scored = quality["variants"][variant]
        application[variant] = {
            "display_name": variant_config["display_name"],
            "minimum_accuracy": scored["minimum_accuracy"],
            "quality_eligible": scored["quality_eligible"],
            "reasoning_budget_tokens": budget,
            "max_output_tokens": variant_config["max_output_tokens"],
            "package_size_bytes": package_size,
            "model_load_ms": summarize(loads),
            "same_text_encode_ms": summarize(encode_ms),
            "same_text_decode_ms": summarize(decode_ms),
            "same_text_total_ms": summarize(
                [left + right for left, right in zip(encode_ms, decode_ms)]
            ),
            "http_round_trip_ms": summarize(http_ms),
            "reasoning_characters": summarize(reasoning_values),
            "generated_tokens": summarize(generated_tokens),
            "quality_process": {
                "maximum_rss_kib": summarize(rss_values),
                "repetitions": processes,
            },
            "quality_repetitions": scored["repetitions"],
            "runtime_buffer_evidence": sorted(runtime_evidence),
        }

    eligible = {
        name: {
            "minimum_accuracy": record["minimum_accuracy"],
            "same_text_total_ms_median": record["same_text_total_ms"]["median"],
            "maximum_quality_process_rss_kib": record["quality_process"][
                "maximum_rss_kib"
            ]["max"],
            "package_size_bytes": float(record["package_size_bytes"]),
        }
        for name, record in application.items()
        if record["quality_eligible"]
    }
    frontier = pareto_front(eligible, contract["pareto"]["directions"])
    return {
        "schema_version": 1,
        "experiment_id": "E3e",
        "status": "valid_frontier" if frontier else "valid_no_quality_eligible_variant",
        "source": {
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{provenance['github_run_id']}",
            "artifact_name": f"{contract['artifact_name_prefix']}-{provenance['github_run_id']}-{provenance['github_run_attempt']}",
            "artifact_retention_days": 90,
        },
        "platform": {
            "uname": (evidence_dir / "uname.txt").read_text().strip(),
            **parse_lscpu((evidence_dir / "lscpu.txt").read_text()),
        },
        "provenance": provenance,
        "quality": quality,
        "application": application,
        "pareto": {
            "directions": contract["pareto"]["directions"],
            "inputs": eligible,
            "frontier": frontier,
            "weighted_score_used": False,
        },
        "validation": {
            "quality_policy_predeclared": True,
            "deployment_policy_predeclared": True,
            "same_tasks_and_instruction_as_e3": True,
            "bounded_reasoning_outputs_observed_after_freeze": True,
            "current_llama_cpp_pinned": True,
            "kleidiai_build_enabled": True,
            "kleidiai_runtime_buffer_proven": all(
                application[name]["runtime_buffer_evidence"] for name in variants
            ),
            "performance_comparison_allowed": True,
            "quality_eligible_variants": sorted(
                name for name in variants if application[name]["quality_eligible"]
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    result = build_manifest(
        arguments.evidence_dir,
        arguments.contract,
        arguments.models,
        arguments.tasks,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
