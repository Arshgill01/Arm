#!/usr/bin/env python3
"""Validate composed E19a cache-certificate and shared-arena evidence."""

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
    from experiments.e13b_ingest import (
        count_output_mismatches,
        expected_trace,
        finite,
        validate_process_cpu,
    )
    from experiments.e16a_ingest import validate_source_build
    from experiments.e16b_ingest import (
        LOADER_COMPLETE,
        LOADER_MAPPED,
        parse_smaps_rollup,
        validate_construction,
    )
    from experiments.e19a_freeze import INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import load_object, sha256_file
    from e9a_ingest import expected_server_argv
    from e13b_ingest import (
        count_output_mismatches,
        expected_trace,
        finite,
        validate_process_cpu,
    )
    from e16a_ingest import validate_source_build
    from e16b_ingest import (
        LOADER_COMPLETE,
        LOADER_MAPPED,
        parse_smaps_rollup,
        validate_construction,
    )
    from e19a_freeze import INPUT_PATHS


def validate_inputs(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E19a"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E19a contract differs")
    for name, relative in INPUT_PATHS.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if (
            sha256_file(root / relative) != expected
            or sha256_file(evidence / "frozen-inputs" / relative) != expected
        ):
            raise ValueError(f"E19a frozen input differs for {name}")
    return contract


def expected_environment(identity: dict[str, Any]) -> dict[str, Any]:
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
    contract: dict[str, Any],
    identity: dict[str, Any],
    policy: str,
    repetition: int,
    worker: int,
) -> dict[str, Any]:
    server = recipe.get("server_path")
    model = recipe.get("model", {})
    model_path = model.get("path")
    port = contract["mechanism"]["worker_ports"][worker - 1]
    if (
        recipe.get("schema_version") != 1
        or recipe.get("experiment_id") != "E19a"
        or recipe.get("policy") != policy
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
        or recipe.get("runtime_environment") != expected_environment(identity)
    ):
        raise ValueError(f"E19a {policy} r{repetition} worker {worker} recipe differs")
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
        raise ValueError("E19a server argv differs")
    return recipe


def sidecar_mapping(path: Path) -> tuple[str, str, str] | None:
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if "pareto64-e19a-sidecar.bin" in line
    ]
    if not lines:
        return None
    if len(lines) != 1:
        raise ValueError("E19a worker has multiple sidecar mappings")
    fields = lines[0].split(maxsplit=5)
    if len(fields) != 6:
        raise ValueError("E19a sidecar mapping is malformed")
    permissions, offset, device, inode, pathname = fields[1:]
    return permissions, offset, f"{device}:{inode}:{pathname}"


def expected_trace_with_workers(contract: dict[str, Any]) -> list[dict[str, Any]]:
    trace = expected_trace(contract)
    for item in trace:
        item["worker"] = 1 + (
            (item["point_index"] + item["prefix_marker_index"]) % 2
        )
    return trace


def validate_records(
    records: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    contract: dict[str, Any],
    policy: str,
) -> dict[str, Any]:
    if len(records) != len(trace):
        raise ValueError("E19a trace is incomplete")
    certified = {
        item["prompt_sha256"] for item in contract["policy"]["certified_allowlist"]
    }
    denied = {
        item["prompt_sha256"] for item in contract["policy"]["fallback_denylist"]
    }
    failures = 0
    uncached_reuse = 0
    for observed, expected in zip(records, trace, strict=True):
        if any(observed.get(name) != value for name, value in expected.items()):
            raise ValueError("E19a trace identity or affinity differs")
        fingerprint = observed["prompt_sha256"]
        if policy == "all_uncached":
            use_cache, decision = False, "baseline_uncached"
        elif fingerprint in certified:
            use_cache, decision = True, "certified_cache"
        elif fingerprint in denied:
            use_cache, decision = False, "calibration_fallback"
        else:
            use_cache, decision = False, "unknown_fallback"
        if (
            observed.get("cache_prompt") is not use_cache
            or observed.get("decision") != decision
            or not isinstance(observed.get("prompt_tokens"), int)
            or not 0
            < observed["prompt_tokens"]
            <= contract["prompt_construction"]["maximum_prompt_tokens"]
        ):
            raise ValueError("E19a cache decision differs")
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
            uncached_reuse += (
                not use_cache
                and observed["cached_tokens"]
                != contract["acceptance"]["required_uncached_cached_tokens"]
            )
        else:
            failures += 1
    measured_certified = [
        record
        for record in records
        if record["phase"] == "measured" and record["decision"] == "certified_cache"
    ]
    cache_hits = sum(
        record["cached_tokens"] >= record["shared_prefix_tokens"]
        for record in measured_certified
    )
    return {
        "failures": failures,
        "uncached_cache_reuse_violations": uncached_reuse,
        "certified_measured_cache_hit_fraction": (
            cache_hits / len(measured_certified) if measured_certified else 0.0
        ),
    }


