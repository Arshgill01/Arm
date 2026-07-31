#!/usr/bin/env python3
"""Validate E3 evidence and derive the quality-constrained Pareto frontier."""

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


VARIANTS = ("llama_q4_0", "llama_q4_k_m", "mnn_int4")
ROUND_PATTERN = re.compile(r"^round-(\d+)-position-(\d+)$")
PERFORMANCE_FIELDS = {
    "encode_tokens_per_sec": "encode_tokens_per_sec",
    "decode_tokens_per_sec": "decode_tokens_per_sec",
    "ttft_ms": "time_to_first_token_ms",
    "total_ms": "total_time_ms",
}
FRONTIER_DIRECTIONS = {
    "minimum_accuracy": "higher",
    "same_text_total_ms_median": "lower",
    "maximum_quality_process_rss_kib": "lower",
    "package_size_bytes": "lower",
}


def normalize_quality_sources(
    quality: dict[str, Any], variants: Sequence[str]
) -> None:
    for variant in variants:
        repetitions = quality["variants"][variant]["repetitions"]
        for repetition, run in enumerate(repetitions, start=1):
            run["source"] = (
                f"variants/{variant}/quality-repeat-{repetition}.json"
            )


def pareto_front(
    candidates: dict[str, dict[str, float]], directions: dict[str, str]
) -> list[str]:
    def dominates(left: dict[str, float], right: dict[str, float]) -> bool:
        at_least_as_good = True
        strictly_better = False
        for metric, direction in directions.items():
            if direction == "higher":
                at_least_as_good &= left[metric] >= right[metric]
                strictly_better |= left[metric] > right[metric]
            elif direction == "lower":
                at_least_as_good &= left[metric] <= right[metric]
                strictly_better |= left[metric] < right[metric]
            else:
                raise ValueError(f"unknown Pareto direction {direction}")
        return at_least_as_good and strictly_better

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
) -> dict[str, Any]:
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
        iterations = benchmark.get("iterations")
        expected_count = benchmark.get("parameters", {}).get("num_iterations")
        if not isinstance(iterations, list) or len(iterations) != expected_count:
            raise ValueError(f"invalid iterations for {variant} round {round_number}")
        timing = parse_time_output((candidate / "time.log").read_text(encoding="utf-8"))
        if timing["exit_status"] != 0:
            raise ValueError(f"failed benchmark for {variant} round {round_number}")
        rounds[round_number] = {
            "position": position,
            "parameters": benchmark["parameters"],
            "iterations": iterations,
            "process": timing,
        }
    if sorted(rounds) != [1, 2, 3]:
        raise ValueError(f"{variant} must contain performance rounds 1 through 3")
    return rounds


