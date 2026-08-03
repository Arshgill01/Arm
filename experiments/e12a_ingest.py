#!/usr/bin/env python3
"""Validate native E12a importance-matrix evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure


ARTIFACT_INPUTS = {
    "application_tasks": "application-tasks.json",
    "sample_generator": "sample-generator.py",
    "sample_map": "sample-map.json",
    "corpus_generator": "corpus-generator.py",
    "task_utils": "task-utils.py",
    "requirements": "requirements.txt",
}


def validate_metadata(
    metadata_dump: dict[str, Any], plan: dict[str, Any], corpus_path: str
) -> dict[str, Any]:
    metadata = metadata_dump.get("metadata")
    tensors = metadata_dump.get("tensors")
    if not isinstance(metadata, dict) or not isinstance(tensors, dict):
        raise ValueError("E12a GGUF dump is incomplete")

    def value(name: str) -> Any:
        field = metadata.get(name)
        return field.get("value") if isinstance(field, dict) else None

    datasets = value("imatrix.datasets")
    chunk_count = value("imatrix.chunk_count")
    chunk_size = value("imatrix.chunk_size")
    if (
        value("general.type") != "imatrix"
        or datasets != [corpus_path]
        or chunk_count != plan["imatrix"]["processed_chunks"]
        or chunk_size != plan["imatrix"]["tokens_per_chunk"]
    ):
        raise ValueError("E12a GGUF metadata differs from the frozen run")
    sums = {
        name.removesuffix(".in_sum2") for name in tensors if name.endswith(".in_sum2")
    }
    counts = {
        name.removesuffix(".counts") for name in tensors if name.endswith(".counts")
    }
    if sums != counts or len(sums) < plan["acceptance"]["minimum_imatrix_entries"]:
        raise ValueError("E12a GGUF activation entry pairs differ")
    return {
        "general_type": value("general.type"),
        "datasets": datasets,
        "chunk_count": chunk_count,
        "chunk_size": chunk_size,
        "entries": len(sums),
        "gguf_tensors": len(tensors),
    }


def validate_command(
    command: dict[str, Any],
    plan: dict[str, Any],
    *,
    model_path: str,
    corpus_path: str,
    imatrix_path: str,
) -> list[str]:
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not argv[0].endswith("/llama-imatrix"):
        raise ValueError("E12a imatrix command is incomplete")
    replacements = {
        "MODEL_PATH": model_path,
        "CORPUS_PATH": corpus_path,
        "IMATRIX_PATH": imatrix_path,
    }
    expected = [argv[0]] + [
        replacements.get(argument, argument)
        for argument in plan["imatrix"]["argv_after_binary"]
    ]
    if argv != expected:
        raise ValueError("E12a imatrix command differs from the frozen plan")
    return argv


def build_manifest(evidence: Path, plan_path: Path, root: Path) -> dict[str, Any]:
    plan = load_object(plan_path)
    if plan.get("schema_version") != 1 or plan.get("experiment_id") != "E12a":
        raise ValueError("plan does not identify E12a")
    if load_object(evidence / "contract.json") != plan:
        raise ValueError("artifact plan differs from frozen E12a")
    for key, artifact_name in ARTIFACT_INPUTS.items():
        source = root / plan["inputs"][f"{key}_path"]
        expected = plan["inputs"][f"{key}_sha256"]
        if (
            sha256_file(source) != expected
            or sha256_file(evidence / artifact_name) != expected
        ):
            raise ValueError(f"E12a input hash differs for {key}")
    for key in ("ingest", "test"):
        if (
            sha256_file(root / plan["inputs"][f"{key}_path"])
            != plan["inputs"][f"{key}_sha256"]
        ):
            raise ValueError(f"E12a implementation hash differs for {key}")

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != plan["acceptance"]["required_architecture"]:
        raise ValueError("E12a evidence is not native Arm64")
    if load_object(evidence / "source.json") != plan["source"]:
        raise ValueError("E12a source identity differs")
    if (
        sha256_file(evidence / "source-diff.patch")
        != plan["source"]["source_diff_sha256"]
    ):
        raise ValueError("E12a source diff differs")
    configure = load_object(evidence / "build/configure-command.json")
    if configure.get("cmake_arguments") != plan["build"]["cmake_arguments"]:
        raise ValueError("E12a configure command differs")
    cache_lines = (
        (evidence / "build/CMakeCache.txt").read_text(errors="replace").splitlines()
    )
    for argument in plan["build"]["cmake_arguments"]:
        if argument.startswith("-D") and "=" in argument:
            name, expected = argument[2:].split("=", 1)
            if expected in {"ON", "OFF"} and not any(
                line.startswith(f"{name}:") and line.endswith(f"={expected}")
                for line in cache_lines
            ):
                raise ValueError(f"E12a CMake cache differs for {name}")
    build_process = parse_time_output((evidence / "build/build-time.log").read_text())
    if build_process["exit_status"] != 0 or build_process["maximum_rss_kib"] is None:
        raise ValueError("E12a build process evidence differs")
    runtime_closures = {}
    for tool in plan["build"]["targets"]:
        closure = validate_runtime_closure(
            evidence / f"build/{tool}-runtime-closure.json"
        )
        dependencies = sorted(
            {
                Path(item["resolved_path"]).name
                for item in closure["runtime_dependencies"]
            }
        )
        if set(plan["build"]["forbidden_dynamic_dependency_basenames"]).intersection(
            dependencies
        ):
            raise ValueError(f"E12a {tool} runtime retains a forbidden dependency")
        runtime_closures[tool] = {
            "closure": closure,
            "dynamic_dependency_basenames": dependencies,
        }

    corpus = evidence / "calibration.txt"
    corpus_manifest = load_object(evidence / "corpus-manifest.json")
    expected_corpus = plan["calibration"]["expected_corpus"]
    if any(corpus_manifest.get(key) != value for key, value in expected_corpus.items()):
        raise ValueError("E12a corpus manifest differs")
    if (
        corpus.stat().st_size != expected_corpus["corpus_bytes"]
        or sha256_file(corpus) != expected_corpus["corpus_sha256"]
    ):
        raise ValueError("E12a retained corpus differs")
    if load_object(evidence / "generated-sample-map.json") != load_object(
        evidence / "sample-map.json"
    ):
        raise ValueError("E12a generated sample map differs")

    model_path = (evidence / "model-path.txt").read_text().strip()
    model_line = (evidence / "model-sha256.txt").read_text().strip().split()
    if (
        len(model_line) != 2
        or model_line[0] != plan["model"]["sha256"]
        or model_line[1] != model_path
    ):
        raise ValueError("E12a BF16 model identity differs")
    command = validate_command(
        load_object(evidence / "imatrix-command.json"),
        plan,
        model_path=model_path,
        corpus_path=str(corpus),
        imatrix_path=str(evidence / "imatrix.gguf"),
    )
    process = parse_time_output((evidence / "imatrix-time.log").read_text())
    if (
        process["exit_status"] != plan["acceptance"]["process_exit_status"]
        or process["maximum_rss_kib"] is None
    ):
        raise ValueError("E12a imatrix process evidence differs")
    imatrix_path = evidence / "imatrix.gguf"
    imatrix_sha = sha256_file(imatrix_path)
    imatrix_size = imatrix_path.stat().st_size
    retained_line = (evidence / "imatrix-sha256.txt").read_text().strip().split()
    if len(retained_line) != 2 or retained_line[0] != imatrix_sha:
        raise ValueError("E12a imatrix digest evidence differs")
    metadata = validate_metadata(
        load_object(evidence / "imatrix-metadata.json"), plan, str(corpus)
    )
    statistics = (evidence / "imatrix-statistics.log").read_text(errors="replace")
    match = re.search(r"Computing statistics for .* \((\d+) tensors\)", statistics)
    if not match or int(match.group(1)) != metadata["entries"]:
        raise ValueError("E12a statistics entry count differs")
    generation_log = (evidence / "imatrix.log").read_text(errors="replace")
    if (
        f"computing over {plan['imatrix']['processed_chunks']} chunks"
        not in generation_log
    ):
        raise ValueError("E12a generation log lacks the frozen chunk count")
    return {
        "schema_version": 1,
        "experiment_id": "E12a",
        "status": "valid_application_conditioned_imatrix",
        "contract_sha256": sha256_file(plan_path),
        "platform": platform,
        "source": plan["source"],
        "build": {
            "configure_command": configure,
            "process": build_process,
            "imatrix_version": (evidence / "build/imatrix-version.txt")
            .read_text(errors="replace")
            .strip(),
            "quantize_sha256": (evidence / "build/quantize-sha256.txt")
            .read_text(errors="replace")
            .strip(),
            "runtime_closures": runtime_closures,
        },
        "model": plan["model"],
        "corpus": expected_corpus,
        "command": command,
        "process": process,
        "imatrix": {
            "path": "imatrix.gguf",
            "sha256": imatrix_sha,
            "size_bytes": imatrix_size,
            "metadata": metadata,
            "statistics_sha256": sha256_file(evidence / "imatrix-statistics.log"),
        },
        "validation": {
            "native_arm64": True,
            "exact_source_build_model": True,
            "deterministic_frozen_corpus": True,
            "holdouts_excluded": True,
            "complete_chunk_count": True,
            "gguf_metadata_valid": True,
            "statistics_retained": True,
            "model_promoted": False,
        },
        "decision": plan["decision"],
        "claim_boundary": plan["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.evidence_dir, args.plan, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {"status": manifest["status"], "imatrix": manifest["imatrix"]},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
