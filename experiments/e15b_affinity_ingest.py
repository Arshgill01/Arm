#!/usr/bin/env python3
"""Validate the confirmatory E15b two-CPU-affinity scheduler experiment."""

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
    from experiments.e15a_split_scheduler_ingest import (
        evaluate,
        expected_server_argv,
        summarize_performance,
        validate_runtime,
    )
    from experiments.e15b_affinity_freeze import INPUT_PATHS
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
    from e15a_split_scheduler_ingest import (
        evaluate,
        expected_server_argv,
        summarize_performance,
        validate_runtime,
    )
    from e15b_affinity_freeze import INPUT_PATHS


ARTIFACT_INPUTS = {
    "manifest": "selected-manifest.json",
    "models": "models-manifest.json",
    "tasks": "tasks-manifest.json",
    "e9a_contract": "e9a-contract.json",
    "e9a_manifest": "e9a-manifest.json",
    "e15a_contract": "e15a-contract.json",
    "e15a_failure": "e15a-failure.json",
    "e15a_failure_report": "e15a-failure-report.md",
    "probe": "probe.py",
    "cell_runner": "cell-runner.sh",
    "freeze": "freeze.py",
    "ingest": "ingest.py",
    "test": "test.py",
}


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E15b"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("contract does not identify E15b")
    for name, relative in INPUT_PATHS.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if (
            sha256_file(root / relative) != expected
            or sha256_file(evidence / ARTIFACT_INPUTS[name]) != expected
            or sha256_file(evidence / "frozen-inputs" / relative) != expected
        ):
            raise ValueError(f"E15b input differs for {name}")
    prerequisite = contract["prerequisites"]["e9a"]
    if (
        sha256_file(evidence / "e9a-workflow-summary.json")
        != prerequisite["workflow_summary_sha256"]
        or load_object(evidence / "e9a-workflow-summary.json").get("status")
        != prerequisite["required_status"]
    ):
        raise ValueError("E15b E9a workflow prerequisite differs")
    return contract


def expand_cpu_list(value: str) -> list[int]:
    cpus: set[int] = set()
    for item in value.split(","):
        bounds = item.split("-", 1)
        if not bounds[0].isdigit() or (
            len(bounds) == 2 and not bounds[1].isdigit()
        ):
            raise ValueError("invalid Linux CPU-list evidence")
        start = int(bounds[0])
        end = int(bounds[-1])
        if end < start:
            raise ValueError("descending Linux CPU-list evidence")
        cpus.update(range(start, end + 1))
    if not cpus:
        raise ValueError("empty Linux CPU-list evidence")
    return sorted(cpus)


def validate_affinity_record(
    record: dict[str, Any], *, expected_ids: list[int], expected_pid: int | None = None
) -> None:
    if expected_pid is not None and record.get("pid") != expected_pid:
        raise ValueError("E15b affinity PID differs")
    if record.get("os_sched_getaffinity") != expected_ids:
        raise ValueError("E15b process affinity differs")
    proc_list = record.get("proc_status_cpus_allowed_list")
    if proc_list is not None and (
        not isinstance(proc_list, str) or expand_cpu_list(proc_list) != expected_ids
    ):
        raise ValueError("E15b proc-status affinity differs")
    thread_affinities = record.get("thread_affinities")
    if thread_affinities is not None:
        if not isinstance(thread_affinities, list) or not thread_affinities:
            raise ValueError("E15b server thread affinity evidence is empty")
        for thread in thread_affinities:
            if (
                type(thread.get("tid")) is not int
                or thread.get("os_sched_getaffinity") != expected_ids
                or expand_cpu_list(thread.get("proc_status_cpus_allowed_list", ""))
                != expected_ids
            ):
                raise ValueError("E15b server thread escaped the frozen affinity")


