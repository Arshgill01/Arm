#!/usr/bin/env python3
"""Validate the E6g/E6i current-runtime launch-adapter integration lanes."""

from __future__ import annotations

import argparse
import json
import math
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
    from experiments.e5j_ingest import validate_process_cpu
    from experiments.e6f_ingest import expected_server_argv
    from experiments.e7a_runtime_closure import parse_ldd_paths
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
    from e5j_ingest import validate_process_cpu
    from e6f_ingest import expected_server_argv
    from e7a_runtime_closure import parse_ldd_paths


ARTIFACT_INPUTS = {
    "manifest": "selected-manifest.json",
    "policy": "deployment-policy.json",
    "models": "models-manifest.json",
    "model_contract": "model-contract.json",
    "runtime_manifest": "runtime-manifest.json",
    "runtime_contract": "runtime-launch-contract.json",
    "tasks": "tasks-manifest.json",
}
LAUNCH_PROFILES = {
    "E6g": {
        "runtime_experiment_id": "E6f",
        "runtime_status": "valid_current_runtime_upgrade_candidate",
        "status": "valid_current_runtime_launch_integration",
        "claim_flag": "current_runtime_launch_claim_allowed",
    },
    "E6i": {
        "runtime_experiment_id": "E6h",
        "runtime_status": "valid_current_runtime_memory_tier_upgrade_candidate",
        "status": "valid_current_runtime_memory_launch_integration",
        "claim_flag": "current_runtime_memory_launch_claim_allowed",
    },
    "E7c": {
        "runtime_experiment_id": "E7b",
        "runtime_status": "valid_http_dependency_pruning_candidate",
        "status": "valid_http_dependency_pruned_launch_integration",
        "claim_flag": "http_dependency_pruned_launch_claim_allowed",
        "dependency_proof": True,
    },
}


def parse_dependency_basenames(output: str) -> list[str]:
    return sorted({path.name for path in parse_ldd_paths(output)})


def launch_profile(contract: dict[str, Any]) -> dict[str, Any]:
    experiment_id = contract.get("experiment_id")
    profile = LAUNCH_PROFILES.get(experiment_id)
    if contract.get("schema_version") != 1 or profile is None:
        raise ValueError("invalid current-runtime launch contract")
    return profile


def validate_copied_inputs(
    evidence_dir: Path,
    contract: dict[str, Any],
    paths: dict[str, Path],
) -> None:
    experiment_id = contract["experiment_id"]
    inputs = contract["inputs"]
    for name, artifact_name in ARTIFACT_INPUTS.items():
        expected = inputs[f"{name}_sha256"]
        if (
            sha256_file(paths[name]) != expected
            or sha256_file(evidence_dir / artifact_name) != expected
        ):
            raise ValueError(f"{experiment_id} {name} input hash differs")