def validate_group(
    directory: Path,
    contract: dict[str, Any],
    identity: dict[str, Any],
    sidecar_index: dict[str, Any],
    policy: str,
    repetition: int,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    raw = load_object(directory / "probe.json")
    workers = raw.get("workers")
    records = raw.get("records")
    result = raw.get("result")
    if (
        raw.get("schema_version") != 1
        or raw.get("experiment_id") != "E19a"
        or raw.get("policy") != policy
        or raw.get("repetition") != repetition
        or raw.get("assignment")
        != contract["mechanism"]["prefix_affinity_assignment"]
        or not isinstance(workers, list)
        or len(workers) != 2
        or not isinstance(records, list)
        or not isinstance(result, dict)
    ):
        raise ValueError("E19a probe structure differs")
    record_validation = validate_records(records, trace, contract, policy)
    worker_results = []
    mappings = []
    summed_pss = 0
    summed_rss = 0
    for worker in (1, 2):
        value = workers[worker - 1]
        expected_inventory = contract["execution"]["worker_request_inventory"][
            worker - 1
        ]
        pid = int((directory / f"server-pid-worker-{worker}.txt").read_text())
        parameters = value.get("parameters", {})
        worker_records = value.get("records")
        elapsed = finite(value.get("elapsed_seconds"), nonnegative=True)
        if (
            value.get("worker") != worker
            or parameters.get("server_pid") != pid
            or parameters.get("trace_requests")
            != expected_inventory["trace_requests"]
            or parameters.get("measured_requests")
            != expected_inventory["measured_requests"]
            or not isinstance(worker_records, list)
            or len(worker_records) != expected_inventory["trace_requests"]
            or elapsed <= 0
            or not math.isclose(
                finite(value.get("requests_per_second")),
                len(worker_records) / elapsed,
                rel_tol=1e-12,
            )
        ):
            raise ValueError("E19a worker probe differs")
        recipe = validate_recipe(
            load_object(directory / f"recipe-worker-{worker}.json"),
            contract,
            identity,
            policy,
            repetition,
            worker,
        )
        process_cpu = validate_process_cpu(
            value.get("process_cpu"),
            pid=pid,
            requests=len(worker_records),
            elapsed=elapsed,
        )
        readiness = load_object(directory / f"readiness-worker-{worker}.json")
        ready_ms = finite(readiness.get("ready_ms"), nonnegative=True)
        process = parse_time_output(
            (directory / f"server-time-worker-{worker}.log").read_text()
        )
        time_text = (directory / f"server-time-worker-{worker}.log").read_text()
        timed_commands = [
            line for line in time_text.splitlines() if "Command being timed:" in line
        ]
        shell_exit = int(
            (directory / f"server-shell-exit-worker-{worker}.txt").read_text()
        )
        smaps = parse_smaps_rollup(
            directory / f"smaps-rollup-worker-{worker}.txt"
        )
        mapping = sidecar_mapping(directory / f"process-maps-worker-{worker}.txt")
        log = (directory / f"server-worker-{worker}.stderr.log").read_text(
            errors="replace"
        )
        mapped = LOADER_MAPPED.findall(log)
        complete = LOADER_COMPLETE.findall(log)
        verification = load_object(
            directory / f"prelaunch-verification-worker-{worker}.json"
        )
        slots = load_object(directory / f"health-worker-{worker}.json")
        slot_inventory = json.loads(
            (directory / f"slots-worker-{worker}.json").read_text()
        )
        metrics = (directory / f"metrics-worker-{worker}.txt").read_text()
        if (
            parameters.get("url")
            != f"http://127.0.0.1:{contract['mechanism']['worker_ports'][worker - 1]}"
            or len(timed_commands) != 1
            or not all(argument in timed_commands[0] for argument in recipe["argv"])
            or readiness.get("status") != "ok"
            or ready_ms > contract["acceptance"]["maximum_ready_ms_per_worker"]
            or shell_exit
            not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
            or process.get("exit_status")
            not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
            or process.get("maximum_rss_kib") is None
            or process["maximum_rss_kib"]
            > contract["acceptance"]["maximum_process_rss_kib"]
            or verification.get("status") != "valid_sidecar"
            or verification.get("sidecar_sha256")
            != sidecar_index["sidecar_sha256"]
            or len(mapped) != 1
            or mapped[0][0] != str(sidecar_index["header"]["arena_size_bytes"])
            or mapped[0][2] != str(sidecar_index["header"]["tensor_count"])
            or complete != [str(sidecar_index["header"]["tensor_count"])]
            or mapping is None
            or mapping[0] != contract["acceptance"]["loader_mapping_permissions"]
            or mapping[1] != contract["acceptance"]["loader_mapping_offset_hex"]
            or slots.get("status") != "ok"
            or not isinstance(slot_inventory, list)
            or len(slot_inventory) != 1
            or "llamacpp:" not in metrics
        ):
            raise ValueError("E19a worker process or sidecar proof differs")
        mappings.append(mapping)
        summed_pss += smaps["Pss"]
        summed_rss += smaps["Rss"]
        worker_results.append(
            {
                "worker": worker,
                "ready_ms": ready_ms,
                "process": process,
                "process_cpu": process_cpu,
                "smaps_rollup_kib": smaps,
                "sidecar_mapping": mapping,
                "records": worker_records,
            }
        )
    if mappings[0][2] != mappings[1][2]:
        raise ValueError("E19a workers did not map the same sidecar inode")
    elapsed = finite(result.get("elapsed_seconds"), nonnegative=True)
    rps = finite(result.get("requests_per_second"), nonnegative=True)
    failures = record_validation["failures"]
    decisions = {
        name: sum(record["decision"] == name for record in records)
        for name in (
            "baseline_uncached",
            "certified_cache",
            "calibration_fallback",
            "unknown_fallback",
        )
    }
    skew = finite(result.get("measurement_start_skew_ms"), nonnegative=True)
    if (
        elapsed <= 0
        or not math.isclose(rps, len(records) / elapsed, rel_tol=1e-12)
        or result.get("request_failures") != failures
        or result.get("decision_counts") != decisions
    ):
        raise ValueError("E19a group aggregate differs")
    return {
        "policy": policy,
        "repetition": repetition,
        "workers": worker_results,
        "records": records,
        "elapsed_seconds": elapsed,
        "requests_per_second": rps,
        "measurement_start_skew_ms": skew,
        "request_failures": failures,
        "decision_counts": decisions,
        **record_validation,
        "summed_pss_kib": summed_pss,
        "summed_rss_kib": summed_rss,
        "group_ready_ms": max(worker["ready_ms"] for worker in worker_results),
        "cpu_seconds_per_request": sum(
            worker["process_cpu"]["total_seconds"] for worker in worker_results
        )
        / len(records),
    }


def summarize_policy(groups: list[dict[str, Any]]) -> dict[str, Any]:
    records = [record for group in groups for record in group["records"]]
    return {
        "groups": len(groups),
        "requests": len(records),
        "requests_per_second": summarize(
            [group["requests_per_second"] for group in groups]
        ),
        "http_ms": summarize([float(record["http_ms"]) for record in records]),
        "encode_ms": summarize([float(record["encode_ms"]) for record in records]),
        "decode_ms": summarize([float(record["decode_ms"]) for record in records]),
        "cpu_seconds_per_request": summarize(
            [group["cpu_seconds_per_request"] for group in groups]
        ),
        "summed_pss_kib": summarize([group["summed_pss_kib"] for group in groups]),
        "summed_rss_kib": summarize([group["summed_rss_kib"] for group in groups]),
        "group_ready_ms": summarize([group["group_ready_ms"] for group in groups]),
        "request_failures": sum(group["request_failures"] for group in groups),
    }


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = validate_inputs(evidence, contract_path, root)
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    acceptance = contract["acceptance"]
    if (
        platform["architecture"] != acceptance["required_architecture"]
        or platform["logical_cpus"] != acceptance["required_logical_cpus"]
        or platform["model_name"] != acceptance["required_model_name"]
    ):
        raise ValueError("E19a native platform differs")
    source_build = validate_source_build(evidence, contract)
    identity = load_object(evidence / "sidecar-identity.json")
    if identity.get("experiment_id") != "E19a":
        raise ValueError("E19a sidecar identity differs")
    construction = validate_construction(evidence, contract, identity)
    index = construction["sidecar_index"]
    final = load_object(evidence / "final-sidecar-verification.json")
    cleanup = load_object(evidence / "sidecar-cleanup.json")
    if (
        final.get("status") != "valid_sidecar"
        or final.get("sidecar_sha256") != index["sidecar_sha256"]
        or cleanup.get("deleted_sidecar_sha256") != index["sidecar_sha256"]
        or cleanup.get("deleted_sidecar_bytes") != index["sidecar_size_bytes"]
        or cleanup.get("sidecar_cleanup_complete") is not True
    ):
        raise ValueError("E19a final sidecar cleanup differs")
    trace = expected_trace_with_workers(contract)
    groups = []
    for position, item in enumerate(contract["execution"]["order"], start=1):
        directory = evidence / "cells" / (
            f"{position:02d}-{item['policy']}-r{item['repetition']}"
        )
        groups.append(
            validate_group(
                directory,
                contract,
                identity,
                index,
                item["policy"],
                item["repetition"],
                trace,
            )
        )
    by_key = {(group["policy"], group["repetition"]): group for group in groups}
    baseline_repeat = count_output_mismatches(
        by_key[("all_uncached", 1)]["records"],
        by_key[("all_uncached", 2)]["records"],
    )
    controller_repeat = count_output_mismatches(
        by_key[("certificate", 1)]["records"],
        by_key[("certificate", 2)]["records"],
    )
    controller_vs_baseline = sum(
        count_output_mismatches(
            by_key[("all_uncached", repetition)]["records"],
            by_key[("certificate", repetition)]["records"],
        )
        for repetition in (1, 2)
    )
    baseline = summarize_policy(
        [by_key[("all_uncached", repetition)] for repetition in (1, 2)]
    )
    controller = summarize_policy(
        [by_key[("certificate", repetition)] for repetition in (1, 2)]
    )
    ratios = {
        "throughput": controller["requests_per_second"]["median"]
        / baseline["requests_per_second"]["median"],
        "p95_http_latency": controller["http_ms"]["p95"]
        / baseline["http_ms"]["p95"],
        "cpu_seconds_per_request": controller["cpu_seconds_per_request"]["median"]
        / baseline["cpu_seconds_per_request"]["median"],
        "summed_pss": controller["summed_pss_kib"]["median"]
        / baseline["summed_pss_kib"]["median"],
    }
    expected_decisions = contract["execution"][
        "expected_controller_requests_per_trace"
    ]
    gates = {
        "native_arm64": True,
        "shared_sidecar_mechanism": True,
        "zero_request_failures": baseline["request_failures"] == 0
        and controller["request_failures"] == 0,
        "prefix_affinity": all(
            record["worker"]
            == 1
            + ((record["point_index"] + record["prefix_marker_index"]) % 2)
            for group in groups
            for record in group["records"]
        ),
        "simultaneous_start": max(
            group["measurement_start_skew_ms"] for group in groups
        )
        <= acceptance["maximum_measurement_start_skew_ms"],
        "exact_baseline_repeat_outputs": baseline_repeat
        == acceptance["exact_baseline_repeat_mismatches"],
        "exact_controller_repeat_outputs": controller_repeat
        == acceptance["exact_controller_repeat_mismatches"],
        "exact_controller_matches_uncached": controller_vs_baseline
        == acceptance["exact_controller_vs_uncached_mismatches"],
        "uncached_requests_reused_zero_tokens": all(
            group["uncached_cache_reuse_violations"] == 0 for group in groups
        ),
        "frozen_decision_counts": all(
            by_key[("certificate", repetition)]["decision_counts"]
            == {
                "baseline_uncached": 0,
                **expected_decisions,
            }
            for repetition in (1, 2)
        ),
        "certified_cache_mechanism": min(
            by_key[("certificate", repetition)][
                "certified_measured_cache_hit_fraction"
            ]
            for repetition in (1, 2)
        )
        >= acceptance["minimum_certified_measured_cache_hit_fraction"],
        "baseline_throughput_stable": baseline["requests_per_second"][
            "coefficient_of_variation"
        ]
        <= acceptance["maximum_throughput_coefficient_of_variation"],
        "controller_throughput_stable": controller["requests_per_second"][
            "coefficient_of_variation"
        ]
        <= acceptance["maximum_throughput_coefficient_of_variation"],
        "throughput": ratios["throughput"] >= acceptance["minimum_throughput_ratio"],
        "p95_http_latency": ratios["p95_http_latency"]
        <= acceptance["maximum_p95_http_latency_ratio"],
        "cpu_seconds_per_request": ratios["cpu_seconds_per_request"]
        <= acceptance["maximum_cpu_seconds_per_request_ratio"],
        "summed_pss_ratio": ratios["summed_pss"]
        <= acceptance["maximum_summed_pss_ratio"],
        "summed_pss_absolute": max(
            group["summed_pss_kib"] for group in groups
        )
        <= acceptance["maximum_summed_pss_kib"],
        "startup": max(group["group_ready_ms"] for group in groups)
        <= acceptance["maximum_ready_ms_per_worker"],
        "sidecar_cleanup": cleanup["sidecar_cleanup_complete"],
    }
    passed = all(gates.values())
    return {
        "schema_version": 1,
        "experiment_id": "E19a",
        "status": "valid_composed_affinity_cache_arena_promoted"
        if passed
        else "valid_composed_affinity_cache_arena_rejected",
        "promoted": passed,
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "source_build": source_build,
        "sidecar_identity": identity,
        "construction": construction,
        "baseline": baseline,
        "controller": controller,
        "ratios": ratios,
        "quality": {
            "baseline_repeat_mismatches": baseline_repeat,
            "controller_repeat_mismatches": controller_repeat,
            "controller_vs_uncached_mismatches": controller_vs_baseline,
        },
        "groups": groups,
        "gates": gates,
        "failed_gates": [name for name, passed_gate in gates.items() if not passed_gate],
        "final_sidecar_verification": final,
        "sidecar_cleanup": cleanup,
        "provenance": load_object(evidence / "provenance.json"),
        "decision": {
            "composed_tier_promoted": passed,
            "selected_policy": "certificate" if passed else "all_uncached",
            "post_result_gate_change_permitted": False,
        },
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": summary["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
