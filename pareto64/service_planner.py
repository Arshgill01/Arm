from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .planner import finite_metric, pareto_front, sha256_file


SERVICE_DIRECTIONS = {
    "requests_per_second_median": "higher",
    "http_ms_median": "lower",
    "http_ms_p95": "lower",
    "maximum_rss_kib": "lower",
    "ready_ms_median": "lower",
}


def validate_service_constraints(
    constraints: dict[str, Any],
) -> tuple[dict[str, dict[str, float]], list[str]]:
    if constraints.get("schema_version") != 1:
        raise ValueError("unsupported Pareto64 service constraint schema")
    requirements = constraints.get("requirements")
    priorities = constraints.get("selection_priority")
    if not isinstance(requirements, dict):
        raise ValueError("service constraints require a requirements object")
    if not isinstance(priorities, list) or not priorities:
        raise ValueError("service constraints require a non-empty selection_priority")
    if any(
        not isinstance(metric, str) or metric not in SERVICE_DIRECTIONS
        for metric in priorities
    ):
        raise ValueError("service selection_priority contains an unknown metric")
    if len(set(priorities)) != len(priorities):
        raise ValueError("service selection_priority contains duplicates")

    normalized: dict[str, dict[str, float]] = {}
    for metric, rule in requirements.items():
        if metric not in SERVICE_DIRECTIONS or not isinstance(rule, dict):
            raise ValueError(f"invalid service requirement for {metric}")
        operator = (
            "at_least" if SERVICE_DIRECTIONS[metric] == "higher" else "at_most"
        )
        if set(rule) != {operator}:
            raise ValueError(
                f"service requirement {metric} must contain only {operator}"
            )
        normalized[metric] = {operator: finite_metric(rule[operator], metric)}
    return normalized, priorities


def extract_e5h_profiles(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("experiment_id") != "E5h"
        or manifest.get("status") != "valid_selected_inference_memory_tier"
    ):
        raise ValueError("service planner requires the selected schema-1 E5h result")
    validation = manifest.get("validation", {})
    if (
        validation.get("memory_tier_claim_allowed") is not True
        or validation.get("zero_request_failures") is not True
        or validation.get("model_buffer_mechanism_observed_for_every_profile")
        is not True
    ):
        raise ValueError("E5h manifest does not permit service-tier selection")

    selection = manifest.get("selection", {})
    default_name = selection.get("default_configuration")
    memory_name = selection.get("memory_tier_configuration")
    if default_name != "repack_on" or memory_name != "repack_off":
        raise ValueError("E5h selected service tiers differ from the product contract")
    performance = manifest.get("performance")
    if not isinstance(performance, dict) or set(performance) != {
        default_name,
        memory_name,
    }:
        raise ValueError("E5h performance profiles differ from the selected tiers")

    profiles: dict[str, dict[str, Any]] = {}
    for name in sorted(performance):
        evidence = performance[name]
        if not isinstance(evidence, dict):
            raise ValueError(f"service profile {name} is malformed")
        weight_repack = evidence.get("weight_repack")
        quality_eligible = evidence.get("quality", {}).get(
            "exact_selected_predictions"
        )
        if not isinstance(weight_repack, bool) or not isinstance(
            quality_eligible, bool
        ):
            raise ValueError(f"service profile {name} lacks a bounded decision")
        repack_buffer = finite_metric(
            evidence.get("mechanism", {}).get("repack_buffer_mib"),
            "repack_buffer_mib",
        )
        if (weight_repack and repack_buffer <= 0) or (
            not weight_repack and repack_buffer != 0
        ):
            raise ValueError(f"service profile {name} mechanism is inconsistent")
        metrics = {
            "requests_per_second_median": finite_metric(
                evidence.get("requests_per_second", {}).get("median"),
                "requests_per_second_median",
            ),
            "http_ms_median": finite_metric(
                evidence.get("http_ms", {}).get("median"), "http_ms_median"
            ),
            "http_ms_p95": finite_metric(
                evidence.get("http_ms", {}).get("p95"), "http_ms_p95"
            ),
            "maximum_rss_kib": finite_metric(
                evidence.get("maximum_rss_kib", {}).get("max"),
                "maximum_rss_kib",
            ),
            "ready_ms_median": finite_metric(
                evidence.get("ready_ms", {}).get("median"), "ready_ms_median"
            ),
        }
        profiles[name] = {
            "name": name,
            "quality_eligible": quality_eligible,
            "metrics": metrics,
            "runtime": {
                "weight_repack": weight_repack,
                "launch_arguments": [] if weight_repack else ["--no-weight-repack"],
            },
        }
    return profiles


