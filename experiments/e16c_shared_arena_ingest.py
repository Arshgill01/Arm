#!/usr/bin/env python3
"""Validate and summarize the E16c two-worker shared-sidecar experiment."""

from __future__ import annotations

import argparse
import json
import math
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
    from experiments.e9a_ingest import expected_server_argv
    from experiments.e16a_ingest import ARTIFACT_INPUTS, validate_source_build
    from experiments.e16b_ingest import (
        LOADER_COMPLETE,
        LOADER_MAPPED,
        parse_page_faults,
        parse_smaps_rollup,
        validate_construction,
    )
    from experiments.e16c_shared_arena_freeze import INPUT_PATHS
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
    from e9a_ingest import expected_server_argv
    from e16a_ingest import ARTIFACT_INPUTS, validate_source_build
    from e16b_ingest import (
        LOADER_COMPLETE,
        LOADER_MAPPED,
        parse_page_faults,
        parse_smaps_rollup,
        validate_construction,
    )
    from e16c_shared_arena_freeze import INPUT_PATHS


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E16c":
        raise ValueError("contract does not identify E16c")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E16c")
    for name, relative in INPUT_PATHS.items():
        if sha256_file(root / relative) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E16c frozen input differs for {name}")
        if (
            sha256_file(evidence / "frozen-inputs" / relative)
            != contract["inputs"][f"{name}_sha256"]
        ):
            raise ValueError(f"E16c retained artifact input differs for {name}")
    for name, artifact_name in ARTIFACT_INPUTS.items():
        if (
            sha256_file(evidence / artifact_name)
            != contract["inputs"][f"{name}_sha256"]
        ):
            raise ValueError(f"E16c artifact input differs for {name}")
    prerequisite_artifacts = {
        "e16a_result": "e16a-prerequisite.json",
        "e16b_result": "e16b-prerequisite.json",
    }
    for name, artifact_name in prerequisite_artifacts.items():
        if (
            sha256_file(evidence / artifact_name)
            != contract["inputs"][f"{name}_sha256"]
        ):
            raise ValueError(f"E16c artifact prerequisite differs for {name}")
    return contract


def expected_runtime_environment(
    configuration: str, identity: dict[str, Any]
) -> dict[str, Any]:
    if configuration == "normal_repack_workers":
        return {"GGML_CPU_REPACK_SIDECAR": None}
    cpu = identity["cpu"]
    return {
        "GGML_CPU_REPACK_SIDECAR": "one shared verified sidecar",
        "GGML_CPU_REPACK_SIDECAR_EXPERIMENT_ID": identity["experiment_id"],
        "GGML_CPU_REPACK_SIDECAR_MODEL_SHA256": identity["source_model_sha256"],
        "GGML_CPU_REPACK_SIDECAR_SOURCE_COMMIT": identity["llama_cpp_commit"],
        "GGML_CPU_REPACK_SIDECAR_SOURCE_DIFF_SHA256": identity[
            "source_diff_sha256"
        ],
        "GGML_CPU_REPACK_SIDECAR_ARCHITECTURE": cpu["architecture"],
        "GGML_CPU_REPACK_SIDECAR_CPU_FEATURES_SHA256": cpu[
            "common_features_sha256"
        ],
        "GGML_CPU_REPACK_SIDECAR_SVE_BYTES": str(cpu["sve_vector_length_bytes"]),
    }


def validate_recipe(
    recipe: dict[str, Any],
    *,
    contract: dict[str, Any],
    identity: dict[str, Any],
    configuration: str,
    repetition: int,
    worker: int,
) -> None:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    port = contract["mechanism"]["worker_ports"][worker - 1]
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E16c"
        or recipe.get("configuration") != configuration
        or recipe.get("repetition") != repetition
        or recipe.get("worker") != worker
        or recipe.get("port") != port
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
        raise ValueError(
            f"E16c {configuration} repetition {repetition} worker {worker} recipe differs"
        )
    expected = expected_server_argv(
        server,
        model_path,
        candidate=contract["selected"]["candidate"],
        profile_name="e7c_final",
    )
    expected[expected.index("--port") + 1] = str(port)
    expected.extend(
        ["--log-verbosity", str(contract["mechanism"]["proof_log_verbosity"])]
    )
    if recipe.get("argv") != expected:
        raise ValueError("E16c server argv differs from exact E7c")


