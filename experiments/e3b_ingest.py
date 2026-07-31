#!/usr/bin/env python3
"""Validate E3b/E3c evidence and derive a quality-gated frontier."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Sequence

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e2_ingest import elapsed_seconds
    from experiments.e3_score import build_summary, load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e2_ingest import elapsed_seconds
    from e3_score import build_summary, load_object, sha256_file


ROUND_PATTERN = re.compile(r"^round-(\d+)-position-(\d+)$")
PERFORMANCE_FIELDS = {
    "encode_tokens_per_sec": "encode_tokens_per_sec",
    "decode_tokens_per_sec": "decode_tokens_per_sec",
    "ttft_ms": "time_to_first_token_ms",
    "total_ms": "total_time_ms",
}


def normalize_quality_sources(
    quality: dict[str, Any], variants: Sequence[str]
) -> None:
    for variant in variants:
        for repetition, run in enumerate(
            quality["variants"][variant]["repetitions"], start=1
        ):
            run["source"] = (
                f"variants/{variant}/quality-repeat-{repetition}.json"
            )


def validate_execution_order(
    order: Any, variants: Sequence[str], expected_rounds: int
) -> list[list[str]]:
    if not isinstance(order, list) or len(order) != expected_rounds:
        raise ValueError("invalid execution-order round count")
    normalized: list[list[str]] = []
    for round_order in order:
        if not isinstance(round_order, list) or sorted(round_order) != sorted(variants):
            raise ValueError("every round must contain every variant once")
        normalized.append(round_order)
    return normalized


def pareto_front(
    candidates: dict[str, dict[str, float]], directions: dict[str, str]
) -> list[str]:
    def dominates(left: dict[str, float], right: dict[str, float]) -> bool:
        no_worse = True
        better = False
        for metric, direction in directions.items():
            if direction == "higher":
                no_worse &= left[metric] >= right[metric]
                better |= left[metric] > right[metric]
            elif direction == "lower":
                no_worse &= left[metric] <= right[metric]
                better |= left[metric] < right[metric]
            else:
                raise ValueError(f"unknown Pareto direction {direction}")
        return no_worse and better

    return sorted(
        name
        for name, candidate in candidates.items()
        if not any(
            other_name != name and dominates(other, candidate)
            for other_name, other in candidates.items()
        )
    )


def discover_performance(
    evidence_dir: Path,
    variant: str,
    expected_positions: dict[int, int],
    expected_parameters: dict[str, int],
    expected_model_suffix: str,
) -> dict[int, dict[str, Any]]:
    variant_dir = evidence_dir / "variants" / variant
    rounds: dict[int, dict[str, Any]] = {}
    for candidate in variant_dir.iterdir():
        if not candidate.is_dir():
            continue
        match = ROUND_PATTERN.fullmatch(candidate.name)
        if not match:
            continue
        round_number = int(match.group(1))
        position = int(match.group(2))
        if round_number in rounds:
            raise ValueError(f"duplicate {variant} performance round {round_number}")
        if expected_positions.get(round_number) != position:
            raise ValueError(f"unexpected position for {variant} round {round_number}")
        benchmark = load_object(candidate / "benchmark.json")
        parameters = benchmark.get("parameters")
        iterations = benchmark.get("iterations")
        if not isinstance(parameters, dict) or not isinstance(iterations, list):
            raise ValueError(f"malformed benchmark for {variant} round {round_number}")
        observed_parameters = {
            key: parameters.get(key) for key in expected_parameters
        }
        if observed_parameters != expected_parameters:
            raise ValueError(f"benchmark parameters differ for {variant}")
        if benchmark.get("framework") != "llama.cpp" or not str(
            parameters.get("model_path", "")
        ).endswith(expected_model_suffix):
            raise ValueError(f"benchmark model identity differs for {variant}")
        if len(iterations) != expected_parameters["num_iterations"]:
            raise ValueError(f"invalid iteration count for {variant}")
        timing = parse_time_output(
            (candidate / "time.log").read_text(encoding="utf-8")
        )
        if timing["exit_status"] != 0:
            raise ValueError(f"failed benchmark for {variant} round {round_number}")
        rounds[round_number] = {
            "position": position,
            "parameters": parameters,
            "iterations": iterations,
            "process": timing,
        }
    if sorted(rounds) != sorted(expected_positions):
        raise ValueError(f"{variant} is missing one or more performance rounds")
    return rounds


def summarize_quality_processes(
    evidence_dir: Path, variants: Sequence[str], repetitions: int
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for variant in variants:
        timings = [
            parse_time_output(
                (
                    evidence_dir
                    / "variants"
                    / variant
                    / f"quality-repeat-{repetition}.time.log"
                ).read_text(encoding="utf-8")
            )
            for repetition in range(1, repetitions + 1)
        ]
        if any(item["exit_status"] != 0 for item in timings):
            raise ValueError(f"failed quality process for {variant}")
        if any(
            item["elapsed"] is None or item["maximum_rss_kib"] is None
            for item in timings
        ):
            raise ValueError(f"missing quality process metric for {variant}")
        output[variant] = {
            "elapsed_seconds": summarize(
                [elapsed_seconds(item["elapsed"]) for item in timings]
            ),
            "maximum_rss_kib": summarize(
                [float(item["maximum_rss_kib"]) for item in timings]
            ),
            "repetitions": timings,
        }
    return output


def validate_frozen_inputs(
    evidence_dir: Path,
    contract_path: Path,
    models_path: Path,
    tasks_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_object(contract_path)
    models = load_object(models_path)
    provenance = load_object(evidence_dir / "provenance.json")
    experiment_id = contract.get("experiment_id")
    if experiment_id not in {"E3b", "E3c"}:
        raise ValueError("contract does not identify a supported experiment")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen contract")
    if load_object(evidence_dir / "models-manifest.json") != models:
        raise ValueError("artifact model manifest differs")
    if sha256_file(tasks_path) != contract["quality"]["tasks_sha256"]:
        raise ValueError("task manifest checksum differs from frozen contract")
    if sha256_file(evidence_dir / "tasks-manifest.json") != sha256_file(tasks_path):
        raise ValueError("artifact task manifest differs")
    if provenance.get("experiment_id") != experiment_id:
        raise ValueError("provenance experiment differs from the contract")
    if provenance.get("llm_runner_commit") != contract["upstream"]["llm_runner_commit"]:
        raise ValueError("LLM-Runner revision differs")
    if provenance.get("llama_cpp_commit") != contract["upstream"]["llama_cpp_commit"]:
        raise ValueError("llama.cpp revision differs")
    if provenance.get("execution_order") != contract["benchmark"]["execution_order"]:
        raise ValueError("provenance execution order differs")
    if provenance.get("patch_sha256") != [
        patch["sha256"] for patch in contract["configuration"]["patches"]
    ]:
        raise ValueError("provenance patch checksums differ")
    expected_revisions = {
        name: model["revision"] for name, model in models["variants"].items()
    }
    if provenance.get("model_revisions") != expected_revisions:
        raise ValueError("provenance model revisions differ")
    source_model = models.get("source_model")
    if source_model is not None and provenance.get(
        "source_model_revision"
    ) != source_model.get("revision"):
        raise ValueError("provenance source-model revision differs")
    if "controlled_difference" in contract and provenance.get(
        "controlled_difference"
    ) != contract["controlled_difference"]:
        raise ValueError("provenance controlled difference differs")
    if experiment_id == "E3c":
        quantization_repository = models.get("quantization_repository")
        if (
            not isinstance(source_model, dict)
            or source_model.get("license") != "Apache-2.0"
            or not isinstance(quantization_repository, dict)
            or quantization_repository.get("license") != "Apache-2.0"
            or quantization_repository.get("base_model")
            != source_model.get("repository")
        ):
            raise ValueError("E3c source or quantization provenance differs")
        quantizations: set[str] = set()
        for model in models.get("variants", {}).values():
            if (
                model.get("repository")
                != quantization_repository.get("repository")
                or model.get("revision")
                != quantization_repository.get("revision")
                or model.get("license") != "Apache-2.0"
                or model.get("parameter_scale")
                != source_model.get("parameter_scale")
                or not isinstance(model.get("quantization"), str)
            ):
                raise ValueError("E3c variant provenance differs")
            quantizations.add(model["quantization"])
        if len(quantizations) != len(models["variants"]):
            raise ValueError("E3c quantization candidates are not unique")
    if (evidence_dir / "build-exit.txt").read_text(encoding="utf-8").strip() != "0":
        raise ValueError(f"{experiment_id} build did not pass")
    changed_files = (
        (evidence_dir / "changed-files.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    if changed_files != [
        "ggml/src/ggml-cpu/CMakeLists.txt",
        "ggml/src/ggml-cpu/arch/arm/quants.c",
    ]:
        raise ValueError("unexpected llama.cpp source changes")
    configure_log = (evidence_dir / "configure.log").read_text(encoding="utf-8")
    if "KleidiAI: ON" not in configure_log:
        raise ValueError("configured build does not prove KleidiAI enabled")
    deployment_policy = contract.get("deployment_policy")
    if deployment_policy is not None:
        if not isinstance(deployment_policy, dict) or set(deployment_policy) != {
            "artifact_path",
            "path",
            "sha256",
        }:
            raise ValueError("invalid frozen deployment policy declaration")
        policy_path = Path(deployment_policy["path"])
        artifact_policy_path = evidence_dir / deployment_policy["artifact_path"]
        if (
            sha256_file(policy_path) != deployment_policy["sha256"]
            or sha256_file(artifact_policy_path) != deployment_policy["sha256"]
            or load_object(policy_path) != load_object(artifact_policy_path)
        ):
            raise ValueError("deployment policy differs from frozen input")
        if provenance.get("deployment_policy_sha256") != deployment_policy["sha256"]:
            raise ValueError("provenance deployment policy checksum differs")
    return contract, models, provenance


def build_manifest(
    evidence_dir: Path,
    contract_path: Path,
    models_path: Path,
    tasks_path: Path,
) -> dict[str, Any]:
    contract, models, provenance = validate_frozen_inputs(
        evidence_dir, contract_path, models_path, tasks_path
    )
    experiment_id = contract["experiment_id"]
    variants = contract["variants"]
    if set(variants) != set(models.get("variants", {})):
        raise ValueError("contract and model variant sets differ")
    order = validate_execution_order(
        contract["benchmark"]["execution_order"],
        variants,
        contract["benchmark"]["rounds_per_variant"],
    )

    model_hash_lines = (
        (evidence_dir / "model-sha256.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    model_size_lines = (
        (evidence_dir / "model-files.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    package_sizes: dict[str, int] = {}
    expected_size_lines: list[str] = []
    expected_hashes: dict[str, str] = {}
    for variant in variants:
        model = models["variants"][variant]
        if model.get("license") != "Apache-2.0":
            raise ValueError(f"{variant} does not satisfy the frozen license policy")
        package_sizes[variant] = sum(item["size_bytes"] for item in model["files"])
        for item in model["files"]:
            artifact_path = f"{variant}/{item['path']}"
            expected_size_lines.append(
                f"{artifact_path} {item['size_bytes']} bytes"
            )
            expected_hashes[artifact_path] = item["sha256"]
    if model_size_lines != sorted(expected_size_lines):
        raise ValueError("model size evidence differs from the frozen packages")
    observed_hashes: dict[str, str] = {}
    for line in model_hash_lines:
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise ValueError("malformed model checksum evidence")
        digest, path = fields
        matches = [
            artifact_path
            for artifact_path in expected_hashes
            if path.endswith(f"/{artifact_path}")
        ]
        if len(matches) != 1 or matches[0] in observed_hashes:
            raise ValueError("model checksum path differs from frozen packages")
        observed_hashes[matches[0]] = digest
    if observed_hashes != expected_hashes:
        raise ValueError("model checksum evidence differs from the frozen packages")

    quality = build_summary(models_path, tasks_path, evidence_dir)
    quality["experiment_id"] = experiment_id
    normalize_quality_sources(quality, variants)
    expected_quality_policy = contract["quality"]
    observed_policy = quality["acceptance_policy"]
    if observed_policy != {
        "repetitions": expected_quality_policy["repetitions"],
        "prediction_parser": expected_quality_policy["prediction_parser"],
        "predictions_must_be_stable": expected_quality_policy[
            "predictions_must_be_stable"
        ],
        "absolute_accuracy_floor": expected_quality_policy[
            "absolute_accuracy_floor"
        ],
        "maximum_task_deficit_from_best": expected_quality_policy[
            "maximum_task_deficit_from_best"
        ],
    }:
        raise ValueError("quality scorer policy differs from frozen contract")
    if quality["tasks"]["count"] != expected_quality_policy["task_count"]:
        raise ValueError("quality task count differs")
    quality_process = summarize_quality_processes(
        evidence_dir, variants, expected_quality_policy["repetitions"]
    )

    application: dict[str, Any] = {}
    for variant in variants:
        model = models["variants"][variant]
        raw_runs = [
            load_object(
                evidence_dir
                / "variants"
                / variant
                / f"quality-repeat-{repetition}.json"
            )
            for repetition in range(1, expected_quality_policy["repetitions"] + 1)
        ]
        if any(
            run.get("max_output_tokens") != expected_quality_policy["max_output_tokens"]
            or run.get("threads") != contract["configuration"]["threads"]
            or run.get("context_size") != contract["configuration"]["context"]
            or run.get("framework") != "llama.cpp"
            or (
                experiment_id == "E3c"
                and run.get("chat_template_mode")
                != contract["configuration"]["chat_template_mode"]
            )
            or not str(run.get("model_path", "")).endswith(
                f"/{variant}/{model['entrypoint']}"
            )
            for run in raw_runs
        ):
            raise ValueError(f"quality parameters differ for {variant}")
        runtime_proof = "\n".join(
            (
                evidence_dir
                / "variants"
                / variant
                / f"quality-repeat-{repetition}.stdout.log"
            ).read_text(encoding="utf-8")
            for repetition in range(1, expected_quality_policy["repetitions"] + 1)
        )
        runtime_patterns = model.get(
            "runtime_buffer_patterns", ["CPU_REPACK model buffer size"]
        )
        if (
            not isinstance(runtime_patterns, list)
            or not runtime_patterns
            or any(
                not isinstance(pattern, str) or not pattern
                for pattern in runtime_patterns
            )
        ):
            raise ValueError(f"{variant} has invalid runtime buffer patterns")
        matched_runtime_patterns = sorted(
            pattern for pattern in runtime_patterns if pattern in runtime_proof
        )
        if not matched_runtime_patterns:
            raise ValueError(f"{variant} lacks frozen runtime buffer proof")
        encode_values: list[float] = []
        decode_values: list[float] = []
        total_values: list[float] = []
        load_values: list[float] = []
        for run in raw_runs:
            load_values.append(float(run["model_load_ms"]))
            for case in run["cases"]:
                encode = float(case["encode_ms"])
                decode = float(case["decode_ms"])
                encode_values.append(encode)
                decode_values.append(decode)
                total_values.append(encode + decode)
        scored = quality["variants"][variant]
        application[variant] = {
            "display_name": model["display_name"],
            "minimum_accuracy": scored["minimum_accuracy"],
            "quality_eligible": scored["quality_eligible"],
            "package_size_bytes": package_sizes[variant],
            "model_load_ms": summarize(load_values),
            "same_text_encode_ms": summarize(encode_values),
            "same_text_decode_ms": summarize(decode_values),
            "same_text_total_ms": summarize(total_values),
            "quality_process": quality_process[variant],
            "quality_repetitions": scored["repetitions"],
        }
        if experiment_id == "E3c":
            application[variant]["runtime_buffer_evidence"] = (
                matched_runtime_patterns
            )

    benchmark = contract["benchmark"]
    expected_parameters = {
        "context_size": benchmark["context"],
        "num_input_tokens": benchmark["input_tokens"],
        "num_iterations": benchmark["measured_iterations_per_round"],
        "num_output_tokens": benchmark["output_tokens"],
        "num_threads": benchmark["threads"],
        "num_warmup": benchmark["warmup_iterations_per_round"],
    }
    expected_positions = {
        variant: {
            round_number: round_order.index(variant) + 1
            for round_number, round_order in enumerate(order, start=1)
        }
        for variant in variants
    }
    performance_rounds = {
        variant: discover_performance(
            evidence_dir,
            variant,
            expected_positions[variant],
            expected_parameters,
            f"/{variant}/{models['variants'][variant]['entrypoint']}",
        )
        for variant in variants
    }
    performance_summary: dict[str, Any] = {}
    for variant in variants:
        pooled = {metric: [] for metric in PERFORMANCE_FIELDS}
        elapsed_values: list[float] = []
        rss_values: list[float] = []
        for round_data in performance_rounds[variant].values():
            for output_name, input_name in PERFORMANCE_FIELDS.items():
                pooled[output_name].extend(
                    float(iteration[input_name])
                    for iteration in round_data["iterations"]
                )
            process = round_data["process"]
            if process["elapsed"] is None or process["maximum_rss_kib"] is None:
                raise ValueError(f"missing performance process metric for {variant}")
            elapsed_values.append(elapsed_seconds(process["elapsed"]))
            rss_values.append(float(process["maximum_rss_kib"]))
        performance_summary[variant] = {
            "metrics": {
                metric: summarize(values) for metric, values in pooled.items()
            },
            "process": {
                "elapsed_seconds": summarize(elapsed_values),
                "maximum_rss_kib": summarize(rss_values),
            },
            "rounds": performance_rounds[variant],
        }

    directions = contract["pareto"]["directions"]
    frontier_inputs = {
        variant: {
            "minimum_accuracy": float(application[variant]["minimum_accuracy"]),
            "same_text_total_ms_median": float(
                application[variant]["same_text_total_ms"]["median"]
            ),
            "maximum_quality_process_rss_kib": float(
                application[variant]["quality_process"]["maximum_rss_kib"]["max"]
            ),
            "package_size_bytes": float(package_sizes[variant]),
        }
        for variant in variants
        if application[variant]["quality_eligible"]
    }
    frontier = pareto_front(frontier_inputs, directions)
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "status": (
            "valid_frontier" if frontier else "valid_no_quality_eligible_variant"
        ),
        "source": {
            "artifact_name": (
                f"{contract.get('artifact_name_prefix', 'e3b-quality-anchor')}-"
                f"{run_id}-{provenance['github_run_attempt']}"
            ),
            "github_run_url": (
                f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}"
            ),
            "artifact_retention_days": 90,
        },
        "provenance": provenance,
        "platform": {
            **parse_lscpu(
                (evidence_dir / "lscpu.txt").read_text(encoding="utf-8")
            ),
            "uname": (evidence_dir / "uname.txt")
            .read_text(encoding="utf-8")
            .strip(),
        },
        "validation": {
            "quality_policy_predeclared": True,
            "performance_comparison_allowed": True,
            "same_tasks_and_instruction_as_e3": True,
            "kleidiai_build_enabled": True,
            (
                "runtime_repack_buffer_proven"
                if experiment_id == "E3b"
                else "runtime_model_buffer_proven"
            ): True,
            "validated_patch_set_applied": True,
            "quality_eligible_variants": sorted(frontier_inputs),
            **(
                {"deployment_policy_predeclared": True}
                if contract.get("deployment_policy") is not None
                else {}
            ),
        },
        "quality": quality,
        "application": application,
        "synthetic_token_benchmark": {
            "parameters": expected_parameters,
            "variants": performance_summary,
        },
        "pareto": {
            "directions": directions,
            "inputs": frontier_inputs,
            "frontier": frontier,
            "weighted_score_used": False,
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
        arguments.evidence_dir,
        arguments.contract,
        arguments.models,
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
