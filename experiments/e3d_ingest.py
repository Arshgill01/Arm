#!/usr/bin/env python3
"""Validate E3d current-runtime evidence and derive its quality-gated frontier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e2_ingest import elapsed_seconds
    from experiments.e3_score import build_summary, load_object, sha256_file
    from experiments.e3b_ingest import (
        normalize_quality_sources,
        pareto_front,
        validate_execution_order,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e2_ingest import elapsed_seconds
    from e3_score import build_summary, load_object, sha256_file
    from e3b_ingest import normalize_quality_sources, pareto_front, validate_execution_order


def validate_inputs(
    evidence_dir: Path, contract_path: Path, models_path: Path, tasks_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_object(contract_path)
    models = load_object(models_path)
    provenance = load_object(evidence_dir / "provenance.json")
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E3d":
        raise ValueError("contract does not identify schema-1 E3d")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E3d contract")
    if load_object(evidence_dir / "models-manifest.json") != models:
        raise ValueError("artifact model manifest differs from frozen E3d models")
    source_model = models.get("source_model")
    quantization_repository = models.get("quantization_repository")
    if (
        not isinstance(source_model, dict)
        or source_model.get("license") != "Apache-2.0"
        or not isinstance(quantization_repository, dict)
        or quantization_repository.get("license") != "Apache-2.0"
        or quantization_repository.get("base_model") != source_model.get("repository")
    ):
        raise ValueError("E3d source or quantization provenance is invalid")
    quantizations: list[str] = []
    for model in models.get("variants", {}).values():
        if (
            model.get("repository") != quantization_repository.get("repository")
            or model.get("revision") != quantization_repository.get("revision")
            or model.get("parameter_scale") != source_model.get("parameter_scale")
            or not isinstance(model.get("quantization"), str)
        ):
            raise ValueError("E3d variants do not share frozen model provenance")
        quantizations.append(model["quantization"])
    if len(quantizations) != len(set(quantizations)):
        raise ValueError("E3d quantization labels must be unique")
    if sha256_file(tasks_path) != contract["quality"]["tasks_sha256"]:
        raise ValueError("task manifest checksum differs from E3d contract")
    if sha256_file(evidence_dir / "tasks-manifest.json") != sha256_file(tasks_path):
        raise ValueError("artifact task manifest differs")
    policy = contract["deployment_policy"]
    policy_path = Path(policy["path"])
    if (
        sha256_file(policy_path) != policy["sha256"]
        or sha256_file(evidence_dir / policy["artifact_path"]) != policy["sha256"]
    ):
        raise ValueError("deployment policy differs from E3d frozen input")
    expected_provenance = {
        "experiment_id": "E3d",
        "llama_cpp_commit": contract["upstream"]["llama_cpp_commit"],
        "llama_cpp_tag": contract["upstream"]["llama_cpp_tag"],
        "kleidiai_release": contract["upstream"]["kleidiai_release"],
        "kleidiai_archive_md5": contract["upstream"]["kleidiai_archive_md5"],
        "execution_order": contract["benchmark"]["execution_order"],
        "controlled_difference": contract["controlled_difference"],
        "deployment_policy_sha256": policy["sha256"],
        "source_model_revision": models["source_model"]["revision"],
        "model_revisions": {
            name: model["revision"] for name, model in models["variants"].items()
        },
    }
    for key, value in expected_provenance.items():
        if provenance.get(key) != value:
            raise ValueError(f"provenance {key} differs from E3d contract")
    if (evidence_dir / "build-exit.txt").read_text().strip() != "0":
        raise ValueError("E3d build failed")
    configure_log = (evidence_dir / "configure.log").read_text(encoding="utf-8")
    if "Using KleidiAI optimized kernels if applicable" not in configure_log:
        raise ValueError("E3d configure log does not prove KleidiAI enabled")
    cache = (evidence_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    for setting in (
        "GGML_CPU_KLEIDIAI:BOOL=ON",
        "GGML_NATIVE:BOOL=ON",
        "LLAMA_BUILD_SERVER:BOOL=ON",
    ):
        if setting not in cache:
            raise ValueError(f"E3d build cache lacks {setting}")
    if not re.search(r"^LLAMA_CURL:(?:BOOL|UNINITIALIZED)=OFF$", cache, re.MULTILINE):
        raise ValueError("E3d build cache lacks LLAMA_CURL=OFF")
    return contract, models, provenance


def validate_model_artifacts(
    evidence_dir: Path, variants: list[str], models: dict[str, Any]
) -> dict[str, int]:
    expected_sizes: list[str] = []
    expected_hashes: dict[str, str] = {}
    package_sizes: dict[str, int] = {}
    for variant in variants:
        model = models["variants"][variant]
        if model.get("license") != "Apache-2.0":
            raise ValueError(f"{variant} violates the E3d license policy")
        package_sizes[variant] = sum(item["size_bytes"] for item in model["files"])
        for item in model["files"]:
            relative = f"{variant}/{item['path']}"
            expected_sizes.append(f"{relative} {item['size_bytes']} bytes")
            expected_hashes[relative] = item["sha256"]
    if (evidence_dir / "model-files.txt").read_text().splitlines() != sorted(expected_sizes):
        raise ValueError("E3d model size evidence differs from frozen packages")
    observed: dict[str, str] = {}
    for line in (evidence_dir / "model-sha256.txt").read_text().splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise ValueError("malformed E3d model checksum evidence")
        digest, path = fields
        matches = [name for name in expected_hashes if path.endswith(f"/{name}")]
        if len(matches) != 1 or matches[0] in observed:
            raise ValueError("E3d model checksum path differs")
        observed[matches[0]] = digest
    if observed != expected_hashes:
        raise ValueError("E3d model checksums differ from frozen packages")
    return package_sizes


def benchmark_round(
    path: Path,
    model_suffix: str,
    input_tokens: int,
    output_tokens: int,
    threads: int,
    repetitions: int,
) -> dict[str, Any]:
    records = json.loads((path / "benchmark.json").read_text(encoding="utf-8"))
    if not isinstance(records, list) or len(records) != 2:
        raise ValueError(f"{path} must contain prompt and generation benchmark records")
    prompt = next(
        (item for item in records if item.get("n_prompt") == input_tokens and item.get("n_gen") == 0),
        None,
    )
    generation = next(
        (item for item in records if item.get("n_prompt") == 0 and item.get("n_gen") == output_tokens),
        None,
    )
    if prompt is None or generation is None:
        raise ValueError(f"{path} benchmark parameters differ from E3d")
    for record in records:
        if (
            record.get("n_threads") != threads
            or not str(record.get("model_filename", "")).endswith(model_suffix)
            or record.get("build_commit") != "9d9a6d29"
            or len(record.get("samples_ns", [])) != repetitions
            or len(record.get("samples_ts", [])) != repetitions
        ):
            raise ValueError(f"{path} benchmark identity or repetition count differs")
    timing = parse_time_output((path / "time.log").read_text(encoding="utf-8"))
    if timing["exit_status"] != 0 or timing["maximum_rss_kib"] is None:
        raise ValueError(f"{path} benchmark process failed")
    prompt_ms = [float(value) / 1_000_000 for value in prompt["samples_ns"]]
    generation_ms = [float(value) / 1_000_000 for value in generation["samples_ns"]]
    return {
        "prompt": prompt,
        "generation": generation,
        "prompt_ms": prompt_ms,
        "generation_ms": generation_ms,
        "total_ms": [left + right for left, right in zip(prompt_ms, generation_ms)],
        "process": timing,
    }


def build_manifest(
    evidence_dir: Path, contract_path: Path, models_path: Path, tasks_path: Path
) -> dict[str, Any]:
    contract, models, provenance = validate_inputs(
        evidence_dir, contract_path, models_path, tasks_path
    )
    variants = contract["variants"]
    if set(variants) != set(models.get("variants", {})):
        raise ValueError("E3d contract and model variants differ")
    order = validate_execution_order(
        contract["benchmark"]["execution_order"],
        variants,
        contract["benchmark"]["rounds_per_variant"],
    )
    package_sizes = validate_model_artifacts(evidence_dir, variants, models)

    quality = build_summary(models_path, tasks_path, evidence_dir)
    quality["experiment_id"] = "E3d"
    normalize_quality_sources(quality, variants)
    expected_quality = contract["quality"]
    if quality["acceptance_policy"] != {
        "repetitions": expected_quality["repetitions"],
        "prediction_parser": expected_quality["prediction_parser"],
        "predictions_must_be_stable": expected_quality["predictions_must_be_stable"],
        "absolute_accuracy_floor": expected_quality["absolute_accuracy_floor"],
        "maximum_task_deficit_from_best": expected_quality["maximum_task_deficit_from_best"],
    }:
        raise ValueError("E3d quality scorer policy differs from the contract")

    application: dict[str, Any] = {}
    benchmark_variants: dict[str, Any] = {}
    for variant in variants:
        model = models["variants"][variant]
        variant_dir = evidence_dir / "variants" / variant
        readiness = load_object(variant_dir / "readiness.json")
        if readiness.get("status") != "ok" or float(readiness.get("ready_ms", -1)) < 0:
            raise ValueError(f"{variant} lacks valid server readiness evidence")
        raw_runs = [
            load_object(variant_dir / f"quality-repeat-{repetition}.json")
            for repetition in range(1, expected_quality["repetitions"] + 1)
        ]
        expected_load_ms = float(readiness["ready_ms"])
        for run in raw_runs:
            if (
                run.get("framework") != "llama.cpp"
                or run.get("transport") != "OpenAI-compatible HTTP"
                or run.get("threads") != contract["configuration"]["threads"]
                or run.get("context_size") != contract["configuration"]["context"]
                or run.get("max_output_tokens") != expected_quality["max_output_tokens"]
                or run.get("chat_template_mode") != contract["configuration"]["chat_template_mode"]
                or run.get("temperature") != contract["configuration"]["temperature"]
                or run.get("seed") != contract["configuration"]["seed"]
                or float(run.get("model_load_ms", -1)) != expected_load_ms
                or not str(run.get("model_path", "")).endswith(
                    f"/{variant}/{model['entrypoint']}"
                )
            ):
                raise ValueError(f"quality runtime parameters differ for {variant}")
        runtime_log = (
            (variant_dir / "server.core.log").read_text(encoding="utf-8")
            + "\n"
            + (variant_dir / "server.stdout.log").read_text(encoding="utf-8")
            + "\n"
            + (variant_dir / "server.stderr.log").read_text(encoding="utf-8")
        )
        runtime_patterns = model["runtime_buffer_patterns"]
        matched_patterns = sorted(pattern for pattern in runtime_patterns if pattern in runtime_log)
        if not matched_patterns:
            raise ValueError(f"{variant} lacks KleidiAI runtime buffer proof")
        process = parse_time_output((variant_dir / "server.time.log").read_text())
        if process["exit_status"] not in {0, 130, 143} or process["maximum_rss_kib"] is None:
            raise ValueError(f"{variant} server process evidence is invalid")
        encode_ms = [float(case["encode_ms"]) for run in raw_runs for case in run["cases"]]
        decode_ms = [float(case["decode_ms"]) for run in raw_runs for case in run["cases"]]
        total_ms = [float(case["encode_ms"]) + float(case["decode_ms"]) for run in raw_runs for case in run["cases"]]
        http_ms = [float(case["http_ms"]) for run in raw_runs for case in run["cases"]]
        scored = quality["variants"][variant]
        application[variant] = {
            "display_name": model["display_name"],
            "minimum_accuracy": scored["minimum_accuracy"],
            "quality_eligible": scored["quality_eligible"],
            "package_size_bytes": package_sizes[variant],
            "model_load_ms": summarize([expected_load_ms]),
            "same_text_encode_ms": summarize(encode_ms),
            "same_text_decode_ms": summarize(decode_ms),
            "same_text_total_ms": summarize(total_ms),
            "http_round_trip_ms": summarize(http_ms),
            "quality_process": {
                "maximum_rss_kib": summarize([float(process["maximum_rss_kib"])]),
                "repetitions": [process],
            },
            "quality_repetitions": scored["repetitions"],
            "runtime_buffer_evidence": matched_patterns,
        }

        rounds: dict[str, Any] = {}
        encode_tps: list[float] = []
        decode_tps: list[float] = []
        ttft_ms: list[float] = []
        combined_ms: list[float] = []
        rss_values: list[float] = []
        elapsed_values: list[float] = []
        for round_number, round_order in enumerate(order, start=1):
            position = round_order.index(variant) + 1
            result = benchmark_round(
                variant_dir / f"round-{round_number}-position-{position}",
                f"/{variant}/{model['entrypoint']}",
                contract["benchmark"]["input_tokens"],
                contract["benchmark"]["output_tokens"],
                contract["benchmark"]["threads"],
                contract["benchmark"]["measured_repetitions_per_round"],
            )
            encode_tps.extend(float(value) for value in result["prompt"]["samples_ts"])
            decode_tps.extend(float(value) for value in result["generation"]["samples_ts"])
            ttft_ms.extend(result["prompt_ms"])
            combined_ms.extend(result["total_ms"])
            rss_values.append(float(result["process"]["maximum_rss_kib"]))
            elapsed_values.append(elapsed_seconds(result["process"]["elapsed"]))
            rounds[str(round_number)] = {"position": position, **result}
        benchmark_variants[variant] = {
            "metrics": {
                "encode_tokens_per_sec": summarize(encode_tps),
                "decode_tokens_per_sec": summarize(decode_tps),
                "ttft_ms": summarize(ttft_ms),
                "total_ms": summarize(combined_ms),
            },
            "process": {
                "maximum_rss_kib": summarize(rss_values),
                "elapsed_seconds": summarize(elapsed_values),
            },
            "rounds": rounds,
        }

    eligible = {
        name: {
            "minimum_accuracy": record["minimum_accuracy"],
            "same_text_total_ms_median": record["same_text_total_ms"]["median"],
            "maximum_quality_process_rss_kib": record["quality_process"]["maximum_rss_kib"]["max"],
            "package_size_bytes": float(record["package_size_bytes"]),
        }
        for name, record in application.items()
        if record["quality_eligible"]
    }
    frontier = pareto_front(eligible, contract["pareto"]["directions"])
    platform = {
        "uname": (evidence_dir / "uname.txt").read_text().strip(),
        "lscpu": parse_lscpu((evidence_dir / "lscpu.txt").read_text()),
    }
    return {
        "schema_version": 1,
        "experiment_id": "E3d",
        "status": "valid_frontier" if frontier else "valid_no_quality_eligible_variant",
        "source": {
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{provenance['github_run_id']}",
            "artifact_name": f"{contract['artifact_name_prefix']}-{provenance['github_run_id']}-{provenance['github_run_attempt']}",
            "artifact_retention_days": 90,
        },
        "platform": platform,
        "provenance": provenance,
        "quality": quality,
        "application": application,
        "synthetic_token_benchmark": {
            "parameters": contract["benchmark"],
            "variants": benchmark_variants,
        },
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
    manifest = build_manifest(
        arguments.evidence_dir, arguments.contract, arguments.models, arguments.tasks
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
