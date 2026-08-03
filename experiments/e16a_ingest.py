#!/usr/bin/env python3
"""Validate and summarize E16a Arm repack-sidecar feasibility evidence."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e9a_ingest import expected_server_argv
    from experiments.e16a_freeze import INPUT_PATHS
    from experiments.e16a_sidecar import INVENTORY_FIELDS, parse_runtime
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from e7a_ingest import validate_runtime_closure
    from e9a_ingest import expected_server_argv
    from e16a_freeze import INPUT_PATHS
    from e16a_sidecar import INVENTORY_FIELDS, parse_runtime


ARTIFACT_INPUTS = {
    "manifest": "selected-manifest.json",
    "policy": "deployment-policy.json",
    "models": "models-manifest.json",
    "runtime_contract": "runtime-contract.json",
    "tasks": "tasks-manifest.json",
}


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E16a":
        raise ValueError("contract does not identify E16a")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E16a")
    for name, relative in INPUT_PATHS.items():
        if sha256_file(root / relative) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E16a frozen input differs for {name}")
    for name, artifact_name in ARTIFACT_INPUTS.items():
        if (
            sha256_file(evidence / artifact_name)
            != contract["inputs"][f"{name}_sha256"]
        ):
            raise ValueError(f"E16a artifact input differs for {name}")
    return contract


def validate_source_build(evidence: Path, contract: dict[str, Any]) -> dict[str, Any]:
    source = load_object(evidence / "source.json")
    expected_patches = [
        Path(item["path"]).name for item in contract["source"]["patches"]
    ]
    if (
        source.get("commit") != contract["source"]["commit"]
        or source.get("tag") != contract["source"]["tag"]
        or source.get("patches_applied") != expected_patches
        or sha256_file(evidence / "source-diff.patch")
        != contract["source"]["aggregate_diff_sha256"]
        or (evidence / "patched-files.txt").read_text(encoding="utf-8").splitlines()
        != contract["source"]["changed_files"]
    ):
        raise ValueError("E16a source proof differs")
    for patch in contract["source"]["patches"]:
        if (
            sha256_file(evidence / "patches" / Path(patch["path"]).name)
            != patch["sha256"]
        ):
            raise ValueError("E16a retained patch differs")

    build = evidence / "build"
    configure = load_object(build / "configure-command.json")
    if configure.get("cmake_arguments") != contract["build"]["cmake_arguments"]:
        raise ValueError("E16a configure command differs")
    cache_lines = (build / "CMakeCache.txt").read_text(errors="replace").splitlines()
    for argument in contract["build"]["cmake_arguments"]:
        if not argument.startswith("-D") or "=" not in argument:
            continue
        name, value = argument[2:].split("=", 1)
        if value in {"ON", "OFF"} and not any(
            line.startswith(f"{name}:") and line.endswith(f"={value}")
            for line in cache_lines
        ):
            raise ValueError(f"E16a CMake cache differs for {name}")
    version = (build / "server-version.txt").read_text(errors="replace").strip()
    if contract["source"]["commit"][:9] not in version:
        raise ValueError("E16a server version differs")
    closure = validate_runtime_closure(build / "runtime-closure.json")
    dependencies = sorted(
        {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
    )
    if set(contract["build"]["forbidden_dynamic_dependency_basenames"]).intersection(
        dependencies
    ):
        raise ValueError("E16a runtime closure contains forbidden dependencies")
    return {
        "source": source,
        "configure_command": configure,
        "server_version": version,
        "runtime_closure": closure,
        "dynamic_dependency_basenames": dependencies,
    }


def read_inventory(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != INVENTORY_FIELDS:
            raise ValueError("E16a retained inventory header differs")
        rows = list(reader)
    if not rows:
        raise ValueError("E16a retained inventory is empty")
    return rows


def inventory_matches_header(
    rows: list[dict[str, str]], tensors: list[dict[str, Any]]
) -> bool:
    if len(rows) != len(tensors):
        return False
    indexed = {item["tensor"]: item for item in tensors}
    for row in rows:
        tensor = indexed.get(row["tensor"])
        if tensor is None:
            return False
        for name in ("file", "type", "parameter_type"):
            if tensor[name] != row[name]:
                return False
        for name in (
            "ne0",
            "ne1",
            "ne2",
            "ne3",
            "bytes",
            "buffer_offset",
            "columns",
            "interleave",
        ):
            if tensor[name] != int(row[name]):
                return False
    return True


def validate_recipe(
    recipe: dict[str, Any], contract: dict[str, Any], repetition: int
) -> None:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E16a"
        or recipe.get("repetition") != repetition
        or recipe.get("source") != contract["source"]
        or recipe.get("build") != contract["build"]
        or recipe.get("service") != contract["service"]
        or not isinstance(server, str)
        or not server.endswith("/bin/llama-server")
        or contract["source"]["commit"][:9] not in recipe.get("server_version", "")
        or not isinstance(model_path, str)
        or not model_path.endswith(".gguf")
        or model.get("sha256") != contract["selected"]["model_sha256"]
        or model.get("size_bytes") != contract["selected"]["model_size_bytes"]
        or recipe.get("runtime_environment")
        != {"GGML_CPU_REPACK_DUMP_DIR": "fresh generated scratch directory"}
    ):
        raise ValueError("E16a service recipe differs")
    expected = expected_server_argv(
        server,
        model_path,
        candidate=contract["selected"]["candidate"],
        profile_name="e7c_final",
    )
    expected.extend(
        ["--log-verbosity", str(contract["mechanism"]["proof_log_verbosity"])]
    )
    if recipe.get("argv") != expected:
        raise ValueError("E16a server argv differs")


def validate_cell(
    cell_dir: Path,
    *,
    contract: dict[str, Any],
    repetition: int,
    identity: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> dict[str, Any]:
    validate_recipe(load_object(cell_dir / "recipe.json"), contract, repetition)
    probe = validate_probe(
        load_object(cell_dir / "probe.json"),
        configuration="persistent_prepack_feasibility",
        repetition=repetition,
        config=contract["service"],
        contract=contract,
        tasks=tasks,
        references=references,
        require_selected_quality=False,
    )
    shell_exit = int((cell_dir / "server-shell-exit.txt").read_text().strip())
    process = parse_time_output(
        (cell_dir / "server-time.log").read_text(encoding="utf-8")
    )
    if shell_exit not in contract["acceptance"]["accepted_server_shell_exit_statuses"]:
        raise ValueError("E16a server exit status differs")
    index = load_object(cell_dir / "sidecar-index.json")
    header = index.get("header", {})
    runtime = parse_runtime(cell_dir / "runtime.tsv")
    inventory = read_inventory(cell_dir / "inventory.tsv")
    verification = load_object(cell_dir / "verification.json")
    cleanup = load_object(cell_dir / "cleanup.json")
    log = (cell_dir / "server.stderr.log").read_text(errors="replace")
    if (
        header.get("format") != "pareto64-arm-repack-sidecar"
        or header.get("data_offset")
        != contract["mechanism"]["sidecar_data_offset_bytes"]
        or header.get("binding") != identity
        or index.get("runtime_capture") != runtime
        or index.get("sidecar_size_bytes")
        != header.get("data_offset", 0) + header.get("arena_size_bytes", -1)
        or not re.fullmatch(r"[0-9a-f]{64}", str(index.get("sidecar_sha256", "")))
        or not inventory_matches_header(inventory, header.get("tensors", []))
        or verification.get("sidecar_sha256") != index.get("sidecar_sha256")
        or verification.get("tensor_count") != header.get("tensor_count")
        or "CPU_REPACK model buffer size" not in log
    ):
        raise ValueError("E16a sidecar mechanism evidence differs")
    if any(path.suffix == ".bin" for path in cell_dir.rglob("*")):
        raise ValueError("E16a artifact retained a generated raw binary")
    packed_bytes = header["packed_tensor_bytes"]
    expected_deleted_bytes = packed_bytes + index["sidecar_size_bytes"]
    cleanup_valid = cleanup == {
        "deleted_raw_tensor_bytes": packed_bytes,
        "deleted_raw_tensor_count": header["tensor_count"],
        "deleted_sidecar_bytes": index["sidecar_size_bytes"],
        "generated_binary_bytes_deleted": expected_deleted_bytes,
        "generated_binary_cleanup_complete": True,
    }
    base = runtime["buffer_base"]
    absolute_base_excluded = base not in json.dumps(header, sort_keys=True)
    return {
        "repetition": repetition,
        "probe": probe,
        "process": process,
        "server_shell_exit_status": shell_exit,
        "sidecar_index": index,
        "inventory": inventory,
        "runtime": runtime,
        "verification": verification,
        "cleanup": cleanup,
        "cleanup_valid": cleanup_valid,
        "absolute_buffer_base_excluded_from_sidecar": absolute_base_excluded,
        "prediction_map": {
            case["id"]: case["predicted"]
            for case in load_object(cell_dir / "probe.json")["cases"]
        },
    }


def metadata_without_hashes(index: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in tensor.items() if key != "sha256"}
        for tensor in index["header"]["tensors"]
    ]


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    platform_info = parse_lscpu((evidence / "lscpu.txt").read_text())
    source_build = validate_source_build(evidence, contract)
    identity = load_object(evidence / "sidecar-identity.json")
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["manifest_path"]),
        contract["selected"]["candidate"],
    )
    cells = [
        validate_cell(
            evidence / "cells" / f"{repetition:02d}-r{repetition}",
            contract=contract,
            repetition=repetition,
            identity=identity,
            tasks=tasks,
            references=references,
        )
        for repetition in contract["execution"]["order"]
    ]
    indexes = [cell["sidecar_index"] for cell in cells]
    headers = [index["header"] for index in indexes]
    tensor_hashes = [
        [tensor["sha256"] for tensor in header["tensors"]] for header in headers
    ]
    predictions = [cell["prediction_map"] for cell in cells]
    required_features = set(contract["acceptance"]["required_common_cpu_features"])
    observed_features = set(identity.get("cpu", {}).get("common_features", []))
    gates = {
        "native_architecture": platform_info["architecture"]
        == contract["acceptance"]["required_architecture"]
        == identity.get("cpu", {}).get("architecture"),
        "required_cpu_features": required_features <= observed_features,
        "tensor_count": all(
            header["tensor_count"] >= contract["acceptance"]["minimum_tensor_count"]
            for header in headers
        ),
        "packed_buffer_coverage": all(
            header["coverage_fraction"]
            >= contract["acceptance"]["minimum_packed_buffer_coverage_fraction"]
            for header in headers
        ),
        "cpu_identity": all(header["binding"] == identity for header in headers),
        "tensor_metadata": metadata_without_hashes(indexes[0])
        == metadata_without_hashes(indexes[1]),
        "tensor_bytes": tensor_hashes[0] == tensor_hashes[1],
        "complete_sidecar": indexes[0]["sidecar_sha256"]
        == indexes[1]["sidecar_sha256"],
        "sidecar_verification": all(
            cell["verification"].get("status")
            == contract["acceptance"]["sidecar_verification_status"]
            for cell in cells
        ),
        "exact_quality": all(
            cell["probe"]["correct"] == contract["acceptance"]["correct_per_repetition"]
            and cell["probe"]["reference_prediction_mismatches"]
            == contract["acceptance"]["reference_prediction_mismatches"]
            and cell["probe"]["failures"] == contract["acceptance"]["request_failures"]
            for cell in cells
        ),
        "stable_predictions": predictions[0] == predictions[1],
        "absolute_address_excluded": all(
            cell["absolute_buffer_base_excluded_from_sidecar"] for cell in cells
        ),
        "bounded_cleanup": all(cell["cleanup_valid"] for cell in cells),
    }
    eligible = all(gates.values())
    return {
        "schema_version": 1,
        "experiment_id": "E16a",
        "contract_sha256": sha256_file(contract_path),
        "status": (
            "valid_loader_feasibility"
            if eligible
            else "valid_loader_feasibility_rejected"
        ),
        "loader_successor_authorized": eligible,
        "gates": gates,
        "failed_gates": sorted(name for name, passed in gates.items() if not passed),
        "platform": platform_info,
        "source_build": source_build,
        "sidecar_identity": identity,
        "sidecar": {
            "sha256_per_repetition": [index["sidecar_sha256"] for index in indexes],
            "size_bytes_per_repetition": [
                index["sidecar_size_bytes"] for index in indexes
            ],
            "tensor_count_per_repetition": [
                header["tensor_count"] for header in headers
            ],
            "packed_tensor_bytes_per_repetition": [
                header["packed_tensor_bytes"] for header in headers
            ],
            "arena_size_bytes_per_repetition": [
                header["arena_size_bytes"] for header in headers
            ],
            "coverage_fraction_per_repetition": [
                header["coverage_fraction"] for header in headers
            ],
            "buffer_base_per_repetition": [
                cell["runtime"]["buffer_base"] for cell in cells
            ],
            "absolute_buffer_base_serialized": False,
        },
        "quality": {
            "correct_per_repetition": [cell["probe"]["correct"] for cell in cells],
            "failures_per_repetition": [cell["probe"]["failures"] for cell in cells],
            "reference_prediction_mismatches_per_repetition": [
                cell["probe"]["reference_prediction_mismatches"] for cell in cells
            ],
            "predictions_stable_between_repetitions": predictions[0] == predictions[1],
        },
        "cells": cells,
        "decision": {
            "loader_experiment_authorized": eligible,
            "performance_claim_permitted": False,
            "sidecar_published_as_deployable": False,
            "raw_generated_binaries_retained": False,
            "post_result_gate_change_permitted": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_summary(args.evidence_dir, args.contract, args.root)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "loader_successor_authorized": summary["loader_successor_authorized"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
