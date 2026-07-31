#!/usr/bin/env python3
"""Validate paired E2 evidence and calculate predeclared KleidiAI effects."""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path
from typing import Any, Sequence

from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize


VARIANTS = ("generic", "kleidiai")
METRICS = {
    "encode_tokens_per_sec": ("encode_tokens_per_sec", "higher"),
    "decode_tokens_per_sec": ("decode_tokens_per_sec", "higher"),
    "ttft_ms": ("time_to_first_token_ms", "lower"),
    "total_ms": ("total_time_ms", "lower"),
}
ROUND_PATTERN = re.compile(r"^round-(\d+)-position-(\d+)$")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def paired_effect(
    generic_rounds: dict[int, list[float]],
    kleidiai_rounds: dict[int, list[float]],
    direction: str,
) -> dict[str, Any]:
    if generic_rounds.keys() != kleidiai_rounds.keys():
        raise ValueError("paired variants do not contain the same rounds")
    ratios: list[float] = []
    round_means: list[dict[str, float | int]] = []
    for round_number in sorted(generic_rounds):
        generic_mean = statistics.fmean(generic_rounds[round_number])
        kleidiai_mean = statistics.fmean(kleidiai_rounds[round_number])
        if direction == "higher":
            ratio = kleidiai_mean / generic_mean
        elif direction == "lower":
            ratio = generic_mean / kleidiai_mean
        else:
            raise ValueError(f"unknown metric direction {direction}")
        ratios.append(ratio)
        round_means.append(
            {
                "round": round_number,
                "generic": generic_mean,
                "kleidiai": kleidiai_mean,
                "improvement_ratio": ratio,
            }
        )
    median_ratio = statistics.median(ratios)
    improved_rounds = sum(ratio > 1.0 for ratio in ratios)
    return {
        "direction": f"{direction}_is_better",
        "round_means": round_means,
        "round_improvement_ratios": ratios,
        "median_improvement_ratio": median_ratio,
        "median_improvement_percent": (median_ratio - 1.0) * 100.0,
        "improved_rounds": improved_rounds,
        "total_rounds": len(ratios),
        "material_1_05x_and_3_of_4": median_ratio >= 1.05
        and improved_rounds >= 3,
    }


def discover_variant(
    evidence_dir: Path, variant: str, expected_positions: dict[int, int]
) -> dict[str, Any]:
    variant_dir = evidence_dir / variant
    configure = (variant_dir / "configure.log").read_text(encoding="utf-8")
    build = (variant_dir / "build.log").read_text(encoding="utf-8")
    ctest = (variant_dir / "ctest.log").read_text(encoding="utf-8")
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
            raise ValueError(f"duplicate {variant} round {round_number}")
        if expected_positions.get(round_number) != position:
            raise ValueError(f"unexpected execution position for {variant} round {round_number}")
        benchmark = load_object(candidate / "benchmark.json")
        stdout = (candidate / "stdout.log").read_text(encoding="utf-8")
        stderr = (candidate / "stderr.log").read_text(encoding="utf-8")
        timing = parse_time_output((candidate / "time.log").read_text(encoding="utf-8"))
        iterations = benchmark.get("iterations")
        expected_count = benchmark.get("parameters", {}).get("num_iterations")
        if not isinstance(iterations, list) or len(iterations) != expected_count:
            raise ValueError(f"invalid iteration count for {variant} round {round_number}")
        if timing["exit_status"] != 0:
            raise ValueError(f"benchmark failed for {variant} round {round_number}")
        rounds[round_number] = {
            "position": position,
            "parameters": benchmark["parameters"],
            "iterations": iterations,
            "tool_reported_results": benchmark.get("results"),
            "process": timing,
            "quality_warning": "GENERATION QUALITY WILL BE DEGRADED" in stderr,
            "kleidiai_runtime_buffer": "CPU_KLEIDIAI model buffer size" in stdout,
        }
    if sorted(rounds) != [1, 2, 3, 4]:
        raise ValueError(f"{variant} must contain rounds 1 through 4")
    return {
        "configure_kleidiai": "KleidiAI: ON" in configure,
        "configure_generic": "KleidiAI: OFF" in configure,
        "build_completed": "Built target llm-bench-cli" in build
        and "Built target llm-cpp-tests" in build,
        "functional_test_passed": "100% tests passed" in ctest
        and "llamatextconfig_phi_2_json" in ctest,
        "rounds": rounds,
    }