def validate_source_and_build(
    evidence_dir: Path,
    *,
    contract: dict[str, Any],
    launch_contract: dict[str, Any],
    recipe: dict[str, Any],
) -> dict[str, Any]:
    experiment_id = contract["experiment_id"]
    source = load_object(evidence_dir / "source.json")
    expected_source = contract["runtime"]
    if (
        source.get("schema_version") != 1
        or source.get("repository") != expected_source["repository"]
        or source.get("tag") != expected_source["tag"]
        or source.get("commit") != expected_source["commit"]
    ):
        raise ValueError(f"{experiment_id} source proof differs from the contract")
    source_diff = evidence_dir / "source-diff.patch"
    patched_files = (evidence_dir / "patched-files.txt").read_text().splitlines()
    runtime_record = launch_contract["runtime"]
    if (
        sha256_file(source_diff) != expected_source["source_diff_sha256"]
        or patched_files != runtime_record["changed_files"]
    ):
        raise ValueError(
            f"{experiment_id} patched source differs from the launch contract"
        )

    runtime = recipe["runtime"]
    upgrade = runtime.get("upgrade_provenance", {})
    cache_path = evidence_dir / "CMakeCache.txt"
    cache_lines = set(cache_path.read_text(errors="replace").splitlines())
    required_cache = set(launch_contract["build"]["cmake_cache_entries"])
    binary_path = evidence_dir / "llama-server"
    if (
        not required_cache.issubset(cache_lines)
        or f"CMAKE_HOME_DIRECTORY:INTERNAL={upgrade.get('source_root')}"
        not in cache_lines
        or sha256_file(cache_path) != upgrade.get("cmake_cache_sha256")
        or sha256_file(binary_path) != upgrade.get("server_sha256")
        or upgrade.get("source_commit") != expected_source["commit"]
        or upgrade.get("source_diff_sha256") != expected_source["source_diff_sha256"]
        or upgrade.get("changed_files") != runtime_record["changed_files"]
        or upgrade.get("patches") != runtime_record["patches"]
        or upgrade.get("selected_commit") != expected_source["commit"]
    ):
        raise ValueError(f"{experiment_id} build or binary provenance differs")
    forbidden_dependencies = launch_contract["build"].get(
        "forbidden_dynamic_dependency_basenames", []
    )
    if forbidden_dependencies and (
        upgrade.get("dynamic_dependency_basenames") is None
        or set(upgrade["dynamic_dependency_basenames"]).intersection(
            forbidden_dependencies
        )
    ):
        raise ValueError(f"{experiment_id} runtime dependency provenance differs")
    return {
        **source,
        "source_diff_sha256": sha256_file(source_diff),
        "changed_files": patched_files,
        "cmake_cache_sha256": sha256_file(cache_path),
        "server_sha256": sha256_file(binary_path),
        **(
            {
                "dynamic_dependency_basenames": upgrade[
                    "dynamic_dependency_basenames"
                ]
            }
            if forbidden_dependencies
            else {}
        ),
    }


def validate_recipe(
    recipe: dict[str, Any],
    *,
    contract: dict[str, Any],
    launch_contract: dict[str, Any],
) -> None:
    experiment_id = contract["experiment_id"]
    profile = launch_profile(contract)
    inputs = contract["inputs"]
    selected = contract["selected"]
    service = contract["service"]
    recipe_inputs = recipe.get("inputs", {})
    runtime = recipe.get("runtime", {})
    upgrade = runtime.get("upgrade_provenance", {})
    model_files = recipe.get("model", {}).get("files")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("service") != "Pareto64"
        or recipe.get("status") != "ready_to_launch"
        or recipe.get("selected_candidate") != selected["candidate"]
        or recipe.get("selection", {}).get("plan_status") != "selected"
        or recipe.get("selection", {}).get("runtime_upgrade")
        != {
            "status": profile["runtime_status"],
            "experiment_id": profile["runtime_experiment_id"],
            "selected_commit": contract["runtime"]["commit"],
            "promotion_mode": "explicit_evidence_bound_upgrade",
        }
        or recipe.get("weighted_score_used") is not False
        or not isinstance(model_files, list)
        or len(model_files) != 1
        or model_files[0].get("sha256") != selected["model_sha256"]
        or model_files[0].get("size_bytes") != selected["model_size_bytes"]
    ):
        raise ValueError(f"{experiment_id} launch recipe does not preserve selection")
    for recipe_name, input_name in (
        ("manifest", "manifest"),
        ("constraints", "policy"),
        ("models", "models"),
        ("contract", "model_contract"),
        ("runtime_manifest", "runtime_manifest"),
        ("runtime_contract", "runtime_contract"),
    ):
        if recipe_inputs.get(f"{recipe_name}_sha256") != inputs[
            f"{input_name}_sha256"
        ]:
            raise ValueError(f"{experiment_id} recipe {recipe_name} hash differs")
    expected_runtime = {
        "llama_cpp_commit": contract["runtime"]["commit"],
        "threads": service["threads"],
        "parallel_slots": service["server_parallel_slots"],
        "prompt_cache": service["prompt_cache"],
        "kv_cache_type_k": service["kv_cache_type_k"],
        "kv_cache_type_v": service["kv_cache_type_v"],
        "flash_attention": service["flash_attention"],
        "context_per_slot": service["context_per_slot"],
        "context_total": service["context_per_slot"]
        * service["server_parallel_slots"],
        "batch_size_requested": service["batch_size"],
        "micro_batch_size_requested": service["micro_batch_size"],
        "batch_size": service["batch_size"],
        "micro_batch_size": service["micro_batch_size"],
        "weight_repack": service["weight_repack"],
        "log_verbosity": service["log_verbosity"],
    }
    if any(runtime.get(name) != value for name, value in expected_runtime.items()):
        raise ValueError(
            f"{experiment_id} runtime recipe differs from the exact service"
        )
    if contract["runtime"]["commit"][:9] not in runtime.get("server_version", ""):
        raise ValueError(f"{experiment_id} server version differs from current source")
    expected_argv = expected_server_argv(
        runtime["server_path"],
        model_files[0]["path"],
        candidate=selected["candidate"],
        service=service,
    )
    if runtime.get("argv") != expected_argv:
        raise ValueError(f"{experiment_id} server argv differs from the exact service")
    if (
        upgrade.get("contract_id") != launch_contract["contract_id"]
        or upgrade.get("promotion_mode") != launch_contract["promotion_mode"]
        or upgrade.get("runtime_manifest_sha256")
        != inputs["runtime_manifest_sha256"]
        or upgrade.get("runtime_contract_sha256")
        != inputs["runtime_contract_sha256"]
        or upgrade.get("claim_boundary") != launch_contract["claim_boundary"]
    ):
        raise ValueError(f"{experiment_id} recipe lacks current-runtime provenance")


