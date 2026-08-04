#!/usr/bin/env python3
"""Validate E17c 8K-context K/V quality and serving-density evidence."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

try:
    import experiments.e17b_ingest as base
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e7a_ingest import validate_runtime_closure
    from experiments.e17c_freeze import INPUT_PATHS
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    import e17b_ingest as base
    from e1_ingest import parse_lscpu
    from e5b_ingest import load_object, sha256_file
    from e7a_ingest import validate_runtime_closure
    from e17c_freeze import INPUT_PATHS


_BASE_VALIDATE_RECIPE = base.validate_recipe
_BASE_VALIDATE_PROBE = base.validate_probe


def validate_recipe(
    recipe: dict[str, Any],
    contract: dict[str, Any],
    configuration: str,
    slots: int,
    repetition: int,
) -> None:
    adjusted_recipe = copy.deepcopy(recipe)
    adjusted_contract = copy.deepcopy(contract)
    if (
        recipe.get("experiment_id") != "E17c"
        or contract.get("experiment_id") != "E17c"
    ):
        raise ValueError("E17c recipe identity differs")
    adjusted_recipe["experiment_id"] = "E17b"
    adjusted_contract["experiment_id"] = "E17b"
    adjusted_recipe["argv"] = [
        "18082" if value == "18083" else value for value in adjusted_recipe["argv"]
    ]
    _BASE_VALIDATE_RECIPE(
        adjusted_recipe, adjusted_contract, configuration, slots, repetition
    )


def validate_probe(
    probe: dict[str, Any],
    contract: dict[str, Any],
    tasks: dict[str, Any],
    configuration: str,
    slots: int,
    repetition: int,
) -> dict[str, Any]:
    adjusted_probe = copy.deepcopy(probe)
    adjusted_contract = copy.deepcopy(contract)
    if probe.get("experiment_id") != "E17c":
        raise ValueError("E17c probe identity differs")
    adjusted_probe["experiment_id"] = "E17b"
    adjusted_contract["experiment_id"] = "E17b"
    return _BASE_VALIDATE_PROBE(
        adjusted_probe,
        adjusted_contract,
        tasks,
        configuration,
        slots,
        repetition,
    )


def validate_inputs(evidence: Path, root: Path, contract: dict[str, Any]) -> None:
    for name, relative in INPUT_PATHS.items():
        expected = contract["inputs"][f"{name}_sha256"]
        if contract["inputs"][f"{name}_path"] != relative.as_posix():
            raise ValueError(f"E17c {name} path differs")
        for path in (root / relative, evidence / "frozen-inputs" / relative):
            if sha256_file(path) != expected:
                raise ValueError(f"E17c {name} input differs")


def build_manifest(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    tasks = load_object(root / INPUT_PATHS["tasks"])
    if (
        contract.get("experiment_id") != "E17c"
        or load_object(evidence / "contract.json") != contract
    ):
        raise ValueError("E17c contract differs")
    validate_inputs(evidence, root, contract)
    predecessor = load_object(root / INPUT_PATHS["predecessor_failure"])
    if (
        predecessor.get("status") != contract["predecessor"]["status"]
        or predecessor.get("github", {}).get("run_id")
        != contract["predecessor"]["run_id"]
        or predecessor.get("decision", {}).get("sixteen_k_claim_allowed") is not False
    ):
        raise ValueError("E17c predecessor differs")

    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != contract["acceptance"]["required_architecture"]:
        raise ValueError("E17c evidence is not native Arm64")
    if load_object(evidence / "e9a-workflow-summary.json") != load_object(
        root / INPUT_PATHS["e9a_manifest"]
    ):
        raise ValueError("E17c runtime prerequisite differs")
    artifact = load_object(evidence / "e9a-artifact.json")
    provenance = contract["runtime"]["artifact"]
    if (
        str(artifact.get("id")) != provenance["id"]
        or artifact.get("name") != provenance["name"]
        or artifact.get("digest") != provenance["digest"]
        or artifact.get("size_in_bytes") != provenance["size_bytes"]
    ):
        raise ValueError("E17c runtime artifact identity differs")
    closure = validate_runtime_closure(evidence / "runtime/runtime-closure.json")
    server = evidence / "runtime/runtime-files/bin/llama-server"
    if sha256_file(server) != contract["runtime"]["server_sha256"]:
        raise ValueError("E17c server differs")
    model_digest = (evidence / "model-sha256.txt").read_text().split()
    if (
        len(model_digest) != 2
        or model_digest[0] != contract["selected"]["model_sha256"]
    ):
        raise ValueError("E17c model differs")

    cells: list[dict[str, Any]] = []
    original_recipe = base.validate_recipe
    original_probe = base.validate_probe
    base.validate_recipe = validate_recipe
    base.validate_probe = validate_probe
    try:
        for index, item in enumerate(contract["execution"]["cells"], start=1):
            path = evidence / "cells" / (
                f"{index:02d}-{item['configuration']}-s{item['slots']}"
                f"-r{item['repetition']}"
            )
            caller = int((path / "caller-exit.txt").read_text().strip())
            cells.append(
                base.successful_cell(path, contract, tasks, **item)
                if caller == 0
                else base.failed_cell(path, contract, **item)
            )
    finally:
        base.validate_recipe = original_recipe
        base.validate_probe = original_probe
    if len(cells) != 9:
        raise ValueError("E17c did not account for all cells")

    f16_four_cells = [
        cell
        for cell in cells
        if cell["configuration"] == "f16_f16" and cell["slots"] == 4
    ]
    if len(f16_four_cells) != 2 or not all(
        cell["served"] for cell in f16_four_cells
    ):
        raise ValueError("E17c f16 four-slot control did not serve")
    canonical_prompts = f16_four_cells[0]["probe"]["prompt_sha256"]
    if any(
        cell["probe"]["prompt_sha256"] != canonical_prompts
        for cell in cells
        if cell["served"]
    ):
        raise ValueError("E17c successful cells used different prompts")

    four_slot: dict[str, Any] = {}
    eight_slot: dict[str, Any] = {}
    for configuration in contract["execution"]["configurations"]:
        four_slot[configuration] = base.four_slot_summary(
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
            and throughput_ratio
            >= acceptance["minimum_quantized_four_slot_throughput_ratio"]
            and p95_ratio <= acceptance["maximum_quantized_four_slot_p95_ratio"]
            and density_throughput_ratio
            >= acceptance["minimum_eight_to_four_slot_throughput_ratio"]
            and density_p95_ratio
            <= acceptance["maximum_eight_to_four_slot_p95_ratio"]
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
    f16_eight = eight_slot["f16_f16"]
    return {
        "schema_version": 1,
        "experiment_id": "E17c",
        "status": (
            "valid_8k_context_quantized_kv_density"
            if promoted
            else "valid_no_8k_context_quantized_kv_density_promotion"
        ),
        "contract_sha256": sha256_file(contract_path),
        "platform": platform,
        "runtime": {"artifact": provenance, "closure": closure},
        "selected": contract["selected"],
        "predecessor": contract["predecessor"],
        "workload": {
            "prompt_sha256": canonical_prompts,
            "prompt_token_counts": f16_four_cells[0]["probe"][
                "prompt_token_counts"
            ],
            "expected_answers": expected_answers,
            "configured_context_tokens_per_slot": contract["workload"][
                "context_tokens_per_slot"
            ],
        },
        "cells": cells,
        "four_slot": four_slot,
        "eight_slot": eight_slot,
        "gates": gates,
        "decision": {
            "promoted_8k_context_configurations": promoted,
            "serving_density_win": bool(promoted),
            "f16_eight_slot_served": bool(
                isinstance(f16_eight, dict) and f16_eight.get("served") is True
            ),
            "general_service_promotion_made": False,
            "separate_general_quality_confirmation_required": True,
            "e17b_failed_contract_rehabilitated": False,
            "sixteen_k_claim_allowed": False,
        },
        "validation": {
            "native_arm64": True,
            "exact_e9a_runtime_closure": True,
            "exact_selected_model": True,
            "all_frozen_inputs_match": True,
            "all_nine_cells_accounted_for": True,
            "f16_four_slot_control_served_twice": True,
            "reverse_balanced_four_slot_order": True,
            "same_prompts_in_every_successful_cell": True,
            "prompt_cache_disabled": True,
            "process_address_space_limit_verified": True,
            "all_answers_probabilities_and_failures_retained": True,
            "e17b_failure_not_reinterpreted": True,
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
    print(json.dumps({"status": manifest["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
