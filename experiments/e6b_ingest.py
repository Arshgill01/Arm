#!/usr/bin/env python3
"""Validate paired E6b Arm quantizer evidence and apply the frozen gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output


VARIANTS = ("baseline", "patched")
INFERENCE_METRICS = {
    "encode_tokens_per_sec": ("encode_tokens_per_sec", "higher"),
    "decode_tokens_per_sec": ("decode_tokens_per_sec", "higher"),
    "ttft_ms": ("time_to_first_token_ms", "lower"),
    "total_ms": ("total_time_ms", "lower"),
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


def read_exit_status(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError as error:
        raise ValueError(f"{path} does not contain an exit status") from error


def parse_perf(path: Path, expected_sizes: list[int]) -> dict[int, float]:
    values: dict[int, float] = {}
    current_size: int | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        size_match = re.match(r"^\s+(\d+) values \(", line)
        if size_match:
            current_size = int(size_match.group(1))
            continue
        throughput_match = re.match(
            r"^\s+float32 throughput\s+:\s+([0-9]+(?:\.[0-9]+)?) GB/s$",
            line,
        )
        if throughput_match and current_size is not None:
            if current_size in values:
                raise ValueError(f"{path} repeats size {current_size}")
            value = float(throughput_match.group(1))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{path} contains invalid throughput")
            values[current_size] = value
            current_size = None
    if sorted(values) != sorted(expected_sizes):
        raise ValueError(f"{path} does not contain the frozen benchmark sizes")
    return values


def paired_effect(
    baseline: dict[int, list[float]],
    patched: dict[int, list[float]],
    direction: str,
) -> dict[str, Any]:
    if baseline.keys() != patched.keys():
        raise ValueError("paired variants do not contain the same rounds")
    ratios: list[float] = []
    rounds: list[dict[str, float | int]] = []
    for round_number in sorted(baseline):
        baseline_mean = statistics.fmean(baseline[round_number])
        patched_mean = statistics.fmean(patched[round_number])
        if direction == "higher":
            ratio = patched_mean / baseline_mean
        elif direction == "lower":
            ratio = baseline_mean / patched_mean
        else:
            raise ValueError(f"unknown direction {direction}")
        ratios.append(ratio)
        rounds.append(
            {
                "round": round_number,
                "baseline": baseline_mean,
                "patched": patched_mean,
                "improvement_ratio": ratio,
            }
        )
    median_ratio = statistics.median(ratios)
    return {
        "direction": f"{direction}_is_better",
        "rounds": rounds,
        "round_improvement_ratios": ratios,
        "median_improvement_ratio": median_ratio,
        "median_improvement_percent": (median_ratio - 1.0) * 100.0,
        "improved_rounds": sum(ratio > 1.0 for ratio in ratios),
        "total_rounds": len(ratios),
    }


def assembly_summary(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8").lower()
    paired_vector_stores = len(
        re.findall(
            r"\bstp\s+q(?:[0-9]|[12][0-9]|3[01])\s*,\s*q(?:[0-9]|[12][0-9]|3[01])\b",
            text,
        )
    )
    return {
        "static_instructions": len(
            re.findall(r"^\s*[0-9a-f]+:\s+\S+", text, flags=re.MULTILINE)
        ),
        "byte_stores": len(re.findall(r"\b(?:str|stur)\s+b(?:[0-9]|[12][0-9]|3[01])\b", text)),
        "vector_stores": len(
            re.findall(
                r"\b(?:str|stur)\s+q(?:[0-9]|[12][0-9]|3[01])\b", text
            )
        )
        + 2 * paired_vector_stores,
        "vector_narrows": len(re.findall(r"\b(?:xtn2?|uzp1)\b", text)),
    }


def quality_signature(path: Path, expected_count: int) -> list[dict[str, Any]]:
    quality = load_object(path)
    cases = quality.get("cases")
    if not isinstance(cases, list) or len(cases) != expected_count:
        raise ValueError(f"{path} has an invalid quality case count")
    signature = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError(f"{path} contains a malformed quality case")
        signature.append(
            {
                key: case.get(key)
                for key in ("id", "response", "generated_tokens", "termination_reason")
            }
        )
    if len({item["id"] for item in signature}) != expected_count:
        raise ValueError(f"{path} contains duplicate quality case identifiers")
    return signature


def validate_build(
    evidence_dir: Path,
    variant: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    directory = evidence_dir / "variants" / variant
    expected_commit = contract["upstream"]["llama_cpp_commit"]
    if (directory / "llama-cpp-commit.txt").read_text(encoding="utf-8").strip() != expected_commit:
        raise ValueError(f"{variant} llama.cpp commit differs from contract")
    if read_exit_status(directory / "build-exit.txt") != 0:
        raise ValueError(f"{variant} build failed")
    if read_exit_status(directory / "quantize-test-exit.txt") != 0:
        raise ValueError(f"{variant} upstream quantization test failed")
    if read_exit_status(directory / "quality-exit.txt") != 0:
        raise ValueError(f"{variant} quality execution failed")
    configure = (directory / "configure.log").read_text(encoding="utf-8")
    if "KleidiAI: OFF" not in configure or "CPU_ARCH=Armv8.6_1" not in configure:
        raise ValueError(f"{variant} configuration differs from contract")
    test_log = (directory / "quantize-test.log").read_text(encoding="utf-8")
    if "0 tests failed" not in test_log:
        raise ValueError(f"{variant} upstream quantization test is incomplete")
    source_sha256 = (
        directory / "source-sha256.txt"
    ).read_text(encoding="utf-8").split()[0]
    expected_source_sha256 = contract["patch"][
        "source_sha256_after" if variant == "patched" else "source_sha256_before"
    ]
    if source_sha256 != expected_source_sha256:
        raise ValueError(f"{variant} source checksum differs from contract")
    changed_files = (
        directory / "changed-files.txt"
    ).read_text(encoding="utf-8").splitlines()
    if variant == "patched":
        if changed_files != [contract["patch"]["target"]]:
            raise ValueError("patched source tree has an unexpected change set")
        if not (directory / "applied.patch").read_text(encoding="utf-8"):
            raise ValueError("patched source diff is empty")
    elif changed_files or (directory / "source-diff.patch").read_text(encoding="utf-8"):
        raise ValueError("baseline source tree is not clean")
    quality_process = parse_time_output(
        (directory / "quality-time.log").read_text(encoding="utf-8")
    )
    if quality_process["exit_status"] != 0:
        raise ValueError(f"{variant} quality process evidence is not clean")
    return {
        "assembly": assembly_summary(directory / "assembly.txt"),
        "quality": quality_signature(
            directory / "quality.json", contract["correctness"]["quality_task_count"]
        ),
        "quality_process": quality_process,
    }


def validate_round(
    directory: Path, variant: str, contract: dict[str, Any]
) -> dict[str, Any]:
    if read_exit_status(directory / "perf-exit.txt") != 0:
        raise ValueError(f"{directory.name} direct benchmark failed")
    perf_process = parse_time_output(
        (directory / "perf-time.log").read_text(encoding="utf-8")
    )
    inference_process = parse_time_output(
        (directory / "inference-time.log").read_text(encoding="utf-8")
    )
    if perf_process["exit_status"] != 0 or inference_process["exit_status"] != 0:
        raise ValueError(f"{directory.name} process evidence is not clean")
    benchmark = load_object(directory / "benchmark.json")
    parameters = benchmark.get("parameters")
    iterations = benchmark.get("iterations")
    expected = contract["inference_benchmark"]
    expected_parameters = {
        "num_input_tokens": expected["input_tokens"],
        "num_output_tokens": expected["output_tokens"],
        "context_size": expected["context"],
        "num_threads": expected["threads"],
        "num_iterations": expected["measured_iterations"],
        "num_warmup": expected["warmup_iterations"],
    }
    if not isinstance(parameters, dict) or not isinstance(iterations, list):
        raise ValueError(f"{directory.name} has malformed inference evidence")
    for key, value in expected_parameters.items():
        if parameters.get(key) != value:
            raise ValueError(f"{directory.name} inference parameter {key} differs")
    if len(iterations) != expected["measured_iterations"]:
        raise ValueError(f"{directory.name} inference iteration count differs")
    metrics: dict[str, list[float]] = {}
    for name, (field, _direction) in INFERENCE_METRICS.items():
        values = [float(item[field]) for item in iterations]
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError(f"{directory.name} contains invalid {name}")
        metrics[name] = values
    maximum_rss_kib = inference_process["maximum_rss_kib"]
    if not isinstance(maximum_rss_kib, int):
        raise ValueError(f"{directory.name} lacks RSS evidence")
    return {
        "variant": variant,
        "direct_gib_per_second": parse_perf(
            directory / "perf.log", contract["direct_benchmark"]["sizes"]
        ),
        "direct_process": perf_process,
        "inference_parameters": parameters,
        "inference_iterations": iterations,
        "inference_metrics": metrics,
        "inference_process": inference_process,
    }


def evaluate_win(
    direct: dict[str, dict[str, Any]],
    inference: dict[str, dict[str, Any]],
    rss: dict[str, int],
    assembly: dict[str, dict[str, int]],
    quality_unchanged: bool,
    acceptance: dict[str, Any],
) -> tuple[dict[str, bool], dict[str, bool], dict[str, bool]]:
    direct_criteria = {
        size: (
            comparison["median_improvement_ratio"]
            >= acceptance["direct_minimum_median_improvement_ratio_by_size"][size]
            and comparison["improved_rounds"]
            >= acceptance["direct_minimum_improved_rounds_by_size"][size]
        )
        for size, comparison in direct.items()
    }
    inference_criteria = {
        metric: comparison["median_improvement_ratio"]
        >= acceptance["minimum_inference_improvement_ratio"]
        for metric, comparison in inference.items()
    }
    baseline_assembly = assembly["baseline"]
    patched_assembly = assembly["patched"]
    criteria = {
        "bit_identical_quantizer_output": True,
        "quality_outputs_unchanged": quality_unchanged,
        "baseline_scalar_store_mechanism_reproduced": (
            baseline_assembly["byte_stores"]
            >= acceptance["minimum_baseline_byte_stores"]
        ),
        "patched_byte_store_limit_met": (
            patched_assembly["byte_stores"]
            <= acceptance["maximum_patched_byte_stores"]
        ),
        "patched_vector_narrow_mechanism_present": (
            patched_assembly["vector_narrows"]
            >= acceptance["minimum_patched_vector_narrows"]
        ),
        "patched_vector_store_mechanism_present": (
            patched_assembly["vector_stores"]
            >= acceptance["minimum_patched_vector_stores"]
        ),
        "direct_benchmark_gates_met": all(direct_criteria.values()),
        "inference_guardrails_met": all(inference_criteria.values()),
        "rss_guardrail_met": (
            rss["patched"]
            <= rss["baseline"] + acceptance["maximum_patched_rss_increase_kib"]
        ),
    }
    return criteria, direct_criteria, inference_criteria


def build_manifest(
    evidence_dir: Path,
    contract_path: Path,
    patch_path: Path,
    tasks_path: Path,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("experiment_id") != "E6b":
        raise ValueError("contract does not identify E6b")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E6b contract")
    if sha256_file(patch_path) != contract["patch"]["sha256"]:
        raise ValueError("frozen patch checksum differs from contract")
    if sha256_file(evidence_dir / "patch.patch") != contract["patch"]["sha256"]:
        raise ValueError("artifact patch checksum differs from contract")
    if sha256_file(tasks_path) != contract["correctness"]["quality_tasks_sha256"]:
        raise ValueError("quality task checksum differs from contract")
    if sha256_file(evidence_dir / "quality-tasks.json") != contract["correctness"]["quality_tasks_sha256"]:
        raise ValueError("artifact quality tasks differ from contract")

    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != "E6b":
        raise ValueError("provenance does not identify E6b")
    if provenance.get("controlled_difference") != "frozen q8_0 vector-store patch only":
        raise ValueError("controlled difference is not declared exactly")
    model_record = (evidence_dir / "model.txt").read_text(encoding="utf-8")
    if (
        contract["model"]["sha256"] not in model_record
        or str(contract["model"]["size_bytes"]) not in model_record
    ):
        raise ValueError("model evidence differs from contract")
    equivalence = (evidence_dir / "equivalence.log").read_text(encoding="utf-8").strip()
    expected_equivalence = (
        f"bit-identical finite_values={contract['correctness']['finite_values']} "
        f"zero_block={str(contract['correctness']['includes_zero_block']).lower()}"
    )
    if equivalence != expected_equivalence:
        raise ValueError("standalone quantizer equivalence test failed")

    builds = {
        variant: validate_build(evidence_dir, variant, contract)
        for variant in VARIANTS
    }
    quality_unchanged = builds["baseline"]["quality"] == builds["patched"]["quality"]

    round_data: dict[str, dict[int, dict[str, Any]]] = {
        variant: {} for variant in VARIANTS
    }
    for round_number, order in enumerate(contract["execution_order"], start=1):
        if sorted(order) != list(VARIANTS):
            raise ValueError("execution order does not contain both variants")
        for position, variant in enumerate(order, start=1):
            directory = (
                evidence_dir
                / "rounds"
                / f"round-{round_number}-position-{position}-{variant}"
            )
            round_data[variant][round_number] = validate_round(
                directory, variant, contract
            )

    direct: dict[str, Any] = {}
    for size in contract["direct_benchmark"]["sizes"]:
        inputs = {
            variant: {
                round_number: [data["direct_gib_per_second"][size]]
                for round_number, data in round_data[variant].items()
            }
            for variant in VARIANTS
        }
        direct[str(size)] = paired_effect(
            inputs["baseline"], inputs["patched"], "higher"
        )

    inference: dict[str, Any] = {}
    for metric, (_field, direction) in INFERENCE_METRICS.items():
        inputs = {
            variant: {
                round_number: data["inference_metrics"][metric]
                for round_number, data in round_data[variant].items()
            }
            for variant in VARIANTS
        }
        inference[metric] = paired_effect(
            inputs["baseline"], inputs["patched"], direction
        )

    rss = {
        variant: max(
            data["inference_process"]["maximum_rss_kib"]
            for data in round_data[variant].values()
        )
        for variant in VARIANTS
    }
    assembly = {variant: builds[variant]["assembly"] for variant in VARIANTS}
    criteria, direct_criteria, inference_criteria = evaluate_win(
        direct,
        inference,
        rss,
        assembly,
        quality_unchanged,
        contract["acceptance"],
    )
    won = all(criteria.values())
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E6b",
        "status": "valid_hot_path_win" if won else "valid_no_hot_path_win",
        "source": {
            "artifact_name": f"e6b-q8-vector-store-{run_id}-{provenance['github_run_attempt']}",
            "github_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}",
            "artifact_retention_days": 90,
        },
        "contract": contract,
        "provenance": provenance,
        "platform": {
            **parse_lscpu((evidence_dir / "lscpu.txt").read_text(encoding="utf-8")),
            "uname": (evidence_dir / "uname.txt").read_text(encoding="utf-8").strip(),
            "compiler": (evidence_dir / "compiler.txt").read_text(encoding="utf-8").strip(),
        },
        "correctness": {
            "equivalence": equivalence,
            "quality_outputs_unchanged": quality_unchanged,
            "quality_signature": builds["patched"]["quality"],
        },
        "assembly": assembly,
        "direct_benchmark": {
            "comparisons": direct,
            "criteria": direct_criteria,
        },
        "inference_benchmark": {
            "comparisons": inference,
            "criteria": inference_criteria,
            "maximum_rss_kib": rss,
        },
        "validation": {
            "criteria": criteria,
            "validated_win": won,
            "weighted_score_used": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    manifest = build_manifest(
        arguments.evidence_dir,
        arguments.contract,
        arguments.patch,
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
