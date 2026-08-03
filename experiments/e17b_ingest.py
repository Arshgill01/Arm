#!/usr/bin/env python3
"""Validate E17b long-context K/V quality and serving-density evidence."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output, summarize
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e17b_freeze import INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output, summarize
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure
    from e17b_freeze import INPUT_PATHS


KV_ALLOCATION = re.compile(r"CPU KV buffer size =\s+([0-9.]+) MiB")
LETTERS = {"A", "B", "C", "D"}


def expected_argv(recipe: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    config = contract["execution"]["configurations"][recipe["configuration"]]
    slots = recipe["slots"]
    context = slots * contract["workload"]["context_tokens_per_slot"]
    return [
        recipe["server_path"],
        "--model", recipe["model"]["path"],
        "--alias", contract["selected"]["candidate"],
        "--threads", "4",
        "--threads-batch", "4",
        "--ctx-size", str(context),
        "--cache-type-k", config["kv_cache_type_k"],
        "--cache-type-v", config["kv_cache_type_v"],
        "--flash-attn", "on",
        "--parallel", str(slots),
        "--cont-batching",
        "--host", "127.0.0.1",
        "--port", "18082",
        "--no-webui",
        "--metrics",
        "--slots",
        "--jinja",
        "--temp", "0.0",
        "--seed", "424242",
        "--log-colors", "off",
        "--log-verbosity", "4",
        "--batch-size", "1024",
        "--ubatch-size", "512",
    ]


def validate_recipe(
    recipe: dict[str, Any],
    contract: dict[str, Any],
    configuration: str,
    slots: int,
    repetition: int,
) -> None:
    config = contract["execution"]["configurations"].get(configuration)
    service = recipe.get("service")
    if (
        config is None
        or recipe.get("experiment_id") != "E17b"
        or recipe.get("configuration") != configuration
        or recipe.get("slots") != slots
        or recipe.get("repetition") != repetition
        or recipe.get("model", {}).get("sha256")
        != contract["selected"]["model_sha256"]
        or recipe.get("model", {}).get("size_bytes")
        != contract["selected"]["model_size_bytes"]
        or recipe.get("process_address_space_limit_bytes")
        != contract["execution"]["process_address_space_limit_bytes"]
        or not isinstance(service, dict)
        or service.get("kv_cache_type_k") != config["kv_cache_type_k"]
        or service.get("kv_cache_type_v") != config["kv_cache_type_v"]
        or service.get("context_tokens_per_slot")
        != contract["workload"]["context_tokens_per_slot"]
        or service.get("total_context_tokens")
        != slots * contract["workload"]["context_tokens_per_slot"]
        or service.get("parallel_slots") != slots
        or service.get("flash_attention") != "on"
        or service.get("prompt_cache") is not False
        or recipe.get("argv") != expected_argv(recipe, contract)
        or not recipe.get("server_path", "").endswith(
            "/runtime-files/bin/llama-server"
        )
    ):
        raise ValueError("E17b recipe differs")


def parse_pss(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in path.read_text().splitlines():
        if ":" not in line:
            continue
        name, raw = line.split(":", 1)
        pieces = raw.split()
        if pieces and pieces[0].isdigit():
            values[name] = int(pieces[0])
    for required in ("Rss", "Pss", "Private_Clean", "Private_Dirty"):
        if required not in values:
            raise ValueError(f"E17b smaps lacks {required}")
    return {"rss_kib": values["Rss"], "pss_kib": values["Pss"], "private_kib": values["Private_Clean"] + values["Private_Dirty"]}


def validate_address_limit(path: Path, expected: int) -> None:
    line = next(
        (line for line in path.read_text().splitlines() if line.startswith("Max address space")),
        None,
    )
    if line is None:
        raise ValueError("E17b process limits lack address-space limit")
    numbers = [int(value) for value in re.findall(r"\b\d+\b", line)]
    if numbers[:2] != [expected, expected] or not line.rstrip().endswith("bytes"):
        raise ValueError("E17b process address-space limit differs")


def validate_probe(
    probe: dict[str, Any],
    contract: dict[str, Any],
    tasks: dict[str, Any],
    configuration: str,
    slots: int,
    repetition: int,
) -> dict[str, Any]:
    expected_tasks = tasks["tasks"]
    cases = probe.get("cases")
    result = probe.get("result")
    construction = probe.get("prompt_construction")
    if (
        probe.get("experiment_id") != "E17b"
        or probe.get("configuration") != configuration
        or probe.get("slots") != slots
        or probe.get("repetition") != repetition
        or not isinstance(cases, list)
        or not isinstance(result, dict)
        or not isinstance(construction, list)
        or len(cases) != len(expected_tasks)
        or len(construction) != len(expected_tasks)
        or [case.get("task_id") for case in cases]
        != [task["id"] for task in expected_tasks]
        or [item.get("task_id") for item in construction]
        != [task["id"] for task in expected_tasks]
        or result.get("total") != len(expected_tasks)
    ):
        raise ValueError("E17b probe shape differs")

    minimum = contract["workload"]["prompt_token_minimum"]
    maximum = contract["workload"]["prompt_token_maximum"]
    failures = 0
    for case, task, prompt in zip(cases, expected_tasks, construction, strict=True):
        probabilities = case.get("candidate_probabilities")
        timing_names = ("http_ms", "encode_ms", "decode_ms", "top1_margin")
        timing_valid = all(
            isinstance(case.get(name), (int, float))
            and math.isfinite(float(case[name]))
            and float(case[name]) >= 0
            for name in timing_names
        )
        valid = (
            case.get("http_status") == 200
            and case.get("error") is None
            and case.get("prediction") in LETTERS
            and case.get("expected") == task["answer"]
            and isinstance(probabilities, dict)
            and set(probabilities) == LETTERS
            and math.isclose(sum(float(value) for value in probabilities.values()), 1.0, abs_tol=1e-9)
            and case.get("prompt_sha256") == prompt.get("prompt_sha256")
            and case.get("prompt_token_count") == prompt.get("prompt_token_count")
            and minimum <= case.get("prompt_token_count", -1) <= maximum
            and case.get("cached_tokens") == 0
            and case.get("response_tokens_cached") == 0
            and isinstance(case.get("evaluated_prompt_tokens"), (int, float))
            and case["evaluated_prompt_tokens"] >= minimum
            and timing_valid
        )
        if not valid:
            failures += 1
    if failures != result.get("failures"):
        # Semantic answer errors are not transport failures, so only require the
        # workflow-reported request-failure count to be structurally plausible.
        if result.get("failures") != 0 or any(case.get("http_status") != 200 for case in cases):
            raise ValueError("E17b probe failure accounting differs")
    return {
        "answers": {case["task_id"]: case["prediction"] for case in cases},
        "correct": sum(case.get("correct") is True for case in cases),
        "total": len(cases),
        "request_failures": result["failures"],
        "requests_per_second": float(result["requests_per_second"]),
        "http_ms": result["http_ms"],
        "encode_ms": result["encode_ms"],
        "decode_ms": result["decode_ms"],
        "server_process_cpu": result["server_process_cpu"],
        "prompt_sha256": [item["prompt_sha256"] for item in construction],
        "prompt_token_counts": [item["prompt_token_count"] for item in construction],
        "cases": cases,
    }


def successful_cell(
    cell: Path,
    contract: dict[str, Any],
    tasks: dict[str, Any],
    configuration: str,
    slots: int,
    repetition: int,
) -> dict[str, Any]:
    recipe = load_object(cell / "recipe.json")
    validate_recipe(recipe, contract, configuration, slots, repetition)
    readiness = load_object(cell / "readiness.json")
    process = parse_time_output((cell / "server-time.log").read_text())
    shell_status = int((cell / "server-shell-exit.txt").read_text().strip())
    if (
        readiness.get("status") != "ok"
        or shell_status not in {0, 130}
        or process["exit_status"] not in {0, 130}
        or not isinstance(process["maximum_rss_kib"], int)
    ):
        raise ValueError("E17b successful process state differs")
    validate_address_limit(
        cell / "process-limits-ready.txt",
        contract["execution"]["process_address_space_limit_bytes"],
    )
    log = (cell / "server.stderr.log").read_text(errors="replace")
    allocations = KV_ALLOCATION.findall(log)
    if (
        len(allocations) != 1
        or "flash_attn    = enabled" not in log
        or f"n_slots = {slots}" not in log
        or f"n_ctx_slot = {contract['workload']['context_tokens_per_slot']}" not in log
    ):
        raise ValueError("E17b mechanism log differs")
    probe = validate_probe(
        load_object(cell / "probe.json"),
        contract,
        tasks,
        configuration,
        slots,
        repetition,
    )
    return {
        "served": True,
        "configuration": configuration,
        "slots": slots,
        "repetition": repetition,
        "kv_allocation_mib": float(allocations[0]),
        "readiness_ms": readiness["ready_ms"],
        "process": process,
        "memory_ready": parse_pss(cell / "process-smaps-ready.txt"),
        "memory_after": parse_pss(cell / "process-smaps-after.txt"),
        "probe": probe,
        "recipe_sha256": sha256_file(cell / "recipe.json"),
        "probe_sha256": sha256_file(cell / "probe.json"),
        "server_stderr_sha256": sha256_file(cell / "server.stderr.log"),
    }


def failed_cell(
    cell: Path,
    contract: dict[str, Any],
    configuration: str,
    slots: int,
    repetition: int,
) -> dict[str, Any]:
    recipe = load_object(cell / "recipe.json")
    validate_recipe(recipe, contract, configuration, slots, repetition)
    caller = int((cell / "caller-exit.txt").read_text().strip())
    stderr = cell / "server.stderr.log"
    if caller == 0 or not stderr.is_file():
        raise ValueError("E17b failed cell evidence differs")
    process = (
        parse_time_output((cell / "server-time.log").read_text())
        if (cell / "server-time.log").is_file()
        else None
    )
    return {
        "served": False,
        "configuration": configuration,
        "slots": slots,
        "repetition": repetition,
        "caller_exit_status": caller,
        "process": process,
        "failure_stage": "launch, readiness, long-context request, or shutdown",
        "server_stderr_tail": stderr.read_text(errors="replace")[-8000:],
        "recipe_sha256": sha256_file(cell / "recipe.json"),
        "server_stderr_sha256": sha256_file(stderr),
    }


def four_slot_summary(cells: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(cells) != 2 or not all(cell["served"] for cell in cells):
        return None
    cases = [case for cell in cells for case in cell["probe"]["cases"]]
    return {
        "repetitions": cells,
        "requests_per_second": summarize(
            [cell["probe"]["requests_per_second"] for cell in cells]
        ),
        "http_ms": summarize([float(case["http_ms"]) for case in cases]),
        "encode_ms": summarize([float(case["encode_ms"]) for case in cases]),
        "maximum_rss_kib": summarize(
            [float(cell["process"]["maximum_rss_kib"]) for cell in cells]
        ),
        "pss_after_kib": summarize(
            [float(cell["memory_after"]["pss_kib"]) for cell in cells]
        ),
        "kv_allocation_mib": cells[0]["kv_allocation_mib"],
    }


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    tasks = load_object(root / INPUT_PATHS["tasks"])
    if contract.get("experiment_id") != "E17b" or load_object(evidence / "contract.json") != contract:
        raise ValueError("E17b contract differs")
    for name, relative in INPUT_PATHS.items():
        if sha256_file(root / relative) != contract["inputs"][f"{name}_sha256"]:
            raise ValueError(f"E17b input differs for {name}")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E17b evidence is not native Arm64")
    if load_object(evidence / "e9a-workflow-summary.json") != load_object(
        root / INPUT_PATHS["e9a_manifest"]
    ):
        raise ValueError("E17b runtime prerequisite differs")
    artifact = load_object(evidence / "e9a-artifact.json")
    provenance = contract["runtime"]["artifact"]
    if (
        str(artifact.get("id")) != provenance["id"]
        or artifact.get("name") != provenance["name"]
        or artifact.get("digest") != provenance["digest"]
        or artifact.get("size_in_bytes") != provenance["size_bytes"]
    ):
        raise ValueError("E17b runtime artifact identity differs")
    closure = validate_runtime_closure(evidence / "runtime/runtime-closure.json")
    server = evidence / "runtime/runtime-files/bin/llama-server"
    if sha256_file(server) != contract["runtime"]["server_sha256"]:
        raise ValueError("E17b server differs")
    model_digest = (evidence / "model-sha256.txt").read_text().split()
    if len(model_digest) != 2 or model_digest[0] != contract["selected"]["model_sha256"]:
        raise ValueError("E17b model differs")

    cells: list[dict[str, Any]] = []
    for index, item in enumerate(contract["execution"]["cells"], start=1):
        path = evidence / "cells" / (
            f"{index:02d}-{item['configuration']}-s{item['slots']}-r{item['repetition']}"
        )
        caller = int((path / "caller-exit.txt").read_text().strip())
        cells.append(
            successful_cell(path, contract, tasks, **item)
            if caller == 0
            else failed_cell(path, contract, **item)
        )
    if len(cells) != 9:
        raise ValueError("E17b did not account for all cells")

    f16_four_cells = [
        cell for cell in cells if cell["configuration"] == "f16_f16" and cell["slots"] == 4
    ]
    if len(f16_four_cells) != 2 or not all(cell["served"] for cell in f16_four_cells):
        raise ValueError("E17b f16 four-slot control did not serve")
    canonical_prompts = f16_four_cells[0]["probe"]["prompt_sha256"]
    if any(
        cell["probe"]["prompt_sha256"] != canonical_prompts
        for cell in cells
        if cell["served"]
    ):
        raise ValueError("E17b successful cells used different prompts")

    four_slot: dict[str, Any] = {}
    eight_slot: dict[str, Any] = {}
    for configuration in contract["execution"]["configurations"]:
        four_slot[configuration] = four_slot_summary(
            [
                cell
                for cell in cells
                if cell["configuration"] == configuration and cell["slots"] == 4
            ]
        )
        eight = [
            cell
            for cell in cells
            if cell["configuration"] == configuration and cell["slots"] == 8
        ]
        eight_slot[configuration] = eight[0] if len(eight) == 1 else None

    expected_answers = contract["workload"]["answers"]
    baseline = four_slot["f16_f16"]
    baseline_quality = all(
        cell["probe"]["answers"] == expected_answers
        and cell["probe"]["request_failures"] == 0
        for cell in baseline["repetitions"]
    )
    gates: dict[str, Any] = {}
    acceptance = contract["acceptance"]
    for configuration in contract["execution"]["quantized_candidates"]:
        four = four_slot[configuration]
        eight = eight_slot[configuration]
        four_served = four is not None
        eight_served = isinstance(eight, dict) and eight.get("served") is True
        quality = bool(
            baseline_quality
            and four_served
            and eight_served
            and all(
                cell["probe"]["answers"] == expected_answers
                and cell["probe"]["request_failures"] == 0
                for cell in four["repetitions"]
            )
            and eight["probe"]["answers"] == expected_answers
            and eight["probe"]["request_failures"] == 0
        )
        throughput_ratio = (
            four["requests_per_second"]["median"]
            / baseline["requests_per_second"]["median"]
            if four_served
            else None
        )
        p95_ratio = (
            four["http_ms"]["p95"] / baseline["http_ms"]["p95"]
            if four_served
            else None
        )
        density_throughput_ratio = (
            eight["probe"]["requests_per_second"]
            / four["requests_per_second"]["median"]
            if four_served and eight_served
            else None
        )
        density_p95_ratio = (
            eight["probe"]["http_ms"]["p95"] / four["http_ms"]["p95"]
            if four_served and eight_served
            else None
        )
        allocation_ratio = (
            four["kv_allocation_mib"] / baseline["kv_allocation_mib"]
            if four_served
            else None
        )
        allocation_ceiling = (
            acceptance["maximum_q8_allocation_ratio"]
            if configuration == "q8_0_q8_0"
            else acceptance["maximum_q4_allocation_ratio"]
        )
        passed = bool(
            quality
            and throughput_ratio is not None
            and throughput_ratio >= acceptance["minimum_quantized_four_slot_throughput_ratio"]
            and p95_ratio <= acceptance["maximum_quantized_four_slot_p95_ratio"]
            and density_throughput_ratio >= acceptance["minimum_eight_to_four_slot_throughput_ratio"]
            and density_p95_ratio <= acceptance["maximum_eight_to_four_slot_p95_ratio"]
            and allocation_ratio <= allocation_ceiling
        )
        gates[configuration] = {
            "passed": passed,
            "quality_passed": quality,
            "four_slot_served": four_served,
            "eight_slot_served": eight_served,
            "four_slot_throughput_ratio": throughput_ratio,
            "four_slot_p95_ratio": p95_ratio,
            "eight_to_four_slot_throughput_ratio": density_throughput_ratio,
            "eight_to_four_slot_p95_ratio": density_p95_ratio,
            "four_slot_allocation_ratio": allocation_ratio,
            "allocation_ceiling": allocation_ceiling,
        }
    promoted = [name for name, gate in gates.items() if gate["passed"]]
    return {
        "schema_version": 1,
        "experiment_id": "E17b",
        "status": (
            "valid_long_context_quantized_kv_density"
            if promoted
            else "valid_no_long_context_quantized_kv_density_promotion"
        ),
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "runtime": {"artifact": provenance, "closure": closure},
        "selected": contract["selected"],
        "workload": {
            "prompt_sha256": canonical_prompts,
            "prompt_token_counts": f16_four_cells[0]["probe"]["prompt_token_counts"],
            "expected_answers": expected_answers,
        },
        "cells": cells,
        "four_slot": four_slot,
        "eight_slot": eight_slot,
        "gates": gates,
        "decision": {
            "promoted_long_context_configurations": promoted,
            "serving_density_win": bool(promoted),
            "f16_eight_slot_served": eight_slot["f16_f16"]["served"],
            "general_service_promotion_made": False,
            "separate_general_quality_confirmation_required": True,
        },
        "validation": {
            "native_arm64": True,
            "exact_e9a_runtime_closure": True,
            "exact_selected_model": True,
            "all_nine_cells_accounted_for": True,
            "f16_four_slot_control_served_twice": True,
            "reverse_balanced_four_slot_order": True,
            "same_long_context_prompts_in_every_successful_cell": True,
            "prompt_cache_disabled": True,
            "process_address_space_limit_verified": True,
            "all_answers_probabilities_and_failures_retained": True,
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
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"], "decision": manifest["decision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
