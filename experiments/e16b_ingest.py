#!/usr/bin/env python3
"""Validate and summarize the E16b read-only repack-sidecar loader experiment."""

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
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from experiments.e5j_ingest import validate_process_cpu
    from experiments.e9a_ingest import expected_server_argv
    from experiments.e16a_ingest import (
        ARTIFACT_INPUTS,
        inventory_matches_header,
        read_inventory,
        validate_source_build,
    )
    from experiments.e16b_freeze import INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import (
        load_object,
        load_tasks,
        reference_predictions,
        sha256_file,
        validate_probe,
    )
    from e5j_ingest import validate_process_cpu
    from e9a_ingest import expected_server_argv
    from e16a_ingest import (
        ARTIFACT_INPUTS,
        inventory_matches_header,
        read_inventory,
        validate_source_build,
    )
    from e16b_freeze import INPUT_PATHS


LOADER_MAPPED = re.compile(
    r"CPU repack sidecar: mapped (\d+) bytes read-only from (.+) with (\d+) bound tensors"
)
LOADER_COMPLETE = re.compile(
    r"CPU repack sidecar: validated and loaded all (\d+) tensors without runtime repacking"
)


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E16b":
        raise ValueError("contract does not identify E16b")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E16b")
    for name, relative in INPUT_PATHS.items():
        if sha256_file(root / relative) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E16b frozen input differs for {name}")
    for name, artifact_name in ARTIFACT_INPUTS.items():
        if (
            sha256_file(evidence / artifact_name)
            != contract["inputs"][f"{name}_sha256"]
        ):
            raise ValueError(f"E16b artifact input differs for {name}")
    if (
        sha256_file(evidence / "e16a-prerequisite.json")
        != contract["inputs"]["e16a_result_sha256"]
    ):
        raise ValueError("E16b artifact prerequisite differs")
    return contract


def parse_smaps_rollup(path: Path) -> dict[str, int]:
    fields: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([A-Za-z_]+):\s+(\d+) kB", line)
        if match:
            fields[match.group(1)] = int(match.group(2))
    required = {
        "Rss",
        "Pss",
        "Shared_Clean",
        "Shared_Dirty",
        "Private_Clean",
        "Private_Dirty",
        "Anonymous",
        "Swap",
    }
    if not required <= fields.keys() or fields["Rss"] <= 0 or fields["Pss"] <= 0:
        raise ValueError(f"{path.parent.name} smaps rollup is incomplete")
    return {name: fields[name] for name in sorted(required)}


def parse_page_faults(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    patterns = {
        "major": r"^\s*Major \(requiring I/O\) page faults:\s*(\d+)\s*$",
        "minor": r"^\s*Minor \(reclaiming a frame\) page faults:\s*(\d+)\s*$",
    }
    values: dict[str, int] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.MULTILINE)
        if match is None:
            raise ValueError(f"{path.parent.name} lacks {name} page-fault evidence")
        values[name] = int(match.group(1))
    return values


def expected_runtime_environment(
    configuration: str, identity: dict[str, Any]
) -> dict[str, Any]:
    if configuration == "normal_repack":
        return {"GGML_CPU_REPACK_SIDECAR": None}
    cpu = identity["cpu"]
    return {
        "GGML_CPU_REPACK_SIDECAR": "one-time generated and independently verified sidecar",
        "GGML_CPU_REPACK_SIDECAR_EXPERIMENT_ID": identity["experiment_id"],
        "GGML_CPU_REPACK_SIDECAR_MODEL_SHA256": identity["source_model_sha256"],
        "GGML_CPU_REPACK_SIDECAR_SOURCE_COMMIT": identity["llama_cpp_commit"],
        "GGML_CPU_REPACK_SIDECAR_SOURCE_DIFF_SHA256": identity["source_diff_sha256"],
        "GGML_CPU_REPACK_SIDECAR_ARCHITECTURE": cpu["architecture"],
        "GGML_CPU_REPACK_SIDECAR_CPU_FEATURES_SHA256": cpu["common_features_sha256"],
        "GGML_CPU_REPACK_SIDECAR_SVE_BYTES": str(cpu["sve_vector_length_bytes"]),
    }


def validate_recipe(
    recipe: dict[str, Any],
    *,
    contract: dict[str, Any],
    identity: dict[str, Any],
    configuration: str,
    repetition: int,
) -> None:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E16b"
        or recipe.get("configuration") != configuration
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
        != expected_runtime_environment(configuration, identity)
    ):
        raise ValueError(f"E16b {configuration} recipe differs")
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
        raise ValueError("E16b server argv differs from exact E7c")


