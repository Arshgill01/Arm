#!/usr/bin/env python3
"""Capture an architecture manifest and characterize hosted-runner timing noise."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
MICROBENCH_SOURCE = SCRIPT_DIR / "e0_microbench.c"


def command_output(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def read_optional(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None


def percentile(values: list[int], quantile: float) -> int:
    ordered = sorted(values)
    rank = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[rank]


def compile_microbench(binary_path: Path) -> dict[str, Any]:
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        os.environ.get("CC", "cc"),
        "-O3",
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        str(MICROBENCH_SOURCE),
        "-o",
        str(binary_path),
    ]
    result = command_output(command)
    if result["returncode"] != 0:
        raise RuntimeError(f"microbenchmark compilation failed: {result}")
    return result


def run_microbench(binary_path: Path, samples: int, iterations: int) -> dict[str, Any]:
    trials: list[dict[str, Any]] = []
    for _ in range(samples):
        result = command_output([str(binary_path), str(iterations)])
        if result["returncode"] != 0:
            raise RuntimeError(f"microbenchmark failed: {result}")
        try:
            trial = json.loads(result["stdout"])
        except json.JSONDecodeError as error:
            raise RuntimeError(f"invalid microbenchmark output: {result}") from error
        trials.append(trial)

    checksums = {trial["checksum"] for trial in trials}
    if len(checksums) != 1:
        raise RuntimeError(f"microbenchmark checksum mismatch: {checksums}")

    durations = [int(trial["elapsed_ns"]) for trial in trials]
    mean = statistics.fmean(durations)
    deviation = statistics.pstdev(durations)
    return {
        "samples": samples,
        "iterations_per_sample": iterations,
        "checksum": checksums.pop(),
        "elapsed_ns": durations,
        "summary": {
            "min": min(durations),
            "median": int(statistics.median(durations)),
            "p95": percentile(durations, 0.95),
            "max": max(durations),
            "mean": mean,
            "population_stddev": deviation,
            "coefficient_of_variation": deviation / mean if mean else None,
        },
    }


def capture_manifest() -> dict[str, Any]:
    sysfs_governors = sorted(
        {
            value
            for path in Path("/sys/devices/system/cpu").glob(
                "cpu[0-9]*/cpufreq/scaling_governor"
            )
            if (value := read_optional(path))
        }
    )
    selected_environment = {
        key: os.environ[key]
        for key in (
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
            "GITHUB_SHA",
            "GITHUB_WORKFLOW",
            "RUNNER_ARCH",
            "RUNNER_NAME",
            "RUNNER_OS",
        )
        if key in os.environ
    }
    commands = {
        name: command_output(command)
        for name, command in {
            "uname": ["uname", "-a"],
            "lscpu_json": ["lscpu", "--json"],
            "compiler": [os.environ.get("CC", "cc"), "--version"],
            "cmake": ["cmake", "--version"],
            "python": [sys.executable, "--version"],
            "git": ["git", "--version"],
            "perf_paranoid": ["sysctl", "kernel.perf_event_paranoid"],
        }.items()
    }
    return {
        "schema_version": 1,
        "platform": {
            "architecture": platform.machine(),
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
        },
        "github": selected_environment,
        "cpuinfo": read_optional(Path("/proc/cpuinfo")),
        "meminfo": read_optional(Path("/proc/meminfo")),
        "os_release": read_optional(Path("/etc/os-release")),
        "scaling_governors": sysfs_governors,
        "commands": commands,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary-dir", type=Path, default=Path("build/e0"))
    parser.add_argument("--samples", type=int, default=21)
    parser.add_argument("--iterations", type=int, default=100_000_000)
    parser.add_argument("--allow-non-arm", action="store_true")
    arguments = parser.parse_args()
    if arguments.samples < 5:
        parser.error("--samples must be at least 5")
    if arguments.iterations <= 0:
        parser.error("--iterations must be positive")
    return arguments


def main() -> int:
    arguments = parse_args()
    architecture = platform.machine().lower()
    if architecture not in {"aarch64", "arm64"} and not arguments.allow_non_arm:
        print(f"refusing performance probe on non-Arm architecture: {architecture}", file=sys.stderr)
        return 2

    binary_path = arguments.binary_dir / "e0_microbench"
    compilation = compile_microbench(binary_path)
    manifest = capture_manifest()
    manifest["microbenchmark"] = run_microbench(
        binary_path,
        samples=arguments.samples,
        iterations=arguments.iterations,
    )
    manifest["microbenchmark"]["compilation"] = compilation

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