def build_manifest(evidence_dir: Path) -> dict[str, Any]:
    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E2":
        raise ValueError("provenance does not identify E2")
    order: Sequence[Sequence[str]] = provenance["benchmark"]["execution_order"]
    if len(order) != 4 or any(sorted(pair) != list(VARIANTS) for pair in order):
        raise ValueError("invalid paired execution order")
    expected_positions = {
        variant: {
            round_number: pair.index(variant) + 1
            for round_number, pair in enumerate(order, start=1)
        }
        for variant in VARIANTS
    }
    variants = {
        variant: discover_variant(evidence_dir, variant, expected_positions[variant])
        for variant in VARIANTS
    }
    model_record = (evidence_dir / "model.txt").read_text(encoding="utf-8")

    assertions = {
        "both_builds_completed": all(
            variants[variant]["build_completed"] for variant in VARIANTS
        ),
        "both_functional_tests_passed": all(
            variants[variant]["functional_test_passed"] for variant in VARIANTS
        ),
        "generic_config_is_off": variants["generic"]["configure_generic"]
        and not variants["generic"]["configure_kleidiai"],
        "kleidiai_config_is_on": variants["kleidiai"]["configure_kleidiai"]
        and not variants["kleidiai"]["configure_generic"],
        "generic_has_no_kleidiai_buffer": not any(
            item["kleidiai_runtime_buffer"]
            for item in variants["generic"]["rounds"].values()
        ),
        "kleidiai_has_runtime_buffer_every_round": all(
            item["kleidiai_runtime_buffer"]
            for item in variants["kleidiai"]["rounds"].values()
        ),
        "model_checksum_matches": provenance["model_sha256"] in model_record,
        "single_controlled_difference_declared": provenance.get(
            "controlled_difference"
        )
        == "USE_KLEIDIAI only",
    }
    if not all(assertions.values()):
        failed = [name for name, passed in assertions.items() if not passed]
        raise ValueError(f"E2 evidence assertions failed: {', '.join(failed)}")

    common_parameters: dict[str, Any] | None = None
    pooled: dict[str, dict[str, list[float]]] = {
        variant: {metric: [] for metric in METRICS} for variant in VARIANTS
    }
    comparison_inputs: dict[str, dict[str, dict[int, list[float]]]] = {
        metric: {variant: {} for variant in VARIANTS} for metric in METRICS
    }
    for variant in VARIANTS:
        for round_number, round_data in variants[variant]["rounds"].items():
            parameters = round_data["parameters"]
            if common_parameters is None:
                common_parameters = parameters
            elif parameters != common_parameters:
                raise ValueError("benchmark parameters differ across paired runs")
            for metric, (field, _direction) in METRICS.items():
                values = [float(iteration[field]) for iteration in round_data["iterations"]]
                pooled[variant][metric].extend(values)
                comparison_inputs[metric][variant][round_number] = values

    summaries = {
        variant: {
            metric: summarize(values) for metric, values in pooled[variant].items()
        }
        for variant in VARIANTS
    }
    comparisons = {
        metric: paired_effect(
            comparison_inputs[metric]["generic"],
            comparison_inputs[metric]["kleidiai"],
            direction,
        )
        for metric, (_field, direction) in METRICS.items()
    }
    primary = comparisons["encode_tokens_per_sec"]
    primary_accepted = bool(primary["material_1_05x_and_3_of_4"])
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E2",
        "status": "valid_primary_win" if primary_accepted else "valid_no_primary_win",
        "source": {
            "artifact_name": f"e2-kleidiai-ablation-{run_id}-{provenance['github_run_attempt']}",
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "artifact_retention_days": 90,
        },
        "provenance": provenance,
        "platform": {
            **parse_lscpu((evidence_dir / "lscpu.txt").read_text(encoding="utf-8")),
            "uname": (evidence_dir / "uname.txt").read_text(encoding="utf-8").strip(),
        },
        "validation": {
            "assertions": assertions,
            "performance_comparison_allowed": True,
            "quality_claims_allowed": False,
            "primary_metric": "encode_tokens_per_sec",
            "predeclared_threshold": {
                "median_paired_improvement_ratio": 1.05,
                "minimum_improved_rounds": 3,
                "total_rounds": 4,
            },
            "primary_threshold_met": primary_accepted,
            "notes": [
                "The only intended build difference is USE_KLEIDIAI.",
                "The legacy GGUF warning excludes quality claims but not this same-model performance ablation.",
            ],
        },
        "benchmark": {
            "parameters": common_parameters,
            "pooled_summary": summaries,
            "paired_comparison": comparisons,
            "rounds": {
                variant: variants[variant]["rounds"] for variant in VARIANTS
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    manifest = build_manifest(arguments.evidence_dir)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
