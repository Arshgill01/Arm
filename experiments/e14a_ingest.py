#!/usr/bin/env python3
"""Validate and summarize the E14a selective-repack frontier."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e5b_ingest import (
        ARTIFACT_INPUTS,
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from experiments.e5h_ingest import parse_model_buffers
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e5j_ingest import validate_process_cpu
    from experiments.e9a_ingest import expected_server_argv
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import (
        ARTIFACT_INPUTS,
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from e5h_ingest import parse_model_buffers
    from e7a_ingest import validate_runtime_closure
    from e5j_ingest import validate_process_cpu
    from e9a_ingest import expected_server_argv


EXCLUDED_PATTERN = re.compile(
    r"ggml_repack_tensor_is_excluded: excluded tensor ([^\r\n]+)"
)


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E14a":
        raise ValueError("contract does not identify E14a")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E14a")
    for name in (
        "manifest",
        "policy",
        "models",
        "runtime_contract",
        "tasks",
        "e9a_contract",
        "patch_1",
        "patch_2",
        "patch_3",
        "selective_patch",
        "cell_runner",
        "ingest",
        "freeze",
    ):
        path = root / contract["inputs"][f"{name}_path"]
        if sha256_file(path) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E14a frozen input differs for {name}")
    for name, artifact_name in ARTIFACT_INPUTS.items():
        if name not in {"manifest", "policy", "models", "runtime_contract", "tasks"}:
            continue
        if (
            sha256_file(evidence / artifact_name)
            != contract["inputs"][f"{name}_sha256"]
        ):
            raise ValueError(f"E14a artifact input differs for {name}")
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
        or (evidence / "patched-files.txt").read_text().splitlines()
        != contract["source"]["changed_files"]
    ):
        raise ValueError("E14a source proof differs")
    for item in contract["source"]["patches"]:
        artifact = evidence / "patches" / Path(item["path"]).name
        if sha256_file(artifact) != item["sha256"]:
            raise ValueError("E14a retained patch differs")

    build = evidence / "build"
    command = load_object(build / "configure-command.json")
    if command.get("cmake_arguments") != contract["build"]["cmake_arguments"]:
        raise ValueError("E14a build arguments differ")
    cache_lines = (build / "CMakeCache.txt").read_text(errors="replace").splitlines()
    for argument in contract["build"]["cmake_arguments"]:
        if not argument.startswith("-D") or "=" not in argument:
            continue
        name, value = argument[2:].split("=", 1)
        if value in {"ON", "OFF"} and not any(
            line.startswith(f"{name}:") and line.endswith(f"={value}")
            for line in cache_lines
        ):
            raise ValueError(f"E14a CMake cache differs for {name}")
    version = (build / "server-version.txt").read_text(errors="replace").strip()
    if contract["source"]["commit"][:9] not in version:
        raise ValueError("E14a server version differs")
    closure = validate_runtime_closure(build / "runtime-closure.json")
    dependencies = sorted(
        {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
    )
    forbidden = set(contract["build"]["forbidden_dynamic_dependency_basenames"])
    if forbidden.intersection(dependencies):
        raise ValueError("E14a runtime closure contains a forbidden dependency")
    return {
        "source": source,
        "configure_command": command,
        "server_version": version,
        "runtime_closure": closure,
        "dynamic_dependency_basenames": dependencies,
    }


def parse_excluded_tensors(text: str) -> list[str]:
    return sorted(set(EXCLUDED_PATTERN.findall(text)))


def validate_invocation(cell_dir: Path, config: dict[str, Any]) -> None:
    environment = load_object(cell_dir / "environment.json")
    expected_regex = config["exclusion_regex"] or ""
    if environment != {
        "variable": "GGML_CPU_REPACK_EXCLUDE",
        "value": expected_regex,
        "weight_repack": config["weight_repack"],
    }:
        raise ValueError("E14a cell environment differs")
    timed = (cell_dir / "server-time.log").read_text(errors="replace")
    commands = [line for line in timed.splitlines() if "Command being timed:" in line]
    if len(commands) != 1:
        raise ValueError("E14a cell lacks one timed launcher command")
    if (" --no-repack" in commands[0]) is config["weight_repack"]:
        raise ValueError("E14a global repack invocation differs")


def validate_e14a_recipe(
    recipe: dict[str, Any],
    *,
    configuration: str,
    repetition: int,
    config: dict[str, Any],
    contract: dict[str, Any],
) -> None:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E14a"
        or recipe.get("configuration") != configuration
        or recipe.get("repetition") != repetition
        or recipe.get("source") != contract["source"]
        or recipe.get("build") != contract["build"]
        or recipe.get("service") != config
        or not isinstance(server, str)
        or not server.endswith("/bin/llama-server")
        or contract["source"]["commit"][:9] not in recipe.get("server_version", "")
        or not isinstance(model_path, str)
        or not model_path.endswith(".gguf")
        or model.get("sha256") != contract["selected"]["model_sha256"]
        or model.get("size_bytes") != contract["selected"]["model_size_bytes"]
        or recipe.get("runtime_environment")
        != {"GGML_CPU_REPACK_EXCLUDE": config["exclusion_regex"]}
    ):
        raise ValueError("E14a direct service recipe differs")
    expected = expected_server_argv(
        server,
        model_path,
        candidate=contract["selected"]["candidate"],
        profile_name="e7c_final",
    )
    if not config["weight_repack"]:
        expected.append("--no-repack")
    if recipe.get("argv") != expected:
        raise ValueError("E14a server argv differs from the exact E7c service")


def validate_e14a_cell(
    cell_dir: Path,
    *,
    configuration: str,
    repetition: int,
    config: dict[str, Any],
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
) -> dict[str, Any]:
    validate_e14a_recipe(
        load_object(cell_dir / "recipe.json"),
        configuration=configuration,
        repetition=repetition,
        config=config,
        contract=contract,
    )
    readiness = load_object(cell_dir / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not math.isfinite(ready_ms)
        or ready_ms < 0
        or ready_ms > contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError(f"{cell_dir.name} missed the readiness contract")
    probe = validate_probe(
        load_object(cell_dir / "probe.json"),
        configuration=configuration,
        repetition=repetition,
        config=config,
        contract=contract,
        tasks=tasks,
        references=references,
        require_selected_quality=False,
    )
    process = parse_time_output(
        (cell_dir / "server-time.log").read_text(encoding="utf-8")
    )
    shell_exit = int((cell_dir / "server-shell-exit.txt").read_text().strip())
    if (
        shell_exit not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
    ):
        raise ValueError(f"{cell_dir.name} process evidence missed the contract")
    slots = json.loads((cell_dir / "slots.json").read_text(encoding="utf-8"))
    if not isinstance(slots, list) or len(slots) != config["server_parallel_slots"]:
        raise ValueError(f"{cell_dir.name} slot count differs from the contract")
    metrics = (cell_dir / "metrics.txt").read_text(encoding="utf-8")
    if "llamacpp:" not in metrics:
        raise ValueError(f"{cell_dir.name} lacks server metrics")
    return {
        "configuration": configuration,
        "repetition": repetition,
        "ready_ms": float(ready_ms),
        "probe": probe,
        "process": process,
        "server_shell_exit_status": shell_exit,
        "slots_observed": len(slots),
    }


def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    no_more_memory = left["maximum_rss_kib"]["max"] <= right["maximum_rss_kib"]["max"]
    no_less_throughput = (
        left["requests_per_second"]["median"] >= right["requests_per_second"]["median"]
    )
    strict = (
        left["maximum_rss_kib"]["max"] < right["maximum_rss_kib"]["max"]
        or left["requests_per_second"]["median"]
        > right["requests_per_second"]["median"]
    )
    return no_more_memory and no_less_throughput and strict


def non_dominated_names(performance: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(
        name
        for name, point in performance.items()
        if not any(
            other_name != name and dominates(other, point)
            for other_name, other in performance.items()
        )
    )


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E14a evidence is not native Arm64")
    source_build = validate_source_build(evidence, contract)
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["manifest_path"]),
        contract["selected"]["candidate"],
    )
    configurations = contract["execution"]["configurations"]
    order = contract["execution"]["order"]
    expected_pairs = {
        (name, repetition)
        for name in configurations
        for repetition in range(
            1, contract["execution"]["repetitions_per_configuration"] + 1
        )
    }
    observed_pairs = {(item["configuration"], item["repetition"]) for item in order}
    if len(order) != len(expected_pairs) or observed_pairs != expected_pairs:
        raise ValueError("E14a execution order is incomplete")

    cells: list[dict[str, Any]] = []
    cell_paths: dict[tuple[str, int], Path] = {}
    cpu_records: dict[tuple[str, int], dict[str, float | int]] = {}
    mechanisms: dict[tuple[str, int], dict[str, Any]] = {}
    for index, item in enumerate(order, start=1):
        name = item["configuration"]
        repetition = item["repetition"]
        config = configurations[name]
        cell_dir = evidence / "cells" / f"{index:02d}-{name}-r{repetition}"
        cell_paths[(name, repetition)] = cell_dir
        validate_invocation(cell_dir, config)
        cell = validate_e14a_cell(
            cell_dir,
            configuration=name,
            repetition=repetition,
            config=config,
            contract=contract,
            tasks=tasks,
            references=references,
        )
        cells.append(cell)
        probe = load_object(cell_dir / "probe.json")
        cpu_records[(name, repetition)] = validate_process_cpu(
            probe,
            cell_dir=cell_dir,
            measured_requests=contract["request"]["measured_tasks"],
        )
        log = (cell_dir / "server.stderr.log").read_text(errors="replace")
        excluded = parse_excluded_tensors(log)
        if excluded != config["expected_excluded_tensors"]:
            raise ValueError(f"E14a excluded tensor inventory differs for {name}")
        mechanism = parse_model_buffers(log, config=config)
        mechanisms[(name, repetition)] = {**mechanism, "excluded_tensors": excluded}

    performance: dict[str, dict[str, Any]] = {}
    for name, config in configurations.items():
        config_cells = [cell for cell in cells if cell["configuration"] == name]
        probes = [
            load_object(cell_paths[(name, cell["repetition"])] / "probe.json")
            for cell in config_cells
        ]
        raw_cases = [case for probe in probes for case in probe["cases"]]
        prediction_maps = [
            {case["id"]: case["predicted"] for case in probe["cases"]}
            for probe in probes
        ]
        cpu = [cpu_records[(name, cell["repetition"])] for cell in config_cells]
        mechanism_records = [
            mechanisms[(name, cell["repetition"])] for cell in config_cells
        ]
        exact_quality = all(
            cell["probe"]["correct"] == contract["selected"]["reference_correct"]
            and cell["probe"]["reference_prediction_mismatches"]
            == contract["acceptance"]["reference_prediction_mismatches"]
            for cell in config_cells
        ) and all(item == prediction_maps[0] for item in prediction_maps[1:])
        performance[name] = {
            "weight_repack": config["weight_repack"],
            "exclusion_regex": config["exclusion_regex"],
            "excluded_tensor_count": len(config["expected_excluded_tensors"]),
            "quality": {
                "exact_selected_predictions": exact_quality,
                "correct_per_repetition": [
                    cell["probe"]["correct"] for cell in config_cells
                ],
                "reference_prediction_mismatches_per_repetition": [
                    cell["probe"]["reference_prediction_mismatches"]
                    for cell in config_cells
                ],
                "predictions_stable_between_repetitions": all(
                    item == prediction_maps[0] for item in prediction_maps[1:]
                ),
            },
            "requests_per_second": summarize(
                [cell["probe"]["requests_per_second"] for cell in config_cells]
            ),
            "http_ms": summarize([float(case["http_ms"]) for case in raw_cases]),
            "encode_ms": summarize([float(case["encode_ms"]) for case in raw_cases]),
            "decode_ms": summarize([float(case["decode_ms"]) for case in raw_cases]),
            "server_cpu_seconds_per_request": summarize(
                [float(item["seconds_per_request"]) for item in cpu]
            ),
            "average_server_cores_used": summarize(
                [float(item["average_cores_used"]) for item in cpu]
            ),
            "maximum_rss_kib": summarize(
                [float(cell["process"]["maximum_rss_kib"]) for cell in config_cells]
            ),
            "ready_ms": summarize([cell["ready_ms"] for cell in config_cells]),
            "mapped_buffer_mib": summarize(
                [item["mapped_buffer_mib"] for item in mechanism_records]
            ),
            "repack_buffer_mib": summarize(
                [item["repack_buffer_mib"] for item in mechanism_records]
            ),
            "total_model_buffers_mib": summarize(
                [item["total_model_buffers_mib"] for item in mechanism_records]
            ),
            "repetitions": config_cells,
        }

    baseline_name = contract["execution"]["baseline_configuration"]
    no_repack_name = contract["execution"]["no_repack_configuration"]
    baseline = performance[baseline_name]
    no_repack = performance[no_repack_name]
    extra_rss = baseline["maximum_rss_kib"]["max"] - no_repack["maximum_rss_kib"]["max"]
    if extra_rss <= 0:
        raise ValueError("E14a endpoint RSS ordering differs")
    acceptance = contract["acceptance"]
    candidate_gates: dict[str, dict[str, Any]] = {}
    eligible: list[str] = []
    for name in contract["execution"]["selective_configurations"]:
        point = performance[name]
        throughput_ratio = (
            point["requests_per_second"]["median"]
            / baseline["requests_per_second"]["median"]
        )
        p95_ratio = point["http_ms"]["p95"] / baseline["http_ms"]["p95"]
        saved_fraction = (
            baseline["maximum_rss_kib"]["max"] - point["maximum_rss_kib"]["max"]
        ) / extra_rss
        gates = {
            "quality": point["quality"]["exact_selected_predictions"],
            "throughput_stable": point["requests_per_second"][
                "coefficient_of_variation"
            ]
            <= acceptance["maximum_throughput_coefficient_of_variation"],
            "throughput_retention": throughput_ratio
            >= acceptance["minimum_selective_throughput_retention_ratio"],
            "extra_rss_saved": saved_fraction
            >= acceptance["minimum_selective_extra_rss_saved_fraction"],
            "p95_latency": p95_ratio
            <= acceptance["maximum_selective_p95_http_latency_ratio"],
        }
        candidate_gates[name] = {
            "eligible": all(gates.values()),
            "gates": gates,
            "throughput_retention_ratio": throughput_ratio,
            "p95_http_latency_ratio": p95_ratio,
            "extra_rss_saved_fraction": saved_fraction,
        }
        if all(gates.values()):
            eligible.append(name)

    non_dominated = non_dominated_names(performance)
    common_gates = {
        "all_quality_exact": all(
            point["quality"]["exact_selected_predictions"]
            for point in performance.values()
        ),
        "all_throughput_stable": all(
            point["requests_per_second"]["coefficient_of_variation"]
            <= acceptance["maximum_throughput_coefficient_of_variation"]
            for point in performance.values()
        ),
        "minimum_non_dominated_points": len(non_dominated)
        >= acceptance["minimum_non_dominated_points"],
        "selective_target": bool(eligible),
    }
    promoted = all(common_gates.values())
    selected = (
        max(
            eligible,
            key=lambda name: (
                candidate_gates[name]["extra_rss_saved_fraction"],
                performance[name]["requests_per_second"]["median"],
                name,
            ),
        )
        if promoted
        else baseline_name
    )
    frontier = sorted(
        (
            {
                "configuration": name,
                "maximum_rss_kib": point["maximum_rss_kib"]["max"],
                "median_requests_per_second": point["requests_per_second"]["median"],
                "non_dominated": name in non_dominated,
            }
            for name, point in performance.items()
        ),
        key=lambda item: (item["maximum_rss_kib"], -item["median_requests_per_second"]),
    )
    provenance = load_object(evidence / "provenance.json")
    return {
        "schema_version": 1,
        "experiment_id": "E14a",
        "status": (
            "valid_selective_repack_frontier"
            if promoted
            else "valid_no_selective_repack_promotion"
        ),
        "promoted": promoted,
        "contract_sha256": sha256_file(contract_path),
        "scope": contract["scope"],
        "platform": platform,
        "source_build": source_build,
        "selection": {
            "baseline_configuration": baseline_name,
            "no_repack_configuration": no_repack_name,
            "selected_configuration": selected,
            "eligible_selective_configurations": sorted(eligible),
            "non_dominated_configurations": non_dominated,
            "weighted_score_used": False,
        },
        "gates": common_gates,
        "candidate_gates": candidate_gates,
        "frontier": frontier,
        "performance": performance,
        "cells": cells,
        "provenance": provenance,
        "measurement_boundary": contract["measurement_boundary"],
        "claim_boundary": contract["claim_boundary"],
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