def validate_process_cpu(
    worker_probe: dict[str, Any], *, expected_pid: int, measured_requests: int
) -> dict[str, float | int]:
    parameters = worker_probe["parameters"]
    result = worker_probe["result"]
    cpu = result.get("server_process_cpu")
    integer_fields = (
        "pid",
        "clock_ticks_per_second",
        "user_ticks",
        "system_ticks",
        "total_ticks",
    )
    if not isinstance(cpu, dict) or any(
        type(cpu.get(field)) is not int for field in integer_fields
    ):
        raise ValueError("E16c server CPU counters are incomplete")
    if parameters.get("server_pid") != expected_pid or cpu["pid"] != expected_pid:
        raise ValueError("E16c server CPU PID binding differs")
    if (
        cpu["clock_ticks_per_second"] <= 0
        or cpu["user_ticks"] < 0
        or cpu["system_ticks"] < 0
        or cpu["total_ticks"] <= 0
        or cpu["total_ticks"] != cpu["user_ticks"] + cpu["system_ticks"]
    ):
        raise ValueError("E16c server CPU counters are invalid")
    elapsed = result.get("elapsed_seconds")
    if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed <= 0:
        raise ValueError("E16c server CPU interval is invalid")
    total_seconds = cpu["total_ticks"] / cpu["clock_ticks_per_second"]
    expected = {
        "user_seconds": cpu["user_ticks"] / cpu["clock_ticks_per_second"],
        "system_seconds": cpu["system_ticks"] / cpu["clock_ticks_per_second"],
        "total_seconds": total_seconds,
        "seconds_per_request": total_seconds / measured_requests,
        "average_cores_used": total_seconds / elapsed,
    }
    for field, value in expected.items():
        observed = cpu.get(field)
        if (
            not isinstance(observed, (int, float))
            or not math.isfinite(observed)
            or observed < 0
            or not math.isclose(float(observed), value, rel_tol=1e-12)
        ):
            raise ValueError(f"E16c server CPU {field} differs")
    if expected["seconds_per_request"] <= 0 or expected["average_cores_used"] <= 0:
        raise ValueError("E16c server CPU interval is empty")
    return {**{field: cpu[field] for field in integer_fields}, **expected}


def parse_sidecar_mapping(path: Path) -> tuple[str, str, str] | None:
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if "pareto64-e16c-sidecar.bin" in line
    ]
    if not lines:
        return None
    if len(lines) != 1:
        raise ValueError(f"{path.parent.name} has multiple sidecar mappings")
    fields = lines[0].split(maxsplit=5)
    if len(fields) != 6:
        raise ValueError(f"{path.parent.name} sidecar mapping is malformed")
    permissions, offset, device, inode, pathname = fields[1:]
    return permissions, offset, f"{device}:{inode}:{pathname}"


def validate_worker(
    cell_dir: Path,
    *,
    contract: dict[str, Any],
    identity: dict[str, Any],
    configuration: str,
    repetition: int,
    worker: int,
    worker_probe: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
    sidecar_index: dict[str, Any],
) -> dict[str, Any]:
    validate_recipe(
        load_object(cell_dir / f"recipe-worker-{worker}.json"),
        contract=contract,
        identity=identity,
        configuration=configuration,
        repetition=repetition,
        worker=worker,
    )
    readiness = load_object(cell_dir / f"readiness-worker-{worker}.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not math.isfinite(ready_ms)
        or ready_ms < 0
        or ready_ms > contract["acceptance"]["maximum_ready_ms_per_worker"]
    ):
        raise ValueError(f"{cell_dir.name} worker {worker} readiness differs")
    probe = validate_probe(
        worker_probe,
        configuration=configuration,
        repetition=repetition,
        config=contract["service"],
        contract=contract,
        tasks=tasks,
        references=references,
        require_selected_quality=False,
    )
    pid = int((cell_dir / f"server-pid-worker-{worker}.txt").read_text().strip())
    cpu = validate_process_cpu(
        worker_probe,
        expected_pid=pid,
        measured_requests=contract["request"]["measured_tasks"],
    )
    process = parse_time_output(
        (cell_dir / f"server-time-worker-{worker}.log").read_text()
    )
    shell_exit = int(
        (cell_dir / f"server-shell-exit-worker-{worker}.txt").read_text().strip()
    )
    smaps = parse_smaps_rollup(cell_dir / f"smaps-rollup-worker-{worker}.txt")
    page_faults = parse_page_faults(
        cell_dir / f"server-time-worker-{worker}.log"
    )
    mapping = parse_sidecar_mapping(
        cell_dir / f"process-maps-worker-{worker}.txt"
    )
    log = (cell_dir / f"server-worker-{worker}.stderr.log").read_text(
        errors="replace"
    )
    mapped = LOADER_MAPPED.findall(log)
    complete = LOADER_COMPLETE.findall(log)
    if configuration == "shared_sidecar_workers":
        verification = load_object(
            cell_dir / f"prelaunch-verification-worker-{worker}.json"
        )
        mechanism_valid = (
            verification.get("status") == "valid_sidecar"
            and verification.get("sidecar_sha256")
            == sidecar_index["sidecar_sha256"]
            and len(mapped) == 1
            and mapped[0][0] == str(sidecar_index["header"]["arena_size_bytes"])
            and mapped[0][2] == str(sidecar_index["header"]["tensor_count"])
            and complete == [str(sidecar_index["header"]["tensor_count"])]
            and mapping is not None
            and mapping[0]
            == contract["acceptance"]["loader_mapping_permissions"]
            and mapping[1] == contract["acceptance"]["loader_mapping_offset_hex"]
        )
    else:
        verification = None
        mechanism_valid = not mapped and not complete and mapping is None
    if (
        shell_exit
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process.get("maximum_rss_kib") is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
        or not mechanism_valid
    ):
        raise ValueError(f"{cell_dir.name} worker {worker} process evidence differs")
    return {
        "worker": worker,
        "ready_ms": float(ready_ms),
        "probe": probe,
        "raw_cases": worker_probe["cases"],
        "process": process,
        "process_cpu": cpu,
        "smaps_rollup_kib": smaps,
        "page_faults": page_faults,
        "server_shell_exit_status": shell_exit,
        "mechanism_valid": mechanism_valid,
        "sidecar_mapping": mapping,
        "prelaunch_verification": verification,
        "prediction_map": {
            case["id"]: case["predicted"] for case in worker_probe["cases"]
        },
    }


