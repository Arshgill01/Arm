#!/usr/bin/env python3
"""Validate E20a's bounded software graph-node timing evidence."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
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
    from experiments.e6f_ingest import expected_server_argv
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e20a_freeze import INPUT_PATHS
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
    from e6f_ingest import expected_server_argv
    from e7a_ingest import validate_runtime_closure
    from e20a_freeze import INPUT_PATHS


PREFIX = "ggml_cpu_node_timing\t"
ATTENTION = re.compile(r"^blk\.(\d+)\.attn_([qkv])\.weight$")
FFN = re.compile(r"^blk\.(\d+)\.ffn_(gate|up)\.weight$")


def classify_projection(source: str) -> tuple[str, int, str] | None:
    match = ATTENTION.fullmatch(source)
    if match:
        return "attention_qkv", int(match.group(1)), match.group(2)
    match = FFN.fullmatch(source)
    if match:
        return "ffn_gate_up", int(match.group(1)), match.group(2)
    return None


def parse_node_timing(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in path.read_text(errors="replace").splitlines():
        if not raw.startswith(PREFIX):
            continue
        pieces = raw.split("\t")[1:]
        fields: dict[str, str] = {}
        for piece in pieces:
            if "=" not in piece:
                raise ValueError("E20a timing field lacks equals")
            key, value = piece.split("=", 1)
            if key in fields:
                raise ValueError("E20a timing field repeats")
            fields[key] = value
        required = {
            "graph", "node", "op", "name", "src0", "src1", "ne",
            "fused_nodes", "elapsed_us",
        }
        if set(fields) != required:
            raise ValueError("E20a timing field set differs")
        dimensions = [int(value) for value in fields["ne"].split(",")]
        record = {
            "graph": int(fields["graph"]),
            "node": int(fields["node"]),
            "op": fields["op"],
            "name": fields["name"],
            "src0": fields["src0"],
            "src1": fields["src1"],
            "ne": dimensions,
            "fused_nodes": int(fields["fused_nodes"]),
            "elapsed_us": int(fields["elapsed_us"]),
        }
        if (
            record["graph"] < 0
            or record["node"] < 0
            or not record["op"]
            or len(dimensions) != 4
            or any(value <= 0 for value in dimensions)
            or record["fused_nodes"] < 0
            or record["elapsed_us"] < 0
        ):
            raise ValueError("E20a timing record value differs")
        records.append(record)
    return records


def summarize_trace(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(item["elapsed_us"] for item in records)
    if total <= 0:
        raise ValueError("E20a timing trace has no positive duration")
    by_op: dict[str, int] = defaultdict(int)
    by_source: dict[str, int] = defaultdict(int)
    family_elapsed = {"attention_qkv": 0, "ffn_gate_up": 0}
    activation_roles: dict[tuple[str, int, str, int], set[str]] = defaultdict(set)
    for item in records:
        elapsed = item["elapsed_us"]
        by_op[item["op"]] += elapsed
        if item["src0"]:
            by_source[item["src0"]] += elapsed
        projection = classify_projection(item["src0"])
        if projection is not None:
            family, layer, role = projection
            family_elapsed[family] += elapsed
            activation_roles[(family, layer, item["src1"], item["graph"])].add(role)
    shared = {
        family: len(
            {
                (layer, source)
                for (observed, layer, source, _graph), roles in activation_roles.items()
                if observed == family and source and len(roles) >= 2
            }
        )
        for family in family_elapsed
    }
    return {
        "record_count": len(records),
        "positive_record_count": sum(item["elapsed_us"] > 0 for item in records),
        "graph_count": len({item["graph"] for item in records}),
        "total_elapsed_us": total,
        "op_elapsed_us": dict(sorted(by_op.items())),
        "top_ops": sorted(by_op.items(), key=lambda item: (-item[1], item[0]))[:20],
        "top_sources": sorted(by_source.items(), key=lambda item: (-item[1], item[0]))[:30],
        "family_elapsed_us": family_elapsed,
        "family_share": {
            family: elapsed / total for family, elapsed in family_elapsed.items()
        },
        "shared_activation_layers": shared,
    }


def choose_fusion(
    traces: dict[str, dict[str, Any]], contract: dict[str, Any]
) -> dict[str, Any]:
    modes = contract["benchmark"]["selection_modes"]
    threshold = contract["acceptance"]["minimum_prefill_group_share"]
    minimum_layers = contract["acceptance"][
        "minimum_shared_activation_layers_per_prefill_mode"
    ]
    candidates: dict[str, Any] = {}
    for family in contract["selection"]["eligible_families"]:
        shares = [traces[mode]["family_share"][family] for mode in modes]
        shared = [traces[mode]["shared_activation_layers"][family] for mode in modes]
        eligible = all(value >= threshold for value in shares) and all(
            value >= minimum_layers for value in shared
        )
        candidates[family] = {
            "eligible": eligible,
            "shares": dict(zip(modes, shares, strict=True)),
            "shared_activation_layers": dict(zip(modes, shared, strict=True)),
            "geometric_mean_share": math.prod(shares) ** (1 / len(shares)),
        }
    eligible = [name for name, value in candidates.items() if value["eligible"]]
    selected = (
        sorted(
            eligible,
            key=lambda name: (-candidates[name]["geometric_mean_share"], name),
        )[0]
        if eligible
        else None
    )
    return {
        "families": candidates,
        "selected_family": selected,
        "focused_fusion_successor_allowed": selected is not None,
        "automatic_source_optimization_allowed": False,
    }


def validate_bench_case(
    evidence: Path, case: dict[str, Any], contract: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    directory = evidence / "bench" / case["name"]
    command = load_object(directory / "command.json")
    observed_argv = command.get("argv")
    if (
        not isinstance(observed_argv, list)
        or not observed_argv
        or not isinstance(observed_argv[0], str)
        or not observed_argv[0].endswith("/bin/llama-bench")
    ):
        raise ValueError(f"E20a benchmark binary differs for {case['name']}")
    replacements = {
        "BENCH_PATH": observed_argv[0],
        "MODEL_PATH": (evidence / "model-sha256.txt").read_text().split()[1],
    }
    expected = [replacements.get(value, value) for value in case["argv"]]
    if command != {"argv": expected, "case": case}:
        raise ValueError(f"E20a command differs for {case['name']}")
    process = parse_time_output((directory / "process-time.log").read_text())
    if process["exit_status"] != 0:
        raise ValueError(f"E20a benchmark process failed for {case['name']}")
    lines = [line for line in (directory / "result.jsonl").read_text().splitlines() if line]
    if len(lines) != 1:
        raise ValueError(f"E20a benchmark output count differs for {case['name']}")
    result = json.loads(lines[0])
    samples = result.get("samples_ts")
    if (
        result.get("n_prompt") != case["n_prompt"]
        or result.get("n_gen") != case["n_generation"]
        or result.get("model_filename") != replacements["MODEL_PATH"]
        or result.get("model_size") != contract["selected"]["model_size_bytes"]
        or result.get("n_threads") != 4
        or result.get("n_batch") != 1024
        or result.get("n_ubatch") != 512
        or not isinstance(result.get("avg_ns"), int)
        or result["avg_ns"] <= 0
        or not isinstance(result.get("avg_ts"), (int, float))
        or result["avg_ts"] <= 0
        or not isinstance(samples, list)
        or len(samples) != case["repetitions"]
        or any(not isinstance(value, (int, float)) or value <= 0 for value in samples)
        or contract["source"]["commit"][:9] not in str(result.get("build_commit", ""))
    ):
        raise ValueError(f"E20a benchmark result differs for {case['name']}")
    records = parse_node_timing(directory / "stderr.log")
    required = (
        contract["acceptance"]["minimum_positive_timing_records_per_timed_case"]
        if case["node_timing"]
        else contract["acceptance"]["control_timing_records"]
    )
    positive = sum(item["elapsed_us"] > 0 for item in records)
    if (case["node_timing"] and positive < required) or (
        not case["node_timing"] and len(records) != required
    ):
        raise ValueError(f"E20a timing mechanism differs for {case['name']}")
    return {
        "name": case["name"],
        "mode": case["mode"],
        "node_timing": case["node_timing"],
        "repetitions": case["repetitions"],
        "avg_ns": result["avg_ns"],
        "avg_tokens_per_second": float(result["avg_ts"]),
        "samples_tokens_per_second": [float(value) for value in samples],
        "process": process,
        "result_sha256": sha256_file(directory / "result.jsonl"),
        "stderr_sha256": sha256_file(directory / "stderr.log"),
        "timing_record_count": len(records),
        "positive_timing_record_count": positive,
    }, records


def validate_quality(evidence: Path, contract: dict[str, Any], root: Path) -> dict[str, Any]:
    directory = evidence / "quality"
    recipe = load_object(directory / "recipe.json")
    server = recipe.get("server_path")
    model = (evidence / "model-sha256.txt").read_text().split()[1]
    if (
        not isinstance(server, str)
        or not server.endswith("/bin/llama-server")
        or recipe.get("experiment_id") != "E20a"
        or recipe.get("profile_name") != "node_timing_quality"
        or recipe.get("server_path") != server
        or recipe.get("model", {}).get("path") != model
        or recipe.get("model", {}).get("sha256") != contract["selected"]["model_sha256"]
        or recipe.get("model", {}).get("size_bytes") != contract["selected"]["model_size_bytes"]
        or recipe.get("service") != contract["service"]
        or recipe.get("argv")
        != expected_server_argv(
            server,
            model,
            candidate=contract["selected"]["candidate"],
            service=contract["service"],
        )
    ):
        raise ValueError("E20a quality recipe differs")
    tasks = load_tasks(load_object(root / INPUT_PATHS["tasks"]))
    references = reference_predictions(
        load_object(root / INPUT_PATHS["reference_manifest"]),
        contract["selected"]["candidate"],
    )
    probe = validate_probe(
        load_object(directory / "probe.json"),
        configuration="node_timing_quality",
        repetition=1,
        config=contract["service"],
        contract=contract,
        tasks=tasks,
        references=references,
        require_selected_quality=True,
    )
    process = parse_time_output((directory / "server-time.log").read_text())
    shell_status = int((directory / "server-shell-exit.txt").read_text())
    readiness = load_object(directory / "readiness.json")
    records = parse_node_timing(directory / "server.stderr.log")
    positive = sum(item["elapsed_us"] > 0 for item in records)
    if (
        process["exit_status"] not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or shell_status not in contract["acceptance"]["accepted_server_shell_exit_statuses"]
        or readiness.get("status") != "ok"
        or positive
        < contract["acceptance"]["minimum_positive_timing_records_per_timed_case"]
    ):
        raise ValueError("E20a quality process or timing mechanism differs")
    return {
        "probe": probe,
        "process": process,
        "readiness_ms": readiness["ready_ms"],
        "timing_record_count": len(records),
        "positive_timing_record_count": positive,
        "probe_sha256": sha256_file(directory / "probe.json"),
        "stderr_sha256": sha256_file(directory / "server.stderr.log"),
    }


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    if contract.get("experiment_id") != "E20a" or load_object(evidence / "contract.json") != contract:
        raise ValueError("E20a contract differs")
    for name, relative in INPUT_PATHS.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if (
            sha256_file(root / relative) != expected
            or sha256_file(evidence / "frozen-inputs" / relative) != expected
        ):
            raise ValueError(f"E20a input differs for {name}")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["benchmark"]["required_architecture"]:
        raise ValueError("E20a evidence is not native Arm64")
    source = load_object(evidence / "source.json")
    if (
        source != contract["source"]
        or sha256_file(evidence / "source-diff.patch") != contract["source"]["source_diff_sha256"]
        or (evidence / "patched-files.txt").read_text().splitlines()
        != contract["source"]["changed_files"]
    ):
        raise ValueError("E20a source differs")
    cache = (evidence / "build/CMakeCache.txt").read_text(errors="replace").splitlines()
    for argument in contract["build"]["cmake_arguments"]:
        key, value = argument.removeprefix("-D").split("=", 1)
        if not any(line.startswith(f"{key}:") and line.endswith(f"={value}") for line in cache):
            raise ValueError(f"E20a build cache differs for {key}")
    if (
        contract["source"]["commit"][:9]
        not in (evidence / "build/server-version.txt").read_text(errors="replace")
        or (evidence / "build/timing-environment-symbol.txt").read_text().strip()
        != "GGML_CPU_NODE_TIMING"
        or "ggml-cpu.c" not in (evidence / "build/build-commands.txt").read_text(errors="replace")
        or "--n-prompt" not in (evidence / "build/bench-help.txt").read_text(errors="replace")
    ):
        raise ValueError("E20a build mechanism proof differs")
    model_line = (evidence / "model-sha256.txt").read_text().split()
    if (
        len(model_line) != 2
        or model_line[0] != contract["selected"]["model_sha256"]
        or Path(model_line[1]).name != contract["selected"]["path"]
        or int((evidence / "model-size.txt").read_text())
        != contract["selected"]["model_size_bytes"]
    ):
        raise ValueError("E20a model differs")
    closures = {
        name: validate_runtime_closure(evidence / f"build/{name}-runtime-closure.json")
        for name in ("server", "bench")
    }
    for closure in closures.values():
        names = {Path(item["resolved_path"]).name for item in closure["runtime_dependencies"]}
        if names.intersection(contract["build"]["forbidden_dynamic_dependency_basenames"]):
            raise ValueError("E20a retained a forbidden dynamic dependency")

    descriptors = []
    timed_by_mode: dict[str, dict[str, Any]] = {}
    for case in contract["benchmark"]["cases"]:
        descriptor, records = validate_bench_case(evidence, case, contract)
        descriptors.append(descriptor)
        if case["node_timing"]:
            timed_by_mode[case["mode"]] = summarize_trace(records)
    if set(timed_by_mode) != {"pp512", "pp4096", "tg128"}:
        raise ValueError("E20a timed mode set differs")
    selection = choose_fusion(timed_by_mode, contract)
    quality = validate_quality(evidence, contract, root)
    status = (
        "valid_cpu_node_profile_fusion_candidate"
        if selection["selected_family"] is not None
        else "valid_cpu_node_profile_no_fusion_candidate"
    )
    return {
        "schema_version": 1,
        "experiment_id": "E20a",
        "status": status,
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "source": source,
        "model": contract["selected"],
        "runtime_closures": closures,
        "quality": quality,
        "benchmark_descriptors": descriptors,
        "software_timing": timed_by_mode,
        "selection": selection,
        "validation": {
            "native_arm64": True,
            "exact_selected_service_quality": True,
            "zero_request_failures": True,
            "exact_source_and_patch_series": True,
            "openssl_absent": True,
            "all_six_benchmark_cases_complete": True,
            "timer_disabled_controls_have_no_records": True,
            "timer_enabled_cases_have_structured_records": True,
            "software_wall_clock_only": True,
            "hosted_pmu_claim_made": False,
            "timed_results_used_for_performance_claim": False,
        },
        "decision": {
            **selection,
            "separate_source_implementation_contract_required": True,
            "separate_end_to_end_service_gate_required": True,
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
    result = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "selection": result["selection"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