def summarize_quality_processes(
    evidence_dir: Path, variants: Sequence[str]
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
            for repetition in (1, 2)
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


def build_manifest(
    evidence_dir: Path, models_path: Path, tasks_path: Path
) -> dict[str, Any]:
    models = load_object(models_path)
    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E3":
        raise ValueError("provenance does not identify E3")
    if load_object(evidence_dir / "models-manifest.json") != models:
        raise ValueError("artifact model manifest differs from the frozen manifest")
    if sha256_file(evidence_dir / "tasks-manifest.json") != sha256_file(tasks_path):
        raise ValueError("artifact task manifest differs from the frozen manifest")

    order: Sequence[Sequence[str]] = provenance["benchmark"]["execution_order"]
    if len(order) != 3 or any(sorted(round_order) != sorted(VARIANTS) for round_order in order):
        raise ValueError("invalid E3 cyclic execution order")
    expected_positions = {
        variant: {
            round_number: round_order.index(variant) + 1
            for round_number, round_order in enumerate(order, start=1)
        }
        for variant in VARIANTS
    }

    model_hash_record = (evidence_dir / "model-sha256.txt").read_text(encoding="utf-8")
    model_size_record = (evidence_dir / "model-files.txt").read_text(encoding="utf-8")
    package_sizes: dict[str, int] = {}
    for variant in VARIANTS:
        model = models["variants"][variant]
        package_sizes[variant] = sum(item["size_bytes"] for item in model["files"])
        for item in model["files"]:
            expected_path = f"{variant}/{item['path']}"
            if item["sha256"] not in model_hash_record:
                raise ValueError(f"missing checksum evidence for {expected_path}")
            if f"{expected_path} {item['size_bytes']} bytes" not in model_size_record:
                raise ValueError(f"missing size evidence for {expected_path}")

    quality = build_summary(models_path, tasks_path, evidence_dir)
    normalize_quality_sources(quality, VARIANTS)
    if quality["tasks"]["count"] != provenance["quality"]["tasks"]:
        raise ValueError("quality task count differs from provenance")
    quality_process = summarize_quality_processes(evidence_dir, VARIANTS)

    application: dict[str, Any] = {}
    for variant in VARIANTS:
        repetitions = quality["variants"][variant]["repetitions"]
        raw_runs = [
            load_object(
                evidence_dir
                / "variants"
                / variant
                / f"quality-repeat-{repetition}.json"
            )
            for repetition in (1, 2)
        ]
        encode_values: list[float] = []
        decode_values: list[float] = []
        total_values: list[float] = []
        load_values: list[float] = []
        for raw_run in raw_runs:
            load_values.append(float(raw_run["model_load_ms"]))
            for case in raw_run["cases"]:
                encode = float(case["encode_ms"])
                decode = float(case["decode_ms"])
                encode_values.append(encode)
                decode_values.append(decode)
                total_values.append(encode + decode)
        application[variant] = {
            "minimum_accuracy": quality["variants"][variant]["minimum_accuracy"],
            "quality_eligible": quality["variants"][variant]["quality_eligible"],
            "package_size_bytes": package_sizes[variant],
            "model_load_ms": summarize(load_values),
            "same_text_encode_ms": summarize(encode_values),
            "same_text_decode_ms": summarize(decode_values),
            "same_text_total_ms": summarize(total_values),
            "quality_process": quality_process[variant],
            "quality_repetitions": repetitions,
        }

    performance_rounds = {
        variant: discover_performance(
            evidence_dir, variant, expected_positions[variant]
        )
        for variant in VARIANTS
    }
    parameter_keys = (
        "context_size",
        "num_input_tokens",
        "num_iterations",
        "num_output_tokens",
        "num_threads",
        "num_warmup",
    )
    common_parameters: dict[str, Any] | None = None
    performance_summary: dict[str, Any] = {}
    for variant in VARIANTS:
        pooled = {metric: [] for metric in PERFORMANCE_FIELDS}
        elapsed_values: list[float] = []
        rss_values: list[float] = []
        for round_data in performance_rounds[variant].values():
            parameters = {
                key: round_data["parameters"][key] for key in parameter_keys
            }
            if common_parameters is None:
                common_parameters = parameters
            elif parameters != common_parameters:
                raise ValueError("E3 performance parameters differ")
            for output_name, input_name in PERFORMANCE_FIELDS.items():
                pooled[output_name].extend(
                    float(item[input_name]) for item in round_data["iterations"]
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
        for variant in VARIANTS
        if application[variant]["quality_eligible"]
    }
    frontier = pareto_front(frontier_inputs, FRONTIER_DIRECTIONS)
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E3",
        "status": "valid_frontier" if frontier else "valid_no_quality_eligible_variant",
        "source": {
            "artifact_name": f"e3-qwen-frontier-{run_id}-{provenance['github_run_attempt']}",
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "artifact_retention_days": 90,
        },
        "provenance": provenance,
        "platform": {
            **parse_lscpu((evidence_dir / "lscpu.txt").read_text(encoding="utf-8")),
            "uname": (evidence_dir / "uname.txt").read_text(encoding="utf-8").strip(),
        },
        "validation": {
            "quality_policy_predeclared": True,
            "performance_comparison_allowed": True,
            "cross_runtime_token_rate_is_secondary": True,
            "quality_eligible_variants": sorted(frontier_inputs),
        },
        "quality": quality,
        "application": application,
        "synthetic_token_benchmark": {
            "parameters": common_parameters,
            "variants": performance_summary,
        },
        "pareto": {
            "directions": FRONTIER_DIRECTIONS,
            "inputs": frontier_inputs,
            "frontier": frontier,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    manifest = build_manifest(
        arguments.evidence_dir, arguments.models, arguments.tasks
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