def service_rejection_reasons(
    profile: dict[str, Any], requirements: Mapping[str, Mapping[str, float]]
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    if not profile["quality_eligible"]:
        reasons.append({"kind": "quality_gate", "detail": "answer_drift"})
    for metric, rule in requirements.items():
        observed = profile["metrics"][metric]
        if "at_least" in rule and observed < rule["at_least"]:
            reasons.append(
                {
                    "kind": "slo",
                    "metric": metric,
                    "operator": "at_least",
                    "threshold": rule["at_least"],
                    "observed": observed,
                }
            )
        elif "at_most" in rule and observed > rule["at_most"]:
            reasons.append(
                {
                    "kind": "slo",
                    "metric": metric,
                    "operator": "at_most",
                    "threshold": rule["at_most"],
                    "observed": observed,
                }
            )
    return reasons


def service_selection_key(
    metrics: Mapping[str, float], priorities: Sequence[str]
) -> tuple[float, ...]:
    return tuple(
        -metrics[metric]
        if SERVICE_DIRECTIONS[metric] == "higher"
        else metrics[metric]
        for metric in priorities
    )


def build_service_plan(
    manifest: dict[str, Any],
    constraints: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    constraints_path: Path | None = None,
) -> dict[str, Any]:
    requirements, priorities = validate_service_constraints(constraints)
    profiles = extract_e5h_profiles(manifest)
    evaluated: dict[str, dict[str, Any]] = {}
    feasible: dict[str, dict[str, float]] = {}
    for name, profile in profiles.items():
        reasons = service_rejection_reasons(profile, requirements)
        evaluated[name] = {**profile, "rejections": reasons}
        if not reasons:
            feasible[name] = profile["metrics"]

    frontier_names = pareto_front(feasible, SERVICE_DIRECTIONS)
    selected_name = (
        min(
            frontier_names,
            key=lambda name: (
                service_selection_key(feasible[name], priorities),
                name,
            ),
        )
        if frontier_names
        else None
    )
    selected = evaluated[selected_name] if selected_name else None
    return {
        "schema_version": 1,
        "planner": "Pareto64",
        "planner_stage": "service_profile",
        "status": "selected" if selected else "no_feasible_profile",
        "inputs": {
            "experiment_id": manifest["experiment_id"],
            "experiment_status": manifest["status"],
            "github_run_url": manifest.get("source", {}).get("github_run_url"),
            "selected_candidate": manifest["selection"]["candidate"],
            "manifest_path": str(manifest_path) if manifest_path else None,
            "manifest_sha256": sha256_file(manifest_path) if manifest_path else None,
            "constraints_path": str(constraints_path) if constraints_path else None,
            "constraints_sha256": (
                sha256_file(constraints_path) if constraints_path else None
            ),
        },
        "policy": {
            "requirements": requirements,
            "selection_priority": priorities,
            "directions": SERVICE_DIRECTIONS,
            "weighted_score_used": False,
        },
        "evaluated": evaluated,
        "feasible_profiles": sorted(feasible),
        "pareto_frontier": [evaluated[name] for name in frontier_names],
        "selected": selected,
        "decision": (
            "No quality-valid measured service profile passed the declared SLOs."
            if selected is None
            else "Selected lexicographically from the measured service Pareto frontier using the explicit priority list."
        ),
    }
