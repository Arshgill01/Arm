#!/usr/bin/env python3
"""Validate and summarize E13b fail-closed cache-certificate evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e9a_ingest import expected_server_argv
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import load_object, sha256_file
    from e9a_ingest import expected_server_argv


def finite(value: Any, *, nonnegative: bool = False) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("E13b expected a finite number")
    number = float(value)
    if nonnegative and number < 0:
        raise ValueError("E13b expected a nonnegative number")
    return number


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("schema_version") != 1 or contract.get("experiment_id") != "E13b":
        raise ValueError("contract does not identify E13b")
    if load_object(evidence / "contract.json") != contract:
        raise ValueError("artifact contract differs from frozen E13b")
    for name, item in contract["inputs"].items():
        path = root / item["path"]
        if sha256_file(path) != item["sha256"]:
            raise ValueError(f"E13b frozen input differs for {name}")
    if (
        sha256_file(evidence / "calibration-manifest.json")
        != contract["calibration"]["manifest_sha256"]
        or load_object(evidence / "calibration-manifest.json")
        != load_object(root / contract["inputs"]["calibration_manifest"]["path"])
        or load_object(evidence / "calibration-summary.json")
        != load_object(evidence / "calibration-manifest.json")
    ):
        raise ValueError("E13b calibration replay differs")
    return contract


def validate_runtime(evidence: Path, contract: dict[str, Any]) -> dict[str, Any]:
    build = evidence / "build"
    closure = load_object(build / "runtime-closure.json")
    runtime_root = build / "runtime-files"
    for item in closure.get("files", []):
        path = runtime_root / item["relative_path"]
        if (
            not path.is_file()
            or path.stat().st_size != item["size_bytes"]
            or sha256_file(path) != item["sha256"]
        ):
            raise ValueError("E13b reused runtime closure differs")
    server = runtime_root / closure["server_relative_path"]
    if sha256_file(server) != contract["acceptance"]["server_binary_sha256"]:
        raise ValueError("E13b server binary differs")
    dependencies = closure.get("runtime_dependencies", [])
    basenames = sorted({Path(item["resolved_path"]).name for item in dependencies})
    if {"libssl.so.3", "libcrypto.so.3"}.intersection(basenames):
        raise ValueError("E13b runtime unexpectedly contains OpenSSL")
    source = load_object(evidence / "source.json")
    if (
        source.get("commit") != contract["service"]["source_commit"]
        or source.get("tag") != contract["service"]["source_tag"]
        or sha256_file(evidence / "source-diff.patch")
        != contract["service"]["source_diff_sha256"]
    ):
        raise ValueError("E13b source proof differs from E7c")
    return {
        "source": source,
        "server_binary_sha256": sha256_file(server),
        "runtime_closure": closure,
        "dynamic_dependency_basenames": basenames,
        "reused_calibration_run": contract["calibration"]["run_id"],
    }


def expected_trace(contract: dict[str, Any]) -> list[dict[str, Any]]:
    workload = contract["workload"]
    trace: list[dict[str, Any]] = []
    global_index = 0
    for point_index, point in enumerate(workload["point_order"]):
        cardinality = point["prefix_cardinality"]
        length = point["shared_prefix_tokens"]
        warmup_spec = workload["point_warmups"][point_index]
        if any(
            warmup_spec[name] != point[name]
            for name in ("prefix_cardinality", "shared_prefix_tokens")
        ):
            raise ValueError("E13b frozen warmup point differs")
        for warmup in warmup_spec["requests"]:
            trace.append(
                {
                    "global_index": global_index,
                    "phase": "point_warmup",
                    "point_index": point_index,
                    "prefix_cardinality": cardinality,
                    "shared_prefix_tokens": length,
                    "task_id": warmup["task_id"],
                    "prefix_marker": warmup["prefix_marker"],
                    "prefix_marker_index": warmup["prefix_marker_index"],
                    "prompt_sha256": warmup["prompt_sha256"],
                }
            )
            global_index += 1
        measured = warmup_spec["measured_requests"]
        if [item["task_id"] for item in measured] != workload["measured_task_ids"]:
            raise ValueError("E13b measured task sequence differs")
        for request in measured:
            trace.append(
                {
                    "global_index": global_index,
                    "phase": "measured",
                    "point_index": point_index,
                    "prefix_cardinality": cardinality,
                    "shared_prefix_tokens": length,
                    "task_id": request["task_id"],
                    "prefix_marker": request["prefix_marker"],
                    "prefix_marker_index": request["prefix_marker_index"],
                    "prompt_sha256": request["prompt_sha256"],
                }
            )
            global_index += 1
    if len(trace) != workload["trace_requests"]:
        raise ValueError("E13b expected trace count differs")
    return trace


def validate_recipe(recipe: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E13b"
        or recipe.get("profile_name") != "e7c_final"
        or recipe.get("service") != contract["service"]
        or model.get("candidate") != contract["selected"]["candidate"]
        or model.get("sha256") != contract["selected"]["model_sha256"]
        or model.get("size_bytes") != contract["selected"]["model_size_bytes"]
        or not isinstance(server, str)
        or not server.endswith("/bin/llama-server")
        or not isinstance(model_path, str)
        or not model_path.endswith(".gguf")
        or contract["service"]["source_commit"][:9]
        not in recipe.get("server_version", "")
    ):
        raise ValueError("E13b recipe differs from frozen E7c")
    expected = expected_server_argv(
        server,
        model_path,
        candidate=contract["selected"]["candidate"],
        profile_name="e7c_final",
    )
    if recipe.get("argv") != expected:
        raise ValueError("E13b server argv differs from E7c")
    return recipe


def validate_process_cpu(
    value: Any, *, pid: int, requests: int, elapsed: float
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("E13b process CPU evidence is missing")
    for name in (
        "pid",
        "clock_ticks_per_second",
        "user_ticks",
        "system_ticks",
        "total_ticks",
    ):
        if type(value.get(name)) is not int:
            raise ValueError("E13b process CPU counter is not integral")
    if (
        value["pid"] != pid
        or value["clock_ticks_per_second"] <= 0
        or value["total_ticks"] <= 0
        or value["total_ticks"] != value["user_ticks"] + value["system_ticks"]
    ):
        raise ValueError("E13b process CPU counter differs")
    total = value["total_ticks"] / value["clock_ticks_per_second"]
    expected = {
        "user_seconds": value["user_ticks"] / value["clock_ticks_per_second"],
        "system_seconds": value["system_ticks"] / value["clock_ticks_per_second"],
        "total_seconds": total,
        "seconds_per_request": total / requests,
        "average_cores_used": total / elapsed,
    }
    for name, number in expected.items():
        if not math.isclose(
            finite(value.get(name), nonnegative=True), number, rel_tol=1e-12
        ):
            raise ValueError(f"E13b process CPU {name} differs")
    return {**value, **expected}


def validate_cell(
    cell_dir: Path,
    contract: dict[str, Any],
    policy: str,
    repetition: int,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    recipe = validate_recipe(load_object(cell_dir / "recipe.json"), contract)
    timed_text = (cell_dir / "server-time.log").read_text(errors="replace")
    commands = [
        line for line in timed_text.splitlines() if "Command being timed:" in line
    ]
    if len(commands) != 1 or not all(
        argument in commands[0] for argument in recipe["argv"]
    ):
        raise ValueError("E13b timed command differs from recipe")
    process = parse_time_output(timed_text)
    acceptance = contract["acceptance"]
    if process["exit_status"] not in acceptance["accepted_server_shell_exit_statuses"]:
        raise ValueError("E13b process resource evidence differs")
    if process["maximum_rss_kib"] is None:
        raise ValueError("E13b process RSS evidence is missing")
    readiness = load_object(cell_dir / "readiness.json")
    ready_ms = finite(readiness.get("ready_ms"), nonnegative=True)
    if readiness.get("status") != "ok":
        raise ValueError("E13b readiness evidence differs")
    probe = load_object(cell_dir / "probe.json")
    parameters = probe.get("parameters", {})
    pid = int((cell_dir / "server-pid.txt").read_text().strip())
    expected_parameters = {
        "policy": policy,
        "repetition": repetition,
        "server_pid": pid,
        "trace_requests": contract["workload"]["trace_requests"],
        "measured_requests": contract["workload"]["measured_requests"],
        "client_concurrency": contract["workload"]["client_concurrency"],
        "seed": contract["workload"]["seed"],
        "maximum_output_tokens": contract["workload"]["maximum_output_tokens"],
    }
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E13b"
        or parameters != expected_parameters
    ):
        raise ValueError("E13b probe parameters differ")
    records = probe.get("records")
    if not isinstance(records, list) or len(records) != len(trace):
        raise ValueError("E13b probe trace is incomplete")
    certified = {
        item["prompt_sha256"] for item in contract["policy"]["certified_allowlist"]
    }
    denied = {item["prompt_sha256"] for item in contract["policy"]["fallback_denylist"]}
    failures = 0
    uncached_cache_reuse_violations = 0
    for observed, expected in zip(records, trace, strict=True):
        if any(observed.get(name) != value for name, value in expected.items()):
            raise ValueError("E13b trace identity differs")
        fingerprint = observed.get("prompt_sha256")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError("E13b prompt fingerprint is invalid")
        if policy == "all_uncached":
            expected_cache, expected_decision = False, "baseline_uncached"
        elif fingerprint in certified:
            expected_cache, expected_decision = True, "certified_cache"
        elif fingerprint in denied:
            expected_cache, expected_decision = False, "calibration_fallback"
        else:
            expected_cache, expected_decision = False, "unknown_fallback"
        if (
            observed.get("cache_prompt") is not expected_cache
            or observed.get("decision") != expected_decision
            or not isinstance(observed.get("prompt_tokens"), int)
            or not 0
            < observed["prompt_tokens"]
            <= contract["prompt_construction"]["maximum_prompt_tokens"]
        ):
            raise ValueError("E13b cache decision differs from certificate")
        finite(observed.get("http_ms"), nonnegative=True)
        successful = (
            observed.get("http_status") == 200
            and observed.get("error") is None
            and isinstance(observed.get("response"), str)
        )
        if successful:
            for name in (
                "encode_ms",
                "decode_ms",
                "cached_tokens",
                "evaluated_prompt_tokens",
                "response_tokens_cached",
                "response_tokens_evaluated",
            ):
                finite(observed.get(name), nonnegative=True)
            uncached_cache_reuse_violations += (
                not expected_cache
                and observed["cached_tokens"]
                != acceptance["required_fallback_cached_tokens"]
            )
        else:
            failures += 1
    result = probe.get("result", {})
    elapsed = finite(result.get("elapsed_seconds"), nonnegative=True)
    rps = finite(result.get("requests_per_second"), nonnegative=True)
    if (
        elapsed <= 0
        or not math.isclose(rps, len(records) / elapsed, rel_tol=1e-12)
        or result.get("request_failures") != failures
    ):
        raise ValueError("E13b probe aggregate differs")
    process_cpu = validate_process_cpu(
        probe.get("process_cpu"), pid=pid, requests=len(records), elapsed=elapsed
    )
    decision_counts = {
        name: sum(record["decision"] == name for record in records)
        for name in (
            "baseline_uncached",
            "certified_cache",
            "calibration_fallback",
            "unknown_fallback",
        )
    }
    if result.get("decision_counts") != decision_counts:
        raise ValueError("E13b decision summary differs")
    measured_certified = [
        record
        for record in records
        if record["phase"] == "measured" and record["decision"] == "certified_cache"
    ]
    hit_count = sum(
        isinstance(record.get("cached_tokens"), (int, float))
        and record["cached_tokens"] >= record["shared_prefix_tokens"]
        for record in measured_certified
    )
    hit_fraction = hit_count / len(measured_certified) if measured_certified else 0.0
    return {
        "policy": policy,
        "repetition": repetition,
        "recipe": recipe,
        "readiness_ms": ready_ms,
        "process": process,
        "process_cpu": process_cpu,
        "elapsed_seconds": elapsed,
        "requests_per_second": rps,
        "request_failures": failures,
        "uncached_cache_reuse_violations": uncached_cache_reuse_violations,
        "decision_counts": decision_counts,
        "certified_measured_cache_hit_fraction": hit_fraction,
        "records": records,
    }


def count_output_mismatches(
    left: list[dict[str, Any]], right: list[dict[str, Any]]
) -> int:
    if len(left) != len(right):
        raise ValueError("E13b comparison traces differ in length")
    mismatches = 0
    for a, b in zip(left, right, strict=True):
        if (
            a["global_index"] != b["global_index"]
            or a["prompt_sha256"] != b["prompt_sha256"]
        ):
            raise ValueError("E13b comparison prompt identity differs")
        mismatches += a["response"] != b["response"]
    return mismatches


def aggregate_policy(cells: list[dict[str, Any]]) -> dict[str, Any]:
    records = [record for cell in cells for record in cell["records"]]
    requests = len(records)
    elapsed = sum(cell["elapsed_seconds"] for cell in cells)
    cpu = sum(cell["process_cpu"]["total_seconds"] for cell in cells)
    encode_values = [
        float(record["encode_ms"])
        for record in records
        if isinstance(record.get("encode_ms"), (int, float))
        and math.isfinite(record["encode_ms"])
    ]
    decode_values = [
        float(record["decode_ms"])
        for record in records
        if isinstance(record.get("decode_ms"), (int, float))
        and math.isfinite(record["decode_ms"])
    ]
    return {
        "repetitions": len(cells),
        "requests": requests,
        "elapsed_seconds": elapsed,
        "requests_per_second": requests / elapsed,
        "throughput_repetitions": summarize(
            [cell["requests_per_second"] for cell in cells]
        ),
        "http_ms": summarize([float(record["http_ms"]) for record in records]),
        "encode_ms": summarize(encode_values) if encode_values else None,
        "decode_ms": summarize(decode_values) if decode_values else None,
        "cpu_seconds_per_request": cpu / requests,
        "maximum_rss_kib": max(cell["process"]["maximum_rss_kib"] for cell in cells),
        "readiness_ms": summarize([cell["readiness_ms"] for cell in cells]),
        "request_failures": sum(cell["request_failures"] for cell in cells),
    }


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E13b evidence is not native Arm64")
    runtime = validate_runtime(evidence, contract)
    trace = expected_trace(contract)
    cells: list[dict[str, Any]] = []
    for index, expected in enumerate(contract["execution"]["cell_order"], start=1):
        cell_dir = (
            evidence
            / "cells"
            / f"{index:02d}-{expected['policy']}-r{expected['repetition']}"
        )
        cells.append(
            validate_cell(
                cell_dir,
                contract,
                expected["policy"],
                expected["repetition"],
                trace,
            )
        )
    by_key = {(cell["policy"], cell["repetition"]): cell for cell in cells}
    baseline_repeat_mismatches = count_output_mismatches(
        by_key[("all_uncached", 1)]["records"],
        by_key[("all_uncached", 2)]["records"],
    )
    controller_repeat_mismatches = count_output_mismatches(
        by_key[("certificate", 1)]["records"],
        by_key[("certificate", 2)]["records"],
    )
    controller_vs_baseline_mismatches = sum(
        count_output_mismatches(
            by_key[("all_uncached", repetition)]["records"],
            by_key[("certificate", repetition)]["records"],
        )
        for repetition in (1, 2)
    )
    baseline = aggregate_policy(
        [by_key[("all_uncached", repetition)] for repetition in (1, 2)]
    )
    controller = aggregate_policy(
        [by_key[("certificate", repetition)] for repetition in (1, 2)]
    )
    ratios = {
        "throughput": controller["requests_per_second"]
        / baseline["requests_per_second"],
        "p95_http_latency": controller["http_ms"]["p95"] / baseline["http_ms"]["p95"],
        "cpu_seconds_per_request": controller["cpu_seconds_per_request"]
        / baseline["cpu_seconds_per_request"],
    }
    expected_decisions = contract["execution"]["expected_controller_requests_per_trace"]
    decision_counts_match = all(
        by_key[("certificate", repetition)]["decision_counts"]
        == {
            "baseline_uncached": 0,
            "certified_cache": expected_decisions["certified_cache"],
            "calibration_fallback": expected_decisions["calibration_fallback"],
            "unknown_fallback": expected_decisions["unknown_fallback"],
        }
        for repetition in (1, 2)
    )
    acceptance = contract["acceptance"]
    gates = {
        "native_arm64": True,
        "exact_e7c_service": True,
        "zero_request_failures": baseline["request_failures"] == 0
        and controller["request_failures"] == 0,
        "uncached_requests_reused_zero_tokens": all(
            cell["uncached_cache_reuse_violations"] == 0 for cell in cells
        ),
        "exact_baseline_repeat_outputs": baseline_repeat_mismatches
        == acceptance["exact_baseline_repeat_mismatches"],
        "exact_controller_repeat_outputs": controller_repeat_mismatches
        == acceptance["exact_controller_repeat_mismatches"],
        "exact_controller_matches_uncached": controller_vs_baseline_mismatches
        == acceptance["exact_controller_vs_uncached_mismatches"],
        "frozen_decision_counts": decision_counts_match,
        "certified_cache_mechanism": min(
            by_key[("certificate", repetition)]["certified_measured_cache_hit_fraction"]
            for repetition in (1, 2)
        )
        >= acceptance["minimum_certified_measured_cache_hit_fraction"],
        "baseline_throughput_stable": baseline["throughput_repetitions"][
            "coefficient_of_variation"
        ]
        <= acceptance["maximum_throughput_coefficient_of_variation"],
        "controller_throughput_stable": controller["throughput_repetitions"][
            "coefficient_of_variation"
        ]
        <= acceptance["maximum_throughput_coefficient_of_variation"],
        "throughput": ratios["throughput"] >= acceptance["minimum_throughput_ratio"],
        "p95_http_latency": ratios["p95_http_latency"]
        <= acceptance["maximum_p95_http_latency_ratio"],
        "cpu_seconds_per_request": ratios["cpu_seconds_per_request"]
        <= acceptance["maximum_cpu_seconds_per_request_ratio"],
        "rss": max(baseline["maximum_rss_kib"], controller["maximum_rss_kib"])
        <= acceptance["maximum_process_rss_kib"],
        "startup": max(cell["readiness_ms"] for cell in cells)
        <= acceptance["maximum_ready_ms"],
    }
    eligible = all(gates.values())
    fallback_rate = (
        expected_decisions["calibration_fallback"]
        + expected_decisions["unknown_fallback"]
    ) / contract["workload"]["trace_requests"]
    return {
        "schema_version": 1,
        "experiment_id": "E13b",
        "status": "valid_certified_cache_policy"
        if eligible
        else "valid_cache_certificate_rejected",
        "eligible": eligible,
        "contract_sha256": sha256_file(contract_path),
        "scope": contract["scope"],
        "platform": platform,
        "runtime": runtime,
        "calibration": contract["calibration"],
        "policy": {
            "certified_fingerprints": len(contract["policy"]["certified_allowlist"]),
            "fallback_fingerprints": len(contract["policy"]["fallback_denylist"]),
            "unknown_policy": contract["policy"]["unknown_policy"],
            "fallback_rate": fallback_rate,
            "expected_controller_requests_per_trace": expected_decisions,
        },
        "quality": {
            "baseline_repeat_mismatches": baseline_repeat_mismatches,
            "controller_repeat_mismatches": controller_repeat_mismatches,
            "controller_vs_uncached_mismatches": controller_vs_baseline_mismatches,
        },
        "baseline": baseline,
        "controller": controller,
        "ratios": ratios,
        "gates": gates,
        "cells": cells,
        "provenance": load_object(evidence / "github.json"),
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
