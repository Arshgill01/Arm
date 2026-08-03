#!/usr/bin/env python3
"""Validate the native E10e probability-API compatibility preflight."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu, parse_time_output
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e10d_ingest import (
        validate_recipe,
        validate_raw_response,
        validate_source_and_build,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu, parse_time_output
    from e5b_ingest import load_object, sha256_file
    from e10d_ingest import (
        validate_recipe,
        validate_raw_response,
        validate_source_and_build,
    )


ARTIFACT_INPUTS = {
    "failure_manifest": "e10d-failure-manifest.json",
    "e10d_contract": "e10d-contract.json",
    "e9a_contract": "e9a-contract.json",
    "models": "models-manifest.json",
    "cases": "failure-cases.json",
    "primitive_patch": "patches/0004-server-select-exact-token-probabilities.patch",
}


def case_key(value: dict[str, Any]) -> tuple[str, int, int]:
    return (value["task"], value["sample_ordinal"], value["choice_index"])


def validate_attempt_probability(raw: dict[str, Any], attempt: dict[str, Any]) -> None:
    probabilities = raw.get("completion_probabilities")
    entry = (
        probabilities[0]
        if isinstance(probabilities, list) and len(probabilities) == 1
        else None
    )
    selected = entry.get("selected_logprobs") if isinstance(entry, dict) else None
    item = selected[0] if isinstance(selected, list) and len(selected) == 1 else None
    if attempt["status"] == "missing_probability_entry":
        if item is not None:
            raise ValueError("E10e missing probability unexpectedly exists")
        return
    if (
        attempt["status"] != "ok"
        or not isinstance(item, dict)
        or item.get("id") != attempt["target_token_id"]
        or item.get("logprob") != attempt["selected_logprob"]
    ):
        raise ValueError("E10e selected probability differs from raw response")


def validate_variant(
    evidence: Path,
    plan: dict[str, Any],
    name: str,
    e10d_contract: dict[str, Any],
) -> dict[str, Any]:
    definition = plan["variants"][name]
    variant_dir = evidence / "variants" / name
    probe = load_object(variant_dir / "probe.json")
    if (
        probe.get("schema_version") != 1
        or probe.get("experiment_id") != "E10e-preflight"
        or probe.get("variant") != name
        or probe.get("forced_safe_token_id")
        != definition["forced_safe_token_id"]
        or probe.get("forced_safe_logit_bias")
        != definition["forced_safe_logit_bias"]
        or probe.get("model") != plan["model"]["candidate"]
        or probe.get("model_sha256") != plan["model"]["sha256"]
        or probe.get("parameters") != plan["probe_parameters"]
    ):
        raise ValueError(f"E10e {name} probe header differs")
    cases = probe.get("cases")
    by_key = {case_key(case): case for case in cases} if isinstance(cases, list) else {}
    expected_keys = {
        (item["task"], item["sample_ordinal"], item["choice_index"])
        for item in plan["cases"]
    }
    if len(by_key) != len(plan["cases"]) or set(by_key) != expected_keys:
        raise ValueError(f"E10e {name} cases differ")
    retained: dict[str, Any] = {}
    for expected in plan["cases"]:
        key = (expected["task"], expected["sample_ordinal"], expected["choice_index"])
        case = by_key[key]
        candidate = case.get("candidate_tokens")
        attempts = case.get("attempts")
        if (
            case.get("source_index") != expected["source_index"]
            or not isinstance(candidate, list)
            or candidate != expected["candidate_tokens"]
            or not isinstance(attempts, list)
            or not attempts
        ):
            raise ValueError(f"E10e {name} case shape differs")
        for index, attempt in enumerate(attempts):
            if (
                attempt.get("token_index") != index
                or attempt.get("target_token_id") != candidate[index]
                or attempt.get("http_status") != 200
            ):
                raise ValueError(f"E10e {name} attempt identity differs")
            raw = validate_raw_response(variant_dir / "raw", attempt["raw_response"])
            validate_attempt_probability(raw, attempt)
            if (
                definition["forced_safe_token_id"] is not None
                and raw.get("content") != plan["safe_sampling"]["token_text"]
            ):
                raise ValueError(f"E10e {name} safe-token content differs")
            timings = raw.get("timings")
            cache_n = timings.get("cache_n") if isinstance(timings, dict) else None
            if (
                raw.get("tokens") != attempt.get("generated_tokens")
                or cache_n != attempt.get("cache_n")
                or (index == 0 and cache_n != 0)
                or (index > 0 and (type(cache_n) is not int or cache_n <= 0))
            ):
                raise ValueError(f"E10e {name} response evidence differs")
            for metric in ("http_ms", "client_elapsed_ms"):
                value = attempt.get(metric)
                if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"E10e {name} timing differs")
        missing_index = expected["original_missing_token_index"]
        if definition["expected_outcome"] == "reproduce_original_missing_entry":
            if (
                len(attempts) != missing_index + 1
                or any(attempt["status"] != "ok" for attempt in attempts[:-1])
                or attempts[-1]["status"] != "missing_probability_entry"
                or case.get("completed") is not False
            ):
                raise ValueError("E10e original failure did not reproduce exactly")
        elif definition["expected_outcome"] == "complete_all_selected_probabilities":
            safe_token = definition["forced_safe_token_id"]
            if (
                len(attempts) != len(candidate)
                or any(attempt["status"] != "ok" for attempt in attempts)
                or any(
                    attempt.get("generated_tokens") != [safe_token]
                    for attempt in attempts
                )
                or case.get("completed") is not True
            ):
                raise ValueError(f"E10e {name} did not complete")
        else:
            raise ValueError("E10e variant outcome is unknown")
        retained["|".join(map(str, key))] = case
    process = parse_time_output((variant_dir / "server-time.log").read_text())
    readiness = load_object(variant_dir / "readiness.json")
    if (
        process["exit_status"]
        not in plan["acceptance"]["accepted_server_shell_exit_statuses"]
        or process["maximum_rss_kib"] is None
        or process["maximum_rss_kib"]
        > plan["acceptance"]["maximum_process_rss_kib"]
        or readiness.get("status") != "ok"
        or not isinstance(readiness.get("ready_ms"), (int, float))
        or not math.isfinite(readiness["ready_ms"])
        or readiness["ready_ms"] > plan["acceptance"]["maximum_ready_ms"]
    ):
        raise ValueError(f"E10e {name} process evidence differs")
    validate_recipe(
        load_object(variant_dir / "recipe.json"),
        e10d_contract,
        plan["model"],
    )
    return {
        "definition": definition,
        "cases": retained,
        "readiness": readiness,
        "server_process": process,
    }


def compare_variants(
    variants: dict[str, dict[str, Any]], plan: dict[str, Any]
) -> dict[str, float]:
    original = variants["original"]
    first = variants["forced_safe_1"]
    second = variants["forced_safe_2"]
    maximum_original_delta = 0.0
    maximum_repeat_delta = 0.0
    for expected in plan["cases"]:
        key = "|".join(
            map(
                str,
                (expected["task"], expected["sample_ordinal"], expected["choice_index"]),
            )
        )
        original_attempts = original["cases"][key]["attempts"]
        first_attempts = first["cases"][key]["attempts"]
        second_attempts = second["cases"][key]["attempts"]
        for left, right in zip(original_attempts[:-1], first_attempts, strict=False):
            maximum_original_delta = max(
                maximum_original_delta,
                abs(left["selected_logprob"] - right["selected_logprob"]),
            )
        for left, right in zip(first_attempts, second_attempts, strict=True):
            maximum_repeat_delta = max(
                maximum_repeat_delta,
                abs(left["selected_logprob"] - right["selected_logprob"]),
            )
    if (
        maximum_original_delta
        > plan["acceptance"]["maximum_prefailure_logprob_delta"]
        or maximum_repeat_delta
        > plan["acceptance"]["maximum_repeat_logprob_delta"]
    ):
        raise ValueError("E10e safe-token sampling changed retained selected logprobs")
    return {
        "maximum_original_vs_forced_safe_prefailure_logprob_delta": maximum_original_delta,
        "maximum_forced_safe_repeat_logprob_delta": maximum_repeat_delta,
    }


def build_manifest(evidence: Path, plan_path: Path, root: Path) -> dict[str, Any]:
    plan = load_object(plan_path)
    if plan.get("schema_version") != 1 or plan.get("experiment_id") != "E10e-preflight":
        raise ValueError("plan does not identify E10e preflight")
    if load_object(evidence / "contract.json") != plan:
        raise ValueError("artifact plan differs from frozen E10e preflight")
    for key, artifact in ARTIFACT_INPUTS.items():
        source = root / plan["inputs"][f"{key}_path"]
        expected = plan["inputs"][f"{key}_sha256"]
        if sha256_file(source) != expected or sha256_file(evidence / artifact) != expected:
            raise ValueError(f"E10e input differs for {key}")
    for key in ("preflight", "ingest", "cell_runner", "freeze", "test"):
        source = root / plan["inputs"][f"{key}_path"]
        if sha256_file(source) != plan["inputs"][f"{key}_sha256"]:
            raise ValueError(f"E10e implementation differs for {key}")
    failure = load_object(evidence / "e10d-failure-manifest.json")
    if (
        failure.get("status") != "invalid_external_holdout_cell_retained"
        or failure.get("decision", {}).get("negative_result_retained") is not True
        or failure.get("github", {}).get("run_id") != plan["prerequisite"]["run_id"]
        or failure.get("model") != plan["model"]
    ):
        raise ValueError("E10e retained E10d failure differs")
    platform = parse_lscpu((evidence / "lscpu.txt").read_text())
    if platform["architecture"] != plan["acceptance"]["required_architecture"]:
        raise ValueError("E10e evidence is not native Arm64")
    cases = load_object(evidence / "failure-cases.json")
    if cases.get("cases") != plan["cases"]:
        raise ValueError("E10e failure cases differ from frozen plan")
    e10d_contract = load_object(evidence / "e10d-contract.json")
    runtime = validate_source_and_build(evidence, e10d_contract)
    variants = {
        name: validate_variant(evidence, plan, name, e10d_contract)
        for name in plan["variant_order"]
    }
    deltas = compare_variants(variants, plan)
    return {
        "schema_version": 1,
        "experiment_id": "E10e-preflight",
        "status": "valid_probability_api_compatibility_preflight",
        "contract_sha256": sha256_file(plan_path),
        "platform": platform,
        "runtime": runtime,
        "variants": variants,
        "comparison": deltas,
        "decision": {
            "original_failure_reproduced": True,
            "forced_safe_sampling_completed_twice": True,
            "raw_selected_logprobs_preserved": True,
            "full_holdout_validated": False,
            "successor_dispatch_allowed": True,
        },
        "claim_boundary": plan["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = build_manifest(args.evidence_dir, args.plan, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
