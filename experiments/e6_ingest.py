#!/usr/bin/env python3
"""Validate E6a source-patch evidence and emit a compact manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e2_ingest import elapsed_seconds
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e2_ingest import elapsed_seconds


METRICS = (
    "encode_tokens_per_sec",
    "decode_tokens_per_sec",
    "time_to_first_token_ms",
    "total_time_ms",
)


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


def read_exit(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError as error:
        raise ValueError(f"invalid exit status in {path}") from error


def validate_failure_signature(configure_log: str, build_log: str) -> None:
    required_configure = (
        "Performing Test HAVE_SVE - Failed",
        "+sve2-sm4",
        "+nosve",
    )
    for signature in required_configure:
        if signature not in configure_log:
            raise ValueError(f"unpatched configure log lacks {signature!r}")
    required_build = (
        "sve_dotprod_asm.S",
        "selected processor does not support",
    )
    for signature in required_build:
        if signature not in build_log:
            raise ValueError(f"unpatched build log lacks {signature!r}")


def validate_benchmark(
    benchmark: dict[str, Any], expected: dict[str, Any]
) -> dict[str, Any]:
    parameters = benchmark.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("benchmark parameters are missing")
    parameter_map = {
        "num_input_tokens": "input_tokens",
        "num_output_tokens": "output_tokens",
        "context_size": "context",
        "num_threads": "threads",
        "num_warmup": "warmup_iterations",
        "num_iterations": "measured_iterations",
    }
    for actual_key, expected_key in parameter_map.items():
        if parameters.get(actual_key) != expected[expected_key]:
            raise ValueError(f"benchmark parameter {actual_key} differs from contract")

    iterations = benchmark.get("iterations")
    if not isinstance(iterations, list) or len(iterations) != expected["measured_iterations"]:
        raise ValueError("benchmark iteration count differs from contract")
    if any(item.get("tokens_generated") != expected["output_tokens"] for item in iterations):
        raise ValueError("benchmark did not generate every contracted output token")
    return {
        "parameters": parameters,
        "iterations": iterations,
        "metrics": {
            metric: summarize([float(item[metric]) for item in iterations])
            for metric in METRICS
        },
    }


def build_manifest(
    evidence_dir: Path, contract_path: Path, patch_path: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from the frozen E6a contract")
    if contract.get("experiment_id") != "E6a":
        raise ValueError("contract does not identify E6a")

    provenance = load_object(evidence_dir / "provenance.json")
    upstream = contract["upstream"]
    expected_provenance = {
        "experiment_id": "E6a",
        "llm_runner_commit": upstream["llm_runner_commit"],
        "llama_cpp_commit": upstream["llama_cpp_commit"],
        "patch_sha256": contract["patch"]["sha256"],
    }
    for key, value in expected_provenance.items():
        if provenance.get(key) != value:
            raise ValueError(f"provenance field {key} differs from contract")
    if (evidence_dir / "llama-cpp-commit.txt").read_text(encoding="utf-8").strip() != upstream["llama_cpp_commit"]:
        raise ValueError("checked-out llama.cpp commit differs from contract")

    patch_sha256 = sha256_file(patch_path)
    if patch_sha256 != contract["patch"]["sha256"]:
        raise ValueError("local patch checksum differs from contract")
    if sha256_file(evidence_dir / "applied.patch") != patch_sha256:
        raise ValueError("applied source diff differs from the frozen patch")
    if patch_sha256 not in (evidence_dir / "patch-sha256.txt").read_text(encoding="utf-8"):
        raise ValueError("artifact lacks the frozen patch checksum")

    exits = {
        "unpatched_build": read_exit(evidence_dir / "build-unpatched-exit.txt"),
        "patched_build": read_exit(evidence_dir / "build-patched-exit.txt"),
        "functional_test": read_exit(evidence_dir / "ctest-exit.txt"),
        "benchmark": read_exit(evidence_dir / "benchmark-exit.txt"),
    }
    if exits["unpatched_build"] == 0:
        raise ValueError("unpatched source unexpectedly built successfully")
    if any(exits[key] != 0 for key in ("patched_build", "functional_test", "benchmark")):
        raise ValueError("a patched validation step failed")
    if any(value != "success" for value in provenance.get("step_outcomes", {}).values()):
        raise ValueError("workflow step outcomes are incomplete")

    validate_failure_signature(
        (evidence_dir / "configure-unpatched.log").read_text(encoding="utf-8"),
        (evidence_dir / "build-unpatched.log").read_text(encoding="utf-8"),
    )
    patched_build_log = (evidence_dir / "build-patched.log").read_text(
        encoding="utf-8"
    )
    if "kleidiai_download-src" in patched_build_log and "sve_dotprod" in patched_build_log:
        raise ValueError("patched build still contains KleidiAI SVE source evidence")
    test_log = (evidence_dir / "ctest.log").read_text(encoding="utf-8")
    if "100% tests passed, 0 tests failed out of 1" not in test_log:
        raise ValueError("pinned upstream functional test evidence is missing")

    model_record = (evidence_dir / "model.txt").read_text(encoding="utf-8")
    model_sha256 = contract["benchmark"]["model_sha256"]
    if model_sha256 not in model_record:
        raise ValueError("model checksum evidence differs from contract")
    benchmark_stdout = (evidence_dir / "benchmark.stdout.log").read_text(
        encoding="utf-8"
    )
    if "CPU_KLEIDIAI model buffer size" not in benchmark_stdout:
        raise ValueError("benchmark lacks runtime KleidiAI buffer evidence")
    benchmark = validate_benchmark(
        load_object(evidence_dir / "benchmark.json"), contract["benchmark"]
    )
    process = parse_time_output(
        (evidence_dir / "time.log").read_text(encoding="utf-8")
    )
    if process["exit_status"] != 0 or process["elapsed"] is None:
        raise ValueError("benchmark process evidence is invalid")
    process["elapsed_seconds"] = elapsed_seconds(process["elapsed"])

    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E6a",
        "status": "valid_source_correctness_fix",
        "source": {
            "artifact_name": (
                f"e6a-native-feature-fix-{run_id}-"
                f"{provenance['github_run_attempt']}"
            ),
            "github_run_url": (
                f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}"
            ),
            "artifact_retention_days": 90,
        },
        "contract": contract,
        "provenance": provenance,
        "platform": {
            **parse_lscpu((evidence_dir / "lscpu.txt").read_text(encoding="utf-8")),
            "uname": (evidence_dir / "uname.txt").read_text(encoding="utf-8").strip(),
        },
        "validation": {
            "unpatched_exit_status": exits["unpatched_build"],
            "unpatched_failure_reproduced": True,
            "applied_patch_matches_frozen_sha256": True,
            "patched_clean_build_passed": True,
            "invalid_sve_sources_excluded": True,
            "functional_test_passed": True,
            "real_model_inference_passed": True,
            "kleidiai_runtime_buffer_observed": True,
            "speedup_claim_allowed": False,
            "quality_claim_allowed": False,
        },
        "benchmark": {**benchmark, "process": process},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    manifest = build_manifest(
        arguments.evidence_dir, arguments.contract, arguments.patch
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
