#!/usr/bin/env python3
"""Validate an E1 artifact and emit a compact, reviewable result manifest."""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any, Sequence


REQUIRED_FILES = (
    "benchmark.json",
    "benchmark.stderr.log",
    "benchmark.stdout.log",
    "build.log",
    "configure.log",
    "ctest.log",
    "lscpu.txt",
    "model.txt",
    "provenance.json",
    "uname.txt",
)


def nearest_rank(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("cannot calculate a percentile of no values")
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def summarize(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise ValueError("cannot summarize no values")
    mean = statistics.fmean(values)
    deviation = statistics.pstdev(values)
    return {
        "min": min(values),
        "median": statistics.median(values),
        "p95": nearest_rank(values, 0.95),
        "max": max(values),
        "mean": mean,
        "population_stddev": deviation,
        "coefficient_of_variation": deviation / mean if mean else 0.0,
    }


def parse_lscpu(text: str) -> dict[str, Any]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        fields[name.strip()] = value.strip()
    flags = fields.get("Flags", "").split()
    return {
        "architecture": fields.get("Architecture"),
        "logical_cpus": int(fields["CPU(s)"]) if fields.get("CPU(s)", "").isdigit() else None,
        "model_name": fields.get("Model name"),
        "sockets": int(fields["Socket(s)"]) if fields.get("Socket(s)", "").isdigit() else None,
        "threads_per_core": int(fields["Thread(s) per core"])
        if fields.get("Thread(s) per core", "").isdigit()
        else None,
        "relevant_features": sorted(
            set(flags)
            & {
                "asimd",
                "asimddp",
                "bf16",
                "i8mm",
                "sve",
                "sve2",
                "svebf16",
                "svei8mm",
            }
        ),
    }


def parse_time_output(text: str) -> dict[str, Any]:
    def value(pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.MULTILINE)
        return match.group(1).strip() if match else None

    rss = value(r"^\s*Maximum resident set size \(kbytes\):\s*(\d+)\s*$")
    cpu = value(r"^\s*Percent of CPU this job got:\s*([^\n]+)$")
    elapsed = value(
        r"^\s*Elapsed \(wall clock\) time \([^)]*\):\s*([^\n]+)$"
    )
    exit_status = value(r"^\s*Exit status:\s*(\d+)\s*$")
    return {
        "elapsed": elapsed,
        "maximum_rss_kib": int(rss) if rss else None,
        "percent_cpu": cpu,
        "exit_status": int(exit_status) if exit_status else None,
    }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def build_manifest(evidence_dir: Path) -> dict[str, Any]:
    missing = [name for name in REQUIRED_FILES if not (evidence_dir / name).is_file()]
    if missing:
        raise ValueError(f"missing required E1 evidence: {', '.join(missing)}")

    benchmark = load_json(evidence_dir / "benchmark.json")
    provenance = load_json(evidence_dir / "provenance.json")
    stderr = (evidence_dir / "benchmark.stderr.log").read_text(encoding="utf-8")
    stdout = (evidence_dir / "benchmark.stdout.log").read_text(encoding="utf-8")
    configure = (evidence_dir / "configure.log").read_text(encoding="utf-8")
    build = (evidence_dir / "build.log").read_text(encoding="utf-8")
    ctest = (evidence_dir / "ctest.log").read_text(encoding="utf-8")
    model = (evidence_dir / "model.txt").read_text(encoding="utf-8")

    if provenance.get("experiment_id") != "E1":
        raise ValueError("provenance does not identify experiment E1")
    iterations = benchmark.get("iterations")
    if not isinstance(iterations, list) or not iterations:
        raise ValueError("benchmark contains no measured iterations")
    expected_iterations = benchmark.get("parameters", {}).get("num_iterations")
    if len(iterations) != expected_iterations:
        raise ValueError("benchmark iteration count does not match its parameters")

    assertions = {
        "benchmark_exit_zero": parse_time_output(stderr)["exit_status"] == 0,
        "build_completed": "Built target llm-bench-cli" in build
        and "Built target llm-cpp-tests" in build,
        "kleidiai_built": "KleidiAI: ON" in configure
        and "kleidiai" in build.lower(),
        "kleidiai_runtime_buffer": "CPU_KLEIDIAI model buffer size" in stdout,
        "model_checksum_matches": provenance["model_sha256"] in model,
        "phi2_upstream_test_passed": "100% tests passed" in ctest
        and "llamatextconfig_phi_2_json" in ctest,
    }
    if not all(assertions.values()):
        failures = [name for name, passed in assertions.items() if not passed]
        raise ValueError(f"E1 evidence assertions failed: {', '.join(failures)}")

    metric_names = {
        "encode_tokens_per_sec": "encode_tokens_per_sec",
        "decode_tokens_per_sec": "decode_tokens_per_sec",
        "ttft_ms": "time_to_first_token_ms",
        "total_ms": "total_time_ms",
    }
    summaries = {
        output_name: summarize([float(item[input_name]) for item in iterations])
        for output_name, input_name in metric_names.items()
    }
    quality_warning = "GENERATION QUALITY WILL BE DEGRADED" in stderr
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E1",
        "status": "valid_performance_smoke_with_quality_warning"
        if quality_warning
        else "valid_performance_smoke",
        "source": {
            "artifact_name": f"e1-llm-runner-{run_id}-{provenance['github_run_attempt']}",
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
            "quality_claims_allowed": not quality_warning,
            "headline_comparison_allowed": False,
            "notes": [
                "This run establishes build, test, and inference feasibility.",
                "It has no same-job generic baseline and therefore proves no speedup.",
                "The pinned legacy GGUF emitted a missing pre-tokenizer warning; use a modern model artifact before quality comparisons.",
            ],
        },
        "benchmark": {
            "parameters": benchmark["parameters"],
            "iterations": iterations,
            "tool_reported_results": benchmark.get("results"),
            "derived_summary": summaries,
            "process": parse_time_output(stderr),
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