def validate_outer_invocation(
    evidence_dir: Path,
    contract: dict[str, Any],
) -> None:
    experiment_id = contract["experiment_id"]
    text = (evidence_dir / "server-time.log").read_text(errors="replace")
    commands = [line for line in text.splitlines() if "Command being timed:" in line]
    required = (
        "python3 -m pareto64 launch",
        "--runtime-manifest",
        "--runtime-contract",
        "--llama-source-root",
        "--llama-build-root",
        "--parallel 1",
    )
    no_repack_present = "--no-weight-repack" in commands[0] if commands else False
    if (
        len(commands) != 1
        or any(value not in commands[0] for value in required)
        or no_repack_present is contract["service"]["weight_repack"]
    ):
        raise ValueError(
            f"{experiment_id} timed invocation did not use the exact upgrade adapter"
        )


def build_manifest(
    evidence_dir: Path,
    contract_path: Path,
    paths: dict[str, Path],
) -> dict[str, Any]:
    contract = load_object(contract_path)
    profile = launch_profile(contract)
    experiment_id = contract["experiment_id"]
    required = [
        "provenance.json",
        "source.json",
        "source-diff.patch",
        "patched-files.txt",
        "CMakeCache.txt",
        "llama-server",
        "recipe.json",
        "probe.json",
        "readiness.json",
        "server-pid.txt",
        "server-time.log",
        "server-shell-exit.txt",
        "metrics.txt",
        "slots.json",
        "lscpu.txt",
        "uname.txt",
        "python-version.txt",
        *ARTIFACT_INPUTS.values(),
    ]
    if profile.get("dependency_proof"):
        required.append("runtime-ldd.txt")
    missing = [name for name in required if not (evidence_dir / name).is_file()]
    if missing:
        raise ValueError(f"missing {experiment_id} evidence: {', '.join(missing)}")
    validate_copied_inputs(evidence_dir, contract, paths)
    launch_contract = load_object(paths["runtime_contract"])
    recipe = load_object(evidence_dir / "recipe.json")
    validate_recipe(recipe, contract=contract, launch_contract=launch_contract)
    source = validate_source_and_build(
        evidence_dir,
        contract=contract,
        launch_contract=launch_contract,
        recipe=recipe,
    )
    validate_outer_invocation(evidence_dir, contract)

    dependency_names: list[str] | None = None
    if profile.get("dependency_proof"):
        dependency_names = parse_dependency_basenames(
            (evidence_dir / "runtime-ldd.txt").read_text(errors="replace")
        )
        forbidden_dependencies = set(
            contract["acceptance"]["forbidden_runtime_dependency_basenames"]
        )
        recipe_dependencies = recipe["runtime"]["upgrade_provenance"].get(
            "dynamic_dependency_basenames"
        )
        if (
            dependency_names != recipe_dependencies
            or set(dependency_names).intersection(forbidden_dependencies)
        ):
            raise ValueError(
                f"{experiment_id} runtime dependency inventory differs"
            )

    tasks = load_tasks(load_object(paths["tasks"]))
    references = reference_predictions(
        load_object(paths["manifest"]), contract["selected"]["candidate"]
    )
    probe_object = load_object(evidence_dir / "probe.json")
    probe = validate_probe(
        probe_object,
        configuration="current_patched",
        repetition=1,
        config=contract["service"],
        contract=contract,
        tasks=tasks,
        references=references,
    )
    process_cpu = validate_process_cpu(
        probe_object,
        cell_dir=evidence_dir,
        measured_requests=len(tasks),
    )
    readiness = load_object(evidence_dir / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    process = parse_time_output((evidence_dir / "server-time.log").read_text())
    shell_exit = int((evidence_dir / "server-shell-exit.txt").read_text().strip())
    slots = json.loads((evidence_dir / "slots.json").read_text())
    metrics = (evidence_dir / "metrics.txt").read_text()
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not math.isfinite(ready_ms)
        or ready_ms < 0
        or ready_ms > contract["acceptance"]["maximum_ready_ms"]
        or shell_exit
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
        or not isinstance(slots, list)
        or len(slots) != contract["service"]["server_parallel_slots"]
        or "llamacpp:" not in metrics
    ):
        raise ValueError(f"{experiment_id} runtime smoke missed an absolute gate")
    provenance = load_object(evidence_dir / "provenance.json")
    if provenance.get("experiment_id") != experiment_id:
        raise ValueError(f"{experiment_id} provenance differs")
    platform = parse_lscpu((evidence_dir / "lscpu.txt").read_text())
    if platform["architecture"] != "aarch64":
        raise ValueError(f"{experiment_id} requires a native aarch64 host")

    return {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "status": profile["status"],
        "scope": contract["scope"],
        "provenance": provenance,
        "source": source,
        "platform": {
            **platform,
            "uname": (evidence_dir / "uname.txt").read_text().strip(),
            "python": (evidence_dir / "python-version.txt").read_text().strip(),
        },
        "selection": {
            **contract["selected"],
            "runtime_commit": contract["runtime"]["commit"],
            "service": contract["service"],
        },
        "quality": {
            "correct": probe["correct"],
            "total": probe["total"],
            "accuracy": probe["accuracy"],
            "reference_prediction_mismatches": probe[
                "reference_prediction_mismatches"
            ],
            "request_failures": probe["failures"],
            "exact_selected_predictions": True,
            "cached_prefix_observed_in_every_measured_request": True,
        },
        "performance": {
            "ready_ms": float(ready_ms),
            "requests_per_second": probe["requests_per_second"],
            "http_ms": probe["http_ms"],
            "server_process_cpu": process_cpu,
            "maximum_rss_kib": process["maximum_rss_kib"],
        },
        "runtime_provenance": recipe["runtime"]["upgrade_provenance"],
        "validation": {
            "all_input_hashes_match": True,
            "model_selection_recomputed": True,
            "runtime_upgrade_manifest_verified": True,
            "exact_source_diff_verified": True,
            "source_build_binary_bound": True,
            "exact_service_recipe_verified": True,
            "live_server_executed_through_adapter": True,
            "selected_quality_reproduced": True,
            "prefix_reuse_reproduced": True,
            **(
                {
                    "runtime_dependency_inventory_verified": True,
                    "openssl_dependencies_absent": True,
                }
                if dependency_names is not None
                else {}
            ),
            profile["claim_flag"]: True,
            "automatic_other_profile_promotion_allowed": False,
            "energy_claim_allowed": False,
            "weighted_score_used": False,
            "claim_scope": contract["claim_boundary"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    for name in ARTIFACT_INPUTS:
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    paths = {name: getattr(arguments, name) for name in ARTIFACT_INPUTS}
    manifest = build_manifest(arguments.evidence_dir, arguments.contract, paths)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
