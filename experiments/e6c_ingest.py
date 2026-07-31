#!/usr/bin/env python3
"""Validate E6c reasoning-budget fix evidence and derive its native result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e3_score import build_summary, extract_answer, load_object, sha256_file
    from experiments.e3b_ingest import normalize_quality_sources
    from experiments.e3d_ingest import validate_runtime_proof
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e3_score import build_summary, extract_answer, load_object, sha256_file
    from e3b_ingest import normalize_quality_sources
    from e3d_ingest import validate_runtime_proof


VARIANT = "qwen35_q4_budget0_patched"


def read_status(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError as error:
        raise ValueError(f"{path} does not contain an exit status") from error


def read_digest(path: Path) -> str:
    fields = path.read_text(encoding="utf-8").split(maxsplit=1)
    if len(fields) != 2 or not re.fullmatch(r"[0-9a-f]{64}", fields[0]):
        raise ValueError(f"{path} does not contain checksum evidence")
    return fields[0]


def validate_inputs(
    evidence_dir: Path, contract_path: Path, models_path: Path, tasks_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = load_object(contract_path)
    models = load_object(models_path)
    provenance = load_object(evidence_dir / "provenance.json")
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E6c":
        raise ValueError("contract does not identify schema-1 E6c")
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E6c contract")
    if load_object(evidence_dir / "models-manifest.json") != models:
        raise ValueError("artifact model manifest differs from frozen E6c models")
    if load_object(evidence_dir / "tasks-manifest.json") != load_object(tasks_path):
        raise ValueError("artifact task manifest differs from frozen E6c tasks")
    if sha256_file(tasks_path) != contract["quality"]["tasks_sha256"]:
        raise ValueError("E6c task checksum differs from the contract")
    if set(models.get("variants", {})) != {VARIANT}:
        raise ValueError("E6c requires the one patched zero-budget variant")
    shared = models.get("shared_model", {})
    if (
        shared.get("license") != "Apache-2.0"
        or models.get("source_model", {}).get("license") != "Apache-2.0"
        or models.get("quantization_repository", {}).get("license") != "Apache-2.0"
    ):
        raise ValueError("E6c model provenance or license is invalid")
    expected_provenance = {
        "schema_version": 1,
        "experiment_id": "E6c",
        "llama_cpp_commit": contract["upstream"]["llama_cpp_commit"],
        "llama_cpp_tag": contract["upstream"]["llama_cpp_tag"],
        "kleidiai_release": contract["upstream"]["kleidiai_release"],
        "kleidiai_archive_md5": contract["upstream"]["kleidiai_archive_md5"],
        "patch_sha256": contract["patch"]["sha256"],
        "source_model_revision": models["source_model"]["revision"],
        "quantization_revision": models["quantization_repository"]["revision"],
    }
    for key, expected in expected_provenance.items():
        if provenance.get(key) != expected:
            raise ValueError(f"provenance {key} differs from E6c contract")
    for key in ("github_run_id", "github_run_attempt", "git_commit"):
        if not isinstance(provenance.get(key), str) or not provenance[key]:
            raise ValueError(f"provenance lacks {key}")
    return contract, models, provenance


def validate_patch(evidence_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    patch = contract["patch"]
    artifact_patch = evidence_dir / "patch.patch"
    if sha256_file(artifact_patch) != patch["sha256"]:
        raise ValueError("artifact patch checksum differs from E6c contract")
    if (evidence_dir / "applied.patch").read_bytes() != artifact_patch.read_bytes():
        raise ValueError("applied E6c diff differs from the frozen patch")
    changed = (evidence_dir / "changed-files.txt").read_text().splitlines()
    if changed != sorted([patch["source_target"], patch["test_target"]]):
        raise ValueError("E6c patched source tree has an unexpected change set")
    digest_paths = {
        "source_sha256_before": "source-before-sha256.txt",
        "source_sha256_after": "source-after-sha256.txt",
        "test_sha256_before": "test-before-sha256.txt",
        "test_sha256_after": "test-after-sha256.txt",
    }
    for key, path in digest_paths.items():
        if read_digest(evidence_dir / path) != patch[key]:
            raise ValueError(f"E6c {key} evidence differs from the contract")
    baseline_status = read_status(evidence_dir / "baseline-test-exit.txt")
    baseline_log = (evidence_dir / "baseline-test.stderr.log").read_text()
    if (
        baseline_status == 0
        or contract["regression"]["baseline_failure_pattern"] not in baseline_log
    ):
        raise ValueError("E6c baseline did not reproduce the forcing-state failure")
    patched_status = read_status(evidence_dir / "patched-test-exit.txt")
    patched_log = (evidence_dir / "patched-test.stdout.log").read_text()
    if (
        patched_status != contract["regression"]["patched_expected_exit"]
        or contract["regression"]["patched_success_pattern"] not in patched_log
    ):
        raise ValueError("E6c patched upstream test did not pass")
    return {
        "path": patch["path"],
        "sha256": patch["sha256"],
        "changed_files": changed,
        "baseline_test_exit": baseline_status,
        "patched_test_exit": patched_status,
    }


def validate_build(evidence_dir: Path) -> None:
    if read_status(evidence_dir / "build-exit.txt") != 0:
        raise ValueError("E6c patched build failed")
    configure = (evidence_dir / "configure.log").read_text(encoding="utf-8")
    if "Using KleidiAI optimized kernels if applicable" not in configure:
        raise ValueError("E6c configure log does not prove KleidiAI enabled")
    cache = (evidence_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    for setting in (
        "GGML_CPU_KLEIDIAI:BOOL=ON",
        "GGML_NATIVE:BOOL=ON",
        "LLAMA_BUILD_SERVER:BOOL=ON",
        "LLAMA_BUILD_TESTS:BOOL=ON",
    ):
        if setting not in cache:
            raise ValueError(f"E6c build cache lacks {setting}")
    if not re.search(r"^LLAMA_CURL:(?:BOOL|UNINITIALIZED)=OFF$", cache, re.MULTILINE):
        raise ValueError("E6c build cache lacks LLAMA_CURL=OFF")


def validate_model(evidence_dir: Path, model: dict[str, Any]) -> int:
    files = model.get("files")
    if not isinstance(files, list) or len(files) != 1:
        raise ValueError("E6c requires one shared model file")
    item = files[0]
    expected_size = f"{item['path']} {item['size_bytes']} bytes"
    if (evidence_dir / "model-files.txt").read_text().splitlines() != [expected_size]:
        raise ValueError("E6c model size evidence differs")
    lines = (evidence_dir / "model-sha256.txt").read_text().splitlines()
    fields = lines[0].split(maxsplit=1) if len(lines) == 1 else []
    if (
        len(fields) != 2
        or fields[0] != item["sha256"]
        or not fields[1].endswith(f"/{item['path']}")
    ):
        raise ValueError("E6c model checksum evidence differs")
    return int(item["size_bytes"])


def build_manifest(
    evidence_dir: Path, contract_path: Path, models_path: Path, tasks_path: Path
) -> dict[str, Any]:
    contract, models, provenance = validate_inputs(
        evidence_dir, contract_path, models_path, tasks_path
    )
    patch = validate_patch(evidence_dir, contract)
    validate_build(evidence_dir)
    model = models["shared_model"]
    package_size = validate_model(evidence_dir, model)
    variant_dir = evidence_dir / "variants" / VARIANT
    validate_runtime_proof(
        variant_dir,
        f"/{model['entrypoint']}",
        contract["upstream"]["llama_cpp_commit"][:9],
        contract["configuration"]["threads"],
    )
    runtime_log = "\n".join(
        (variant_dir / name).read_text(encoding="utf-8")
        for name in (
            "runtime-proof.stderr.log",
            "server.core.log",
            "server.stdout.log",
            "server.stderr.log",
        )
    )
    runtime_evidence = sorted(
        pattern for pattern in model["runtime_buffer_patterns"] if pattern in runtime_log
    )
    if not runtime_evidence:
        raise ValueError("E6c lacks KleidiAI runtime buffer proof")
    readiness = load_object(variant_dir / "readiness.json")
    if readiness.get("status") != "ok" or float(readiness.get("ready_ms", -1)) < 0:
        raise ValueError("E6c lacks valid server readiness evidence")
    process = parse_time_output((variant_dir / "server.time.log").read_text())
    if process["exit_status"] not in {0, 130, 143} or process["maximum_rss_kib"] is None:
        raise ValueError("E6c server process evidence is invalid")

    quality = build_summary(models_path, tasks_path, evidence_dir)
    quality["experiment_id"] = "E6c"
    normalize_quality_sources(quality, [VARIANT])
    if (
        quality["acceptance_policy"]["repetitions"]
        != contract["quality"]["repetitions"]
        or quality["acceptance_policy"]["prediction_parser"]
        != contract["quality"]["prediction_parser"]
        or quality["acceptance_policy"]["absolute_accuracy_floor"]
        != contract["quality"]["reference_accuracy_floor"]
    ):
        raise ValueError("E6c quality scorer policy differs from the contract")
    scored = quality["variants"][VARIANT]
    config = contract["configuration"]
    raw_runs = [
        load_object(variant_dir / f"quality-repeat-{repetition}.json")
        for repetition in range(1, contract["quality"]["repetitions"] + 1)
    ]
    reasoning_characters: list[float] = []
    generated_tokens: list[float] = []
    encode_ms: list[float] = []
    decode_ms: list[float] = []
    http_ms: list[float] = []
    final_answers = 0
    for run in raw_runs:
        if (
            run.get("framework") != "llama.cpp"
            or run.get("transport") != "OpenAI-compatible HTTP"
            or run.get("threads") != config["threads"]
            or run.get("context_size") != config["context"]
            or run.get("reasoning_budget_tokens") != config["reasoning_budget_tokens"]
            or run.get("max_output_tokens") != config["max_output_tokens"]
            or run.get("chat_template_mode") != config["chat_template_mode"]
            or run.get("reasoning_format") != config["reasoning_format"]
            or run.get("temperature") != config["temperature"]
            or run.get("seed") != config["seed"]
            or float(run.get("model_load_ms", -1)) != float(readiness["ready_ms"])
            or not str(run.get("model_path", "")).endswith(f"/{model['entrypoint']}")
        ):
            raise ValueError("E6c quality runtime parameters differ")
        cases = run.get("cases")
        if not isinstance(cases, list) or len(cases) != contract["quality"]["task_count"]:
            raise ValueError("E6c quality run lacks the frozen task count")
        for case in cases:
            reasoning = case.get("reasoning_content")
            characters = case.get("reasoning_characters")
            tokens = case.get("generated_tokens")
            response = case.get("response")
            if (
                reasoning not in (None, "")
                or characters != 0
                or not isinstance(tokens, int)
                or tokens <= 0
                or tokens > config["max_output_tokens"]
                or not isinstance(response, str)
                or extract_answer(response) is None
                or case.get("termination_reason") != "stop"
            ):
                raise ValueError("E6c did not enforce a clean immediate reasoning end")
            final_answers += 1
            reasoning_characters.append(float(characters))
            generated_tokens.append(float(tokens))
            encode_ms.append(float(case["encode_ms"]))
            decode_ms.append(float(case["decode_ms"]))
            http_ms.append(float(case["http_ms"]))
    if not scored["predictions_stable"]:
        raise ValueError("E6c patched predictions are not stable")

    application = {
        "display_name": models["variants"][VARIANT]["display_name"],
        "reasoning_budget_tokens": 0,
        "package_size_bytes": package_size,
        "minimum_accuracy": scored["minimum_accuracy"],
        "quality_eligible": scored["quality_eligible"],
        "model_load_ms": summarize([float(readiness["ready_ms"])]),
        "same_text_encode_ms": summarize(encode_ms),
        "same_text_decode_ms": summarize(decode_ms),
        "same_text_total_ms": summarize(
            [left + right for left, right in zip(encode_ms, decode_ms)]
        ),
        "http_round_trip_ms": summarize(http_ms),
        "reasoning_characters": summarize(reasoning_characters),
        "generated_tokens": summarize(generated_tokens),
        "final_answer_count": final_answers,
        "quality_process": {
            "maximum_rss_kib": summarize([float(process["maximum_rss_kib"])]),
            "process": process,
        },
        "runtime_buffer_evidence": runtime_evidence,
    }
    return {
        "schema_version": 1,
        "experiment_id": "E6c",
        "status": "valid_correctness_fix",
        "source": {
            "github_run_url": (
                "https://github.com/Arshgill01/Arm/actions/runs/"
                f"{provenance['github_run_id']}"
            ),
            "artifact_name": (
                "e6c-reasoning-budget-fix-"
                f"{provenance['github_run_id']}-{provenance['github_run_attempt']}"
            ),
            "artifact_retention_days": 90,
        },
        "platform": {
            "uname": (evidence_dir / "uname.txt").read_text().strip(),
            "lscpu": parse_lscpu((evidence_dir / "lscpu.txt").read_text()),
        },
        "provenance": provenance,
        "patch": patch,
        "quality": quality,
        "application": {VARIANT: application},
        "validation": {
            "baseline_regression_reproduced": True,
            "patched_upstream_test_passed": True,
            "changed_files_exact": True,
            "kleidiai_runtime_buffer_proven": True,
            "zero_reasoning_characters": True,
            "standalone_final_answer_for_every_request": True,
            "predictions_stable": True,
            "quality_reference_floor_met": scored["absolute_floor_met"],
            "patch_acceptance_independent_of_reference_accuracy": True,
        },
        "claim_boundary": contract["claim_boundary"],
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