def validate_cell(
    cell_dir: Path,
    *,
    configuration: str,
    repetition: int,
    contract: dict[str, Any],
    tasks: list[dict[str, Any]],
    references: dict[str, str],
    affinity_ids: list[int],
    affinity_cpu_list: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = contract["execution"]["configurations"][configuration]
    recipe = load_object(cell_dir / "recipe.json")
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    launch_prefix = ["taskset", "--cpu-list", affinity_cpu_list]
    if (
        recipe.get("experiment_id") != "E15b"
        or recipe.get("configuration") != configuration
        or recipe.get("repetition") != repetition
        or recipe.get("affinity_cpu_list") != affinity_cpu_list
        or recipe.get("affinity_cpu_ids") != affinity_ids
        or recipe.get("server_launch_prefix") != launch_prefix
        or recipe.get("client_launch_prefix") != launch_prefix
        or recipe.get("service") != config
        or model.get("candidate") != contract["selected"]["candidate"]
        or model.get("sha256") != contract["selected"]["model_sha256"]
        or model.get("size_bytes") != contract["selected"]["model_size_bytes"]
        or not isinstance(server, str)
        or not server.endswith("/runtime-files/bin/llama-server")
        or not isinstance(model_path, str)
        or not model_path.endswith(contract["selected"]["path"])
        or contract["runtime"]["source"]["commit"][:9]
        not in recipe.get("server_version", "")
        or recipe.get("argv")
        != expected_server_argv(server, model_path, contract, configuration)
    ):
        raise ValueError(f"{cell_dir.name} E15b recipe differs")
    timed = (cell_dir / "server-time.log").read_text(errors="replace")
    command_lines = [
        line for line in timed.splitlines() if "Command being timed:" in line
    ]
    required_command = ["taskset", "--cpu-list", affinity_cpu_list, *recipe["argv"]]
    if len(command_lines) != 1 or not all(
        argument in command_lines[0] for argument in required_command
    ):
        raise ValueError(f"{cell_dir.name} affinity server command differs")
    client_process = parse_time_output((cell_dir / "client-time.log").read_text())
    client_command = (cell_dir / "client-time.log").read_text(errors="replace")
    if (
        client_process.get("exit_status") != 0
        or f"taskset --cpu-list {affinity_cpu_list}" not in client_command
        or "experiments/e5b_inference_probe.py" not in client_command
    ):
        raise ValueError(f"{cell_dir.name} affinity client command differs")
    readiness = load_object(cell_dir / "readiness.json")
    ready_ms = readiness.get("ready_ms")
    if (
        readiness.get("status") != "ok"
        or not isinstance(ready_ms, (int, float))
        or not math.isfinite(ready_ms)
        or not 0 <= ready_ms <= contract["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError(f"{cell_dir.name} readiness differs")
    raw_probe = load_object(cell_dir / "probe.json")
    probe = validate_probe(
        raw_probe,
        configuration=configuration,
        repetition=repetition,
        config={
            "client_concurrency": config["client_concurrency"],
            "prompt_cache": config["request_cache_prompt"],
            "warmup_slot_ids": config["warmup_slot_ids"],
        },
        contract=contract,
        tasks=tasks,
        references=references,
    )
    cases = raw_probe["cases"]
    if any(
        type(case.get("cached_tokens")) is not int
        or case["cached_tokens"]
        < contract["acceptance"]["minimum_cached_tokens_per_request"]
        for case in cases
    ):
        raise ValueError(f"{cell_dir.name} cache mechanism differs")
    process_cpu = validate_process_cpu(
        raw_probe,
        cell_dir=cell_dir,
        measured_requests=contract["request"]["measured_tasks"],
    )
    server_pid = int((cell_dir / "server-pid.txt").read_text().strip())
    before = load_object(cell_dir / "server-affinity-before.json")
    after = load_object(cell_dir / "server-affinity-after.json")
    client = load_object(cell_dir / "client-affinity.json")
    validate_affinity_record(before, expected_ids=affinity_ids, expected_pid=server_pid)
    validate_affinity_record(after, expected_ids=affinity_ids, expected_pid=server_pid)
    validate_affinity_record(client, expected_ids=affinity_ids)
    if client.get("expected_cpu_list") != affinity_cpu_list:
        raise ValueError(f"{cell_dir.name} client affinity declaration differs")
    process = parse_time_output(timed)
    shell_exit = int((cell_dir / "server-shell-exit.txt").read_text().strip())
    slots = json.loads((cell_dir / "slots.json").read_text())
    if (
        shell_exit
        not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or process.get("maximum_rss_kib") is None
        or process["maximum_rss_kib"]
        > contract["acceptance"]["maximum_process_rss_kib"]
        or not isinstance(slots, list)
        or len(slots) != config["server_parallel_slots"]
        or "llamacpp:" not in (cell_dir / "metrics.txt").read_text()
    ):
        raise ValueError(f"{cell_dir.name} process evidence differs")
    return (
        {
            "configuration": configuration,
            "repetition": repetition,
            "affinity_cpu_ids": affinity_ids,
            "ready_ms": float(ready_ms),
            "probe": probe,
            "server_process_cpu": process_cpu,
            "process": process,
            "client_process": client_process,
            "server_shell_exit_status": shell_exit,
            "slots_observed": len(slots),
            "server_affinity_before": before,
            "server_affinity_after": after,
            "client_affinity": client,
        },
        cases,
    )


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    runtime = validate_runtime(evidence, contract)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    host_affinity = load_object(evidence / "host-affinity.json")
    available_ids = host_affinity.get("available_cpu_ids")
    selected_ids = host_affinity.get("selected_cpu_ids")
    selected_list = host_affinity.get("selected_cpu_list")
    required_count = contract["acceptance"]["required_affinity_cpu_count"]
    if (
        platform["architecture"] != contract["acceptance"]["required_architecture"]
        or platform["model_name"] != contract["acceptance"]["required_model_name"]
        or not isinstance(platform["logical_cpus"], int)
        or platform["logical_cpus"]
        < contract["acceptance"]["minimum_host_logical_cpus"]
        or not isinstance(available_ids, list)
        or any(type(value) is not int for value in available_ids)
        or len(available_ids) < required_count
        or selected_ids != sorted(available_ids)[:required_count]
        or selected_list != ",".join(str(value) for value in selected_ids)
    ):
        raise ValueError("E15b native host or selected affinity differs")
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if (
        len(model_line) != 2
        or model_line[0] != contract["selected"]["model_sha256"]
        or int((evidence / "model-size.txt").read_text())
        != contract["selected"]["model_size_bytes"]
    ):
        raise ValueError("E15b model identity differs")
    tasks = load_tasks(load_object(root / contract["inputs"]["tasks_path"]))
    references = reference_predictions(
        load_object(root / contract["inputs"]["manifest_path"]),
        contract["selected"]["candidate"],
    )
    order = contract["execution"]["order"]
    expected = {
        (name, repetition)
        for name in contract["execution"]["configurations"]
        for repetition in range(
            1, contract["execution"]["repetitions_per_configuration"] + 1
        )
    }
    if (
        len(order) != len(expected)
        or {(item["configuration"], item["repetition"]) for item in order}
        != expected
    ):
        raise ValueError("E15b balanced execution order differs")
    cells = []
    samples = {name: [] for name in contract["execution"]["configurations"]}
    for index, item in enumerate(order, start=1):
        name = item["configuration"]
        repetition = item["repetition"]
        cell, raw = validate_cell(
            evidence / "cells" / f"{index:02d}-{name}-r{repetition}",
            configuration=name,
            repetition=repetition,
            contract=contract,
            tasks=tasks,
            references=references,
            affinity_ids=selected_ids,
            affinity_cpu_list=selected_list,
        )
        cells.append(cell)
        samples[name].extend({**case, "repetition": repetition} for case in raw)
    performance = summarize_performance(cells, samples, contract)
    decision = evaluate(performance, contract)
    return {
        "schema_version": 1,
        "experiment_id": "E15b",
        "status": (
            "valid_affinity_split_scheduler_promoted"
            if decision["passed"]
            else "valid_affinity_split_scheduler_no_promotion"
        ),
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "host_affinity": host_affinity,
        "runtime": runtime,
        "model": contract["selected"],
        "performance": performance,
        "decision": decision,
        "validation": {
            "native_arm64_same_job": True,
            "exact_e9a_runtime_reused": True,
            "exact_model_and_workload": True,
            "fresh_server_per_cell": True,
            "reverse_balanced_six_repetitions": True,
            "server_and_client_two_cpu_affinity": True,
            "all_server_threads_two_cpu_affinity": True,
            "exact_quality": all(
                profile["quality"]["exact_selected_predictions"]
                for profile in performance.values()
            ),
            "zero_request_failures": True,
            "four_cpu_result_seen_before_freeze": True,
            "weighted_score_used": False,
            "energy_claim_allowed": False,
        },
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
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