def validate_construction(
    evidence: Path, contract: dict[str, Any], identity: dict[str, Any]
) -> dict[str, Any]:
    directory = evidence / "construction"
    recipe = load_object(directory / "recipe.json")
    expected = expected_server_argv(
        recipe["server_path"],
        recipe["model_path"],
        candidate=contract["selected"]["candidate"],
        profile_name="e7c_final",
    )
    expected.extend(
        ["--log-verbosity", str(contract["mechanism"]["proof_log_verbosity"])]
    )
    if (
        recipe.get("experiment_id") != "E16b"
        or recipe.get("phase") != "one_time_sidecar_construction"
        or recipe.get("argv") != expected
        or recipe.get("runtime_environment")
        != {
            "GGML_CPU_REPACK_DUMP_DIR": "fresh generated scratch directory",
            "GGML_CPU_REPACK_SIDECAR": None,
        }
    ):
        raise ValueError("E16b construction recipe differs")
    index = load_object(directory / "sidecar-index.json")
    header = index.get("header", {})
    inventory = read_inventory(directory / "inventory.tsv")
    verification = load_object(directory / "verification.json")
    cleanup = load_object(directory / "raw-dump-cleanup.json")
    process = parse_time_output((directory / "server-time.log").read_text())
    build_process = parse_time_output(
        (directory / "sidecar-build-time.log").read_text()
    )
    readiness = load_object(directory / "readiness.json")
    if (
        header.get("binding") != identity
        or header.get("data_offset")
        != contract["mechanism"]["sidecar_data_offset_bytes"]
        or not inventory_matches_header(inventory, header.get("tensors", []))
        or verification.get("status") != "valid_sidecar"
        or verification.get("sidecar_sha256") != index.get("sidecar_sha256")
        or cleanup.get("deleted_raw_tensor_count") != header.get("tensor_count")
        or cleanup.get("deleted_raw_tensor_bytes") != header.get("packed_tensor_bytes")
        or cleanup.get("sidecar_sha256") != index.get("sidecar_sha256")
        or cleanup.get("sidecar_size_bytes") != index.get("sidecar_size_bytes")
        or cleanup.get("raw_tensor_cleanup_complete") is not True
        or cleanup.get("sidecar_retained_for_measured_cells") is not True
        or readiness.get("status") != "ok"
        or int((directory / "server-shell-exit.txt").read_text().strip())
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process.get("maximum_rss_kib") is None
        or process.get("exit_status") not in {0, 130}
        or build_process.get("maximum_rss_kib") is None
        or build_process.get("exit_status") != 0
        or header.get("tensor_count", 0)
        < contract["acceptance"]["minimum_tensor_count"]
        or header.get("coverage_fraction", 0.0)
        < contract["acceptance"]["minimum_packed_buffer_coverage_fraction"]
    ):
        raise ValueError("E16b construction evidence differs")
    return {
        "recipe": recipe,
        "sidecar_index": index,
        "inventory": inventory,
        "verification": verification,
        "cleanup": cleanup,
        "server_process": process,
        "sidecar_build_process": build_process,
        "ready_ms": float(readiness["ready_ms"]),
    }