def validate_group(
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
    raw_probe = load_object(cell_dir / "probe.json")
    raw_workers = raw_probe.get("workers")
    group = raw_probe.get("group")
    if (
        raw_probe.get("schema_version") != 1
        or raw_probe.get("experiment_id") != "E16c"
        or raw_probe.get("configuration") != configuration
        or raw_probe.get("repetition") != repetition
        or not isinstance(raw_workers, list)
        or len(raw_workers) != contract["execution"]["workers_per_group"]
        or not isinstance(group, dict)
    ):
        raise ValueError(f"{cell_dir.name} dual-probe structure differs")
    workers = [
        validate_worker(
            cell_dir,
            contract=contract,
            identity=identity,
            configuration=configuration,
            repetition=repetition,
            worker=index,
            worker_probe=raw_workers[index - 1],
            tasks=tasks,
            references=references,
            sidecar_index=sidecar_index,
        )
        for index in (1, 2)
    ]
    starts = [item["result"]["measurement_started_ns"] for item in raw_workers]
    completions = [
        item["result"]["measurement_completed_ns"] for item in raw_workers
    ]
    elapsed = (max(completions) - min(starts)) / 1_000_000_000
    measured_requests = sum(item["probe"]["total"] for item in workers)
    cpu_seconds = sum(item["process_cpu"]["total_seconds"] for item in workers)
    expected_group = {
        "workers": 2,
        "measured_requests": measured_requests,
        "elapsed_seconds": elapsed,
        "requests_per_second": measured_requests / elapsed,
        "server_cpu_seconds": cpu_seconds,
        "server_cpu_seconds_per_request": cpu_seconds / measured_requests,
        "average_server_cores_used": cpu_seconds / elapsed,
        "measurement_start_skew_ms": (max(starts) - min(starts)) / 1_000_000,
    }
    for field, expected in expected_group.items():
        observed = group.get(field)
        if type(expected) is int:
            matches = observed == expected
        else:
            matches = isinstance(observed, (int, float)) and math.isclose(
                float(observed), expected, rel_tol=1e-12
            )
        if not matches:
            raise ValueError(f"{cell_dir.name} group {field} differs")
    mappings = [item["sidecar_mapping"] for item in workers]
    same_sidecar_mapping = (
        configuration == "shared_sidecar_workers"
        and mappings[0] is not None
        and mappings[1] is not None
        and mappings[0][2] == mappings[1][2]
    ) or (configuration == "normal_repack_workers" and mappings == [None, None])
    if not same_sidecar_mapping:
        raise ValueError(f"{cell_dir.name} workers do not map the same sidecar inode")
    return {
        "configuration": configuration,
        "repetition": repetition,
        "group": expected_group,
        "workers": workers,
        "summed_post_workload_pss_kib": sum(
            item["smaps_rollup_kib"]["Pss"] for item in workers
        ),
        "summed_post_workload_rss_kib": sum(
            item["smaps_rollup_kib"]["Rss"] for item in workers
        ),
        "group_ready_ms": max(item["ready_ms"] for item in workers),
        "same_sidecar_mapping": same_sidecar_mapping,
        "sidecar_mapping_key": mappings[0][2] if mappings[0] else None,
        "raw_cases": [case for item in workers for case in item["raw_cases"]],
    }


def summarize_configuration(groups: list[dict[str, Any]]) -> dict[str, Any]:
    workers = [worker for group in groups for worker in group["workers"]]
    cases = [case for group in groups for case in group["raw_cases"]]
    predictions = [worker["prediction_map"] for worker in workers]
    return {
        "quality": {
            "correct_per_worker": [worker["probe"]["correct"] for worker in workers],
            "failures_per_worker": [
                worker["probe"]["failures"] for worker in workers
            ],
            "reference_prediction_mismatches_per_worker": [
                worker["probe"]["reference_prediction_mismatches"]
                for worker in workers
            ],
            "predictions_stable_between_workers": all(
                item == predictions[0] for item in predictions[1:]
            ),
        },
        "aggregate_requests_per_second": summarize(
            [group["group"]["requests_per_second"] for group in groups]
        ),
        "http_ms": summarize([float(case["http_ms"]) for case in cases]),
        "encode_ms": summarize([float(case["encode_ms"]) for case in cases]),
        "decode_ms": summarize([float(case["decode_ms"]) for case in cases]),
        "server_cpu_seconds_per_request": summarize(
            [
                group["group"]["server_cpu_seconds_per_request"]
                for group in groups
            ]
        ),
        "summed_post_workload_pss_kib": summarize(
            [float(group["summed_post_workload_pss_kib"]) for group in groups]
        ),
        "summed_post_workload_rss_kib": summarize(
            [float(group["summed_post_workload_rss_kib"]) for group in groups]
        ),
        "group_ready_ms": summarize([group["group_ready_ms"] for group in groups]),
        "measurement_start_skew_ms": summarize(
            [group["group"]["measurement_start_skew_ms"] for group in groups]
        ),
        "groups": groups,
    }


def build_summary_from_contract(
    evidence: Path, contract: dict[str, Any], root: Path, contract_sha256: str
) -> dict[str, Any]:
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
    groups = []
    for index, item in enumerate(contract["execution"]["order"], start=1):
        configuration = item["configuration"]
        repetition = item["repetition"]
        groups.append(
            validate_group(
                evidence
                / "cells"
                / f"{index:02d}-{configuration}-r{repetition}",
                contract=contract,
                identity=identity,
                configuration=configuration,
                repetition=repetition,
                tasks=tasks,
                references=references,
                sidecar_index=sidecar_index,
            )
        )
    performance = {
        name: summarize_configuration(
            [group for group in groups if group["configuration"] == name]
        )
        for name in contract["execution"]["configurations"]
    }
    baseline = performance[contract["execution"]["baseline_configuration"]]
    candidate = performance[contract["execution"]["candidate_configuration"]]
    ratios = {
        "aggregate_throughput": candidate["aggregate_requests_per_second"]["median"]
        / baseline["aggregate_requests_per_second"]["median"],
        "median_http_latency": candidate["http_ms"]["median"]
        / baseline["http_ms"]["median"],
        "p95_http_latency": candidate["http_ms"]["p95"]
        / baseline["http_ms"]["p95"],
        "server_cpu_seconds_per_request": candidate[
            "server_cpu_seconds_per_request"
        ]["median"]
        / baseline["server_cpu_seconds_per_request"]["median"],
        "summed_post_workload_pss": candidate["summed_post_workload_pss_kib"][
            "median"
        ]
        / baseline["summed_post_workload_pss_kib"]["median"],
        "group_readiness": candidate["group_ready_ms"]["median"]
        / baseline["group_ready_ms"]["median"],
    }
    pss_saved_kib = (
        baseline["summed_post_workload_pss_kib"]["median"]
        - candidate["summed_post_workload_pss_kib"]["median"]
    )
    acceptance = contract["acceptance"]
    workers = [worker for group in groups for worker in group["workers"]]
    predictions = [worker["prediction_map"] for worker in workers]
    quality = all(
        worker["probe"]["correct"] == acceptance["correct_per_worker"]
        and worker["probe"]["failures"] == acceptance["request_failures"]
        and worker["probe"]["reference_prediction_mismatches"]
        == acceptance["reference_prediction_mismatches"]
        for worker in workers
    ) and all(item == predictions[0] for item in predictions[1:])
    loader_groups = [
        group
        for group in groups
        if group["configuration"] == contract["execution"]["candidate_configuration"]
    ]
    loader_mapping_keys = [group["sidecar_mapping_key"] for group in loader_groups]
    shared_mapping = (
        all(group["same_sidecar_mapping"] for group in loader_groups)
        and len(set(loader_mapping_keys)) == 1
        and loader_mapping_keys[0] is not None
    )
    final_cleanup = load_object(evidence / "sidecar-cleanup.json")
    final_verification = load_object(evidence / "final-sidecar-verification.json")
    cleanup = (
        final_verification.get("status") == "valid_sidecar"
        and final_verification.get("sidecar_sha256")
        == sidecar_index["sidecar_sha256"]
        and final_cleanup.get("deleted_sidecar_bytes")
        == sidecar_index["sidecar_size_bytes"]
        and final_cleanup.get("deleted_sidecar_sha256")
        == sidecar_index["sidecar_sha256"]
        and final_cleanup.get("sidecar_cleanup_complete") is True
    )
    gates = {
        "native_architecture": platform["architecture"]
        == acceptance["required_architecture"],
        "exact_runner_shape": platform["logical_cpus"]
        == acceptance["required_logical_cpus"]
        and platform["model_name"] == acceptance["required_model_name"],
        "required_cpu_features": set(acceptance["required_common_cpu_features"])
        <= set(identity["cpu"]["common_features"]),
        "exact_quality": quality,
        "shared_read_only_sidecar_mapping": shared_mapping,
        "synchronized_measurement": all(
            group["group"]["measurement_start_skew_ms"]
            <= acceptance["maximum_measurement_start_skew_ms"]
            for group in groups
        ),
        "bounded_cleanup": cleanup,
        "throughput_stability": all(
            point["aggregate_requests_per_second"]["coefficient_of_variation"]
            <= acceptance["maximum_throughput_coefficient_of_variation"]
            for point in performance.values()
        ),
        "throughput_retention": ratios["aggregate_throughput"]
        >= acceptance["minimum_aggregate_throughput_retention_ratio"],
        "median_latency_retention": ratios["median_http_latency"]
        <= acceptance["maximum_median_http_latency_ratio"],
        "p95_latency_retention": ratios["p95_http_latency"]
        <= acceptance["maximum_p95_http_latency_ratio"],
        "cpu_retention": ratios["server_cpu_seconds_per_request"]
        <= acceptance["maximum_server_cpu_seconds_per_request_ratio"],
        "summed_pss_ratio": ratios["summed_post_workload_pss"]
        <= acceptance["maximum_summed_post_workload_pss_ratio"],
        "summed_pss_absolute_saving": pss_saved_kib
        >= acceptance["minimum_summed_post_workload_pss_saved_kib"],
        "readiness_retention": ratios["group_readiness"]
        <= acceptance["maximum_group_readiness_ratio"],
    }
    promoted = all(gates.values())
    return {
        "schema_version": 1,
        "experiment_id": "E16c",
        "contract_sha256": contract_sha256,
        "status": (
            "valid_shared_sidecar_workers_promoted"
            if promoted
            else "valid_shared_sidecar_workers_no_promotion"
        ),
        "promoted": promoted,
        "failed_gates": sorted(name for name, passed in gates.items() if not passed),
        "gates": gates,
        "ratios": ratios,
        "summed_post_workload_pss_saved_kib": pss_saved_kib,
        "platform": platform,
        "source_build": source_build,
        "sidecar_identity": identity,
        "construction": construction,
        "final_sidecar_verification": final_verification,
        "sidecar_cleanup": final_cleanup,
        "performance": performance,
        "groups": groups,
        "measurement_boundary": contract["measurement_boundary"],
        "claim_boundary": contract["claim_boundary"],
        "decision": {
            "selected_configuration": (
                contract["execution"]["candidate_configuration"]
                if promoted
                else contract["execution"]["baseline_configuration"]
            ),
            "multi_process_physical_sharing_claim_permitted": promoted,
            "per_process_rss_reduction_claim_permitted": False,
            "sidecar_construction_cost_included_in_steady_state": False,
            "post_result_gate_change_permitted": False,
        },
    }


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    return build_summary_from_contract(
        evidence, contract, root, sha256_file(contract_path)
    )


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
