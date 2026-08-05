#!/usr/bin/env python3
"""Derive the terminal model-tier decision from retained native evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ANCHOR = "ministral3_3b_q4_k_m"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_STOCK = {
    ANCHOR,
    "ministral3_3b_q3_k_s",
    "ministral3_3b_q3_k_m",
    "ministral3_3b_iq4_xs",
    "ministral3_3b_iq4_nl",
    "ministral3_3b_q5_k_m",
}
STOCK_DECISIONS = {
    "ministral3_3b_q3_k_s": (
        "closed_quality_and_service_regression",
        "15/30 with 14 anchor-answer mismatches and 0.2875x anchor throughput",
    ),
    "ministral3_3b_q3_k_m": (
        "closed_quality_and_service_regression",
        "17/30 with six anchor-answer mismatches and 0.3943x anchor throughput",
    ),
    "ministral3_3b_iq4_xs": (
        "closed_quality_and_service_regression",
        "22/30 with one anchor-answer mismatch and 0.5561x anchor throughput",
    ),
    "ministral3_3b_iq4_nl": (
        "closed_marginal_tradeoff_has_no_unique_portfolio_role",
        "23/30 but one answer changes; speed, latency and CPU regress while the "
        "4.2% RSS and 19.9% readiness benefits are already addressed more strongly "
        "by the exact-Q4 memory and sidecar profiles",
    ),
    "ministral3_3b_q5_k_m": (
        "closed_quality_service_and_resource_regression",
        "22/30 with one answer mismatch, 0.7923x throughput and 1.1428x RSS",
    ),
}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def compact_point(point: dict[str, Any], anchor_size: int) -> dict[str, Any]:
    quality = point.get("service", {}).get("quality", {})
    correct_values = set(quality.get("correct_per_repetition", []))
    mismatches = quality.get("reference_prediction_mismatches_per_repetition", [])
    if len(correct_values) != 1 or not mismatches:
        raise ValueError(f"unstable E11b quality for {point.get('candidate')}")
    return {
        "candidate": point["candidate"],
        "exact_30_task_correct": correct_values.pop(),
        "maximum_anchor_answer_mismatches": max(mismatches),
        "external_quality_coordinates": point["quality_coordinates"],
        "model_size_bytes": point["model_size_bytes"],
        "model_size_ratio_to_anchor": point["model_size_bytes"] / anchor_size,
        "throughput_requests_per_second": point["throughput"],
        "median_http_ms": point["median_http_ms"],
        "p95_http_ms": point["p95_http_ms"],
        "cpu_seconds_per_request": point["cpu_seconds_per_request"],
        "maximum_rss_kib": point["maximum_rss_kib"],
        "readiness_ms": point["readiness_ms"],
    }


def generated_signal(
    generated: list[dict[str, Any]], candidate: str
) -> dict[str, Any]:
    selected = [
        item
        for item in generated
        if item.get("candidate_recipe", {}).get("candidate") == candidate
    ]
    if len(selected) != 1:
        raise ValueError(f"E12b generated candidate differs: {candidate}")
    item = selected[0]
    return {
        "candidate": candidate,
        "model_sha256": item["model"]["sha256"],
        "model_size_bytes": item["model"]["size_bytes"],
        "external_quality_coordinates": item["quality_coordinates"],
        "request_failures": item["request_failures"],
        "matched_native_service_evidence": False,
    }


def build_decision(
    *,
    e11b_path: Path,
    e12b_path: Path,
    memory_path: Path,
    sidecar_path: Path,
) -> dict[str, Any]:
    e11b = load_object(e11b_path)
    e12b = load_object(e12b_path)
    memory = load_object(memory_path)
    sidecar = load_object(sidecar_path)
    if (
        e11b.get("status") != "valid_stock_quant_service_frontier"
        or e11b.get("campaign_decision", {}).get("product_promotion_made") is not False
        or e12b.get("status")
        != "valid_safe_sampled_matched_mixed_quant_quality_frontier"
        or e12b.get("campaign_decision", {}).get("product_promotion_made")
        is not False
        or memory.get("status") != "valid_current_runtime_memory_launch_integration"
        or sidecar.get("status") != "valid_sidecar_loader_promoted"
    ):
        raise ValueError("terminal model-tier prerequisite differs")

    points = e11b.get("points", [])
    by_candidate = {point.get("candidate"): point for point in points}
    if set(by_candidate) != EXPECTED_STOCK or len(points) != len(by_candidate):
        raise ValueError("E11b stock candidate set differs")
    anchor = by_candidate[ANCHOR]
    anchor_compact = compact_point(anchor, anchor["model_size_bytes"])
    selection = memory.get("selection", {})
    if (
        selection.get("candidate") != ANCHOR
        or selection.get("model_size_bytes") != anchor["model_size_bytes"]
        or selection.get("reference_correct") != 23
    ):
        raise ValueError("selected Q4_K_M identity differs")

    pair_ratios = {pair["candidate"]: pair["ratios"] for pair in e11b["pairs"]}
    if set(pair_ratios) != EXPECTED_STOCK - {ANCHOR}:
        raise ValueError("E11b pair ratio set differs")
    assessments = []
    for candidate in sorted(EXPECTED_STOCK - {ANCHOR}):
        compact = compact_point(by_candidate[candidate], anchor["model_size_bytes"])
        decision, reason = STOCK_DECISIONS[candidate]
        compact.update(
            {
                "ratios_to_anchor": pair_ratios[candidate],
                "decision": decision,
                "reason": reason,
            }
        )
        assessments.append(compact)

    generated = e12b.get("generated_models", [])
    if len(generated) != 9 or len(e12b.get("quality_size_frontier", [])) != 11:
        raise ValueError("E12b recovered frontier size differs")
    signals = [
        generated_signal(generated, "e12b_iq4_xs_control"),
        generated_signal(generated, "e12b_q4_k_s_edge_layers_q6"),
    ]
    iq4xs = next(
        item for item in assessments if item["candidate"] == "ministral3_3b_iq4_xs"
    )
    sidecar_ratios = sidecar.get("ratios", {})
    if (
        sidecar.get("decision", {}).get("loader_promoted") is not True
        or sidecar_ratios.get("readiness", 1.0) >= 0.8
        or memory.get("validation", {}).get("current_runtime_memory_launch_claim_allowed")
        is not True
    ):
        raise ValueError("selected-model portfolio evidence differs")

    return {
        "schema_version": 1,
        "decision_id": "terminal-model-tier-2026-08-05",
        "status": "selected_q4_k_m_and_closed_model_sweep",
        "inputs": {
            "e11b": {
                "path": repository_path(e11b_path),
                "sha256": sha256_file(e11b_path),
                "github_run_id": e11b["github"]["source_run_id"],
                "source_workflow_remains_failed": True,
                "complete_native_service_cells": 40,
            },
            "e12b": {
                "path": repository_path(e12b_path),
                "sha256": sha256_file(e12b_path),
                "github_run_id": e12b["github"]["source_run_id"],
                "source_workflow_remains_failed": True,
                "successful_generated_cells": 9,
            },
            "selected_memory_profile": {
                "path": repository_path(memory_path),
                "sha256": sha256_file(memory_path),
            },
            "selected_sidecar_profile": {
                "path": repository_path(sidecar_path),
                "sha256": sha256_file(sidecar_path),
            },
        },
        "selected_model": {
            **anchor_compact,
            "model_sha256": selection["model_sha256"],
            "role": "only promoted model tier",
        },
        "stock_candidate_assessments": assessments,
        "generated_frontier_assessment": {
            "generated_recipes": len(generated),
            "combined_quality_size_frontier_points": len(
                e12b["quality_size_frontier"]
            ),
            "strongest_unconfirmed_signals": signals,
            "stock_iq4_xs_throughput_ratio_is_family_context_not_causal_proof": (
                iq4xs["ratios_to_anchor"]["throughput"]
            ),
            "matched_native_service_evidence_available": False,
            "decision": "no_generated_recipe_promoted_or_regenerated",
            "reason": (
                "E12b is a mixed quality/size map. No generated recipe has matched "
                "30-task service evidence, and neither retained signal establishes a "
                "unique product role strong enough to justify another generation and "
                "service matrix."
            ),
        },
        "selected_model_portfolio": {
            "performance_service": ANCHOR,
            "memory_service": {
                "candidate": selection["candidate"],
                "weight_repack": selection["service"]["weight_repack"],
                "claim": memory["validation"]["claim_scope"],
            },
            "startup_service": {
                "candidate": ANCHOR,
                "configuration": sidecar["decision"]["selected_configuration"],
                "same_job_readiness_ratio": sidecar_ratios["readiness"],
                "throughput_ratio": sidecar_ratios["throughput"],
                "claim": sidecar["decision"]["admitted_boundary"],
            },
        },
        "terminal_decision": {
            "selected_model": ANCHOR,
            "additional_model_tiers_promoted": [],
            "additional_model_candidates_to_test": [],
            "new_native_model_experiment_authorized": False,
            "broad_model_knob_sweep_closed": True,
            "original_30_task_contract_changed": False,
            "poor_and_mixed_results_preserved": True,
            "rationale": [
                "Q4_K_M is the fastest exact native service point and preserves all anchor answers.",
                "No stock alternative supplies a unique quality-certified product role after the exact-Q4 memory and startup profiles are considered.",
                "E12b generated recipes have mixed external quality and no matched service evidence, so the quality-size map is not converted into a promotion.",
                "The model lane is closed instead of spending another Arm matrix on marginal or unconfirmed tradeoffs.",
            ],
        },
        "claim_boundary": (
            "This terminal decision selects one model tier for the exact retained "
            "Pareto64 Arm service portfolio. It does not erase the E11b or E12b "
            "frontiers, attribute their differences to one mechanism, or make energy, "
            "PMU, local-device, fleet, cost, other-model, or other-runtime claims."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--e11b",
        type=Path,
        default=Path("results/manifests/e11b-30869286295-recovered.json"),
    )
    parser.add_argument(
        "--e12b",
        type=Path,
        default=Path("results/manifests/e12b-30869536393-recovered.json"),
    )
    parser.add_argument(
        "--memory",
        type=Path,
        default=Path("results/manifests/e6i-30691254831.json"),
    )
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=Path("results/manifests/e16b-30842925537.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_decision(
        e11b_path=args.e11b,
        e12b_path=args.e12b,
        memory_path=args.memory,
        sidecar_path=args.sidecar,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