def validate_cell(
    cell_dir: Path,
    *,
    contract: dict[str, Any],
    identity: dict[str, Any],
    configuration: str,
    repetition: int,
    tasks: list[dict[str, Any]],
    references: dict[str, str],
    sidecar_index: dict[str, Any],
) -> dict[str, Any]:
    validate_recipe(
        load_object(cell_dir / "recipe.json"),
        contract=contract,
        identity=identity,
        configuration=configuration,
        repetition=repetition,
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
        raise ValueError(f"{cell_dir.name} readiness differs")
    probe_object = load_object(cell_dir / "probe.json")
    probe = validate_probe(
        probe_object,
        configuration=configuration,
        repetition=repetition,
        config=contract["service"],
        contract=contract,
        tasks=tasks,
        references=references,
        require_selected_quality=False,
    )
    cpu = validate_process_cpu(
        probe_object,
        cell_dir=cell_dir,
        measured_requests=contract["request"]["measured_tasks"],
    )
    process = parse_time_output((cell_dir / "server-time.log").read_text())
    shell_exit = int((cell_dir / "server-shell-exit.txt").read_text().strip())
    smaps = parse_smaps_rollup(cell_dir / "smaps-rollup-after-workload.txt")
    page_faults = parse_page_faults(cell_dir / "server-time.log")
    maps = (cell_dir / "process-maps-after-workload.txt").read_text(encoding="utf-8")
    log = (cell_dir / "server.stderr.log").read_text(errors="replace")
    mapped = LOADER_MAPPED.findall(log)
    complete = LOADER_COMPLETE.findall(log)
    sidecar_map_lines = [
        line for line in maps.splitlines() if "pareto64-e16b-sidecar.bin" in line
    ]
    if configuration == "sidecar_loader":
        verification = load_object(cell_dir / "prelaunch-verification.json")
        mechanism_valid = (
            verification.get("status") == "valid_sidecar"
            and verification.get("sidecar_sha256") == sidecar_index["sidecar_sha256"]
            and len(mapped) == 1
            and mapped[0][0] == str(sidecar_index["header"]["arena_size_bytes"])
            and mapped[0][2] == str(sidecar_index["header"]["tensor_count"])
            and complete == [str(sidecar_index["header"]["tensor_count"])]
            and len(sidecar_map_lines) == 1
            and sidecar_map_lines[0].split()[1] == "r--s"
            and sidecar_map_lines[0].split()[2] == "00100000"
        )
    else:
        verification = None
        mechanism_valid = not mapped and not complete and not sidecar_map_lines
    if (
        shell_exit not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process.get("maximum_rss_kib") is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
        or not mechanism_valid
    ):
        raise ValueError(f"{cell_dir.name} process or loader evidence differs")
    return {
        "configuration": configuration,
        "repetition": repetition,
        "ready_ms": float(ready_ms),
        "probe": probe,
        "process": process,
        "process_cpu": cpu,
        "smaps_rollup_kib": smaps,
        "page_faults": page_faults,
        "server_shell_exit_status": shell_exit,
        "mechanism_valid": mechanism_valid,
        "prelaunch_verification": verification,
        "prediction_map": {
            case["id"]: case["predicted"] for case in probe_object["cases"]
        },
    }


def summarize_configuration(cells: list[dict[str, Any]]) -> dict[str, Any]:
    probes = [cell["probe"] for cell in cells]
    raw_cases = [case for probe in probes for case in probe["cases"]]
    predictions = [cell["prediction_map"] for cell in cells]
    return {
        "quality": {
            "correct_per_repetition": [probe["correct"] for probe in probes],
            "failures_per_repetition": [probe["failures"] for probe in probes],
            "reference_prediction_mismatches_per_repetition": [
                probe["reference_prediction_mismatches"] for probe in probes
            ],
            "predictions_stable_between_repetitions": all(
                item == predictions[0] for item in predictions[1:]
            ),
        },
        "requests_per_second": summarize(
            [cell["probe"]["requests_per_second"] for cell in cells]
        ),
        "http_ms": summarize([float(case["http_ms"]) for case in raw_cases]),
        "encode_ms": summarize([float(case["encode_ms"]) for case in raw_cases]),
        "decode_ms": summarize([float(case["decode_ms"]) for case in raw_cases]),
        "server_cpu_seconds_per_request": summarize(
            [float(cell["process_cpu"]["seconds_per_request"]) for cell in cells]
        ),
        "maximum_rss_kib": summarize(
            [float(cell["process"]["maximum_rss_kib"]) for cell in cells]
        ),
        "post_workload_rss_kib": summarize(
            [float(cell["smaps_rollup_kib"]["Rss"]) for cell in cells]
        ),
        "post_workload_pss_kib": summarize(
            [float(cell["smaps_rollup_kib"]["Pss"]) for cell in cells]
        ),
        "ready_ms": summarize([cell["ready_ms"] for cell in cells]),
        "major_page_faults": summarize(
            [float(cell["page_faults"]["major"]) for cell in cells]
        ),
        "minor_page_faults": summarize(
            [float(cell["page_faults"]["minor"]) for cell in cells]
        ),
        "cells": cells,
    }


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    source_build = validate_source_build(evidence, contract)
    identity = load_object(evidence / "sidecar-identity.json")
    construction = validate_construction(evidence, contract, identity)
    sidecar_index = construction["sidecar_index"]
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["manifest_path"]),
        contract["selected"]["candidate"],
    )
    cells: list[dict[str, Any]] = []
    for index, item in enumerate(contract["execution"]["order"], start=1):
        name = item["configuration"]
        repetition = item["repetition"]
        cell_dir = evidence / "cells" / f"{index:02d}-{name}-r{repetition}"
        cells.append(
            validate_cell(
                cell_dir,
                contract=contract,
                identity=identity,
                configuration=name,
                repetition=repetition,
                tasks=tasks,
                references=references,
                sidecar_index=sidecar_index,
            )
        )
    performance = {
        name: summarize_configuration(
            [cell for cell in cells if cell["configuration"] == name]
        )
        for name in contract["execution"]["configurations"]
    }
    baseline = performance[contract["execution"]["baseline_configuration"]]
    loader = performance[contract["execution"]["loader_configuration"]]
    ratios = {
        "throughput": loader["requests_per_second"]["median"]
        / baseline["requests_per_second"]["median"],
        "median_http_latency": loader["http_ms"]["median"]
        / baseline["http_ms"]["median"],
        "p95_http_latency": loader["http_ms"]["p95"] / baseline["http_ms"]["p95"],
        "cpu_seconds_per_request": loader["server_cpu_seconds_per_request"]["median"]
        / baseline["server_cpu_seconds_per_request"]["median"],
        "maximum_rss": loader["maximum_rss_kib"]["max"]
        / baseline["maximum_rss_kib"]["max"],
        "post_workload_pss": loader["post_workload_pss_kib"]["median"]
        / baseline["post_workload_pss_kib"]["median"],
        "readiness": loader["ready_ms"]["median"] / baseline["ready_ms"]["median"],
    }
    acceptance = contract["acceptance"]
    all_predictions = [cell["prediction_map"] for cell in cells]
    quality = all(
        cell["probe"]["correct"] == contract["selected"]["reference_correct"]
        and cell["probe"]["failures"] == acceptance["request_failures"]
        and cell["probe"]["reference_prediction_mismatches"]
        == acceptance["reference_prediction_mismatches"]
        for cell in cells
    ) and all(item == all_predictions[0] for item in all_predictions[1:])
    invalid = load_object(evidence / "invalid-identity" / "result.json")
    invalid_log = (evidence / "invalid-identity" / "server.stderr.log").read_text(
        errors="replace"
    )
    final_cleanup = load_object(evidence / "sidecar-cleanup.json")
    final_verification = load_object(evidence / "final-sidecar-verification.json")
    fail_closed = (
        invalid.get("server_exit_status") not in {0, 124}
        and invalid.get("readiness_succeeded") is False
        and invalid.get("deliberately_wrong_model_sha256") == "0" * 64
        and "binding differs for source_model_sha256" in invalid_log
    )
    cleanup = (
        final_verification.get("status") == "valid_sidecar"
        and final_verification.get("sidecar_sha256") == sidecar_index["sidecar_sha256"]
        and final_cleanup.get("deleted_sidecar_bytes")
        == sidecar_index["sidecar_size_bytes"]
        and final_cleanup.get("deleted_sidecar_sha256")
        == sidecar_index["sidecar_sha256"]
        and final_cleanup.get("sidecar_cleanup_complete") is True
    )
    benefit = (
        ratios["maximum_rss"] <= acceptance["maximum_peak_rss_ratio"]
        or ratios["post_workload_pss"] <= acceptance["maximum_post_workload_pss_ratio"]
        or ratios["readiness"] <= acceptance["maximum_readiness_ratio"]
    )
    gates = {
        "native_architecture": platform["architecture"]
        == acceptance["required_architecture"],
        "required_cpu_features": set(acceptance["required_common_cpu_features"])
        <= set(identity["cpu"]["common_features"]),
        "exact_quality": quality,
        "loader_mechanism": all(cell["mechanism_valid"] for cell in cells),
        "invalid_identity_rejected_before_readiness": fail_closed,
        "bounded_cleanup": cleanup,
        "throughput_stability": all(
            point["requests_per_second"]["coefficient_of_variation"]
            <= acceptance["maximum_throughput_coefficient_of_variation"]
            for point in performance.values()
        ),
        "throughput_retention": ratios["throughput"]
        >= acceptance["minimum_throughput_retention_ratio"],
        "median_latency_retention": ratios["median_http_latency"]
        <= acceptance["maximum_median_http_latency_ratio"],
        "p95_latency_retention": ratios["p95_http_latency"]
        <= acceptance["maximum_p95_http_latency_ratio"],
        "cpu_retention": ratios["cpu_seconds_per_request"]
        <= acceptance["maximum_cpu_seconds_per_request_ratio"],
        "material_startup_or_memory_benefit": benefit,
    }
    promoted = all(gates.values())
    return {
        "schema_version": 1,
        "experiment_id": "E16b",
        "contract_sha256": sha256_file(contract_path),
        "status": (
            "valid_sidecar_loader_promoted"
            if promoted
            else "valid_sidecar_loader_no_promotion"
        ),
        "promoted": promoted,
        "failed_gates": sorted(name for name, passed in gates.items() if not passed),
        "gates": gates,
        "ratios": ratios,
        "platform": platform,
        "source_build": source_build,
        "sidecar_identity": identity,
        "construction": construction,
        "invalid_identity_preflight": invalid,
        "final_sidecar_verification": final_verification,
        "sidecar_cleanup": final_cleanup,
        "performance": performance,
        "cells": cells,
        "measurement_boundary": contract["measurement_boundary"],
        "claim_boundary": contract["claim_boundary"],
        "decision": {
            "selected_configuration": (
                contract["execution"]["loader_configuration"]
                if promoted
                else contract["execution"]["baseline_configuration"]
            ),
            "sidecar_construction_cost_included_in_steady_state": False,
            "cold_storage_claim_permitted": False,
            "multi_process_sharing_claim_permitted": False,
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
    print(json.dumps({"status": summary["status"], "promoted": summary["promoted"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
