from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


DIRECTIONS = {
    "minimum_accuracy": "higher",
    "same_text_total_ms_median": "lower",
    "maximum_quality_process_rss_kib": "lower",
    "package_size_bytes": "lower",
    "model_load_ms_median": "lower",
}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite_metric(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"metric {name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"metric {name} must be finite and non-negative")
    return numeric


def pareto_front(
    candidates: Mapping[str, Mapping[str, float]],
    directions: Mapping[str, str],
) -> list[str]:
    def dominates(left: Mapping[str, float], right: Mapping[str, float]) -> bool:
        no_worse = True
        better = False
        for metric, direction in directions.items():
            if direction == "higher":
                no_worse &= left[metric] >= right[metric]
                better |= left[metric] > right[metric]
            elif direction == "lower":
                no_worse &= left[metric] <= right[metric]
                better |= left[metric] < right[metric]
            else:
                raise ValueError(f"unknown direction {direction!r} for {metric}")
        return no_worse and better

    return sorted(
        name
        for name, candidate in candidates.items()
        if not any(
            other_name != name and dominates(other, candidate)
            for other_name, other in candidates.items()
        )
    )


def validate_constraints(constraints: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    if constraints.get("schema_version") != 1:
        raise ValueError("unsupported Pareto64 constraint schema")
    requirements = constraints.get("requirements")
    priorities = constraints.get("selection_priority")
    if not isinstance(requirements, dict):
        raise ValueError("constraints require a requirements object")
    if not isinstance(priorities, list) or not priorities:
        raise ValueError("constraints require a non-empty selection_priority")
    if any(not isinstance(metric, str) or metric not in DIRECTIONS for metric in priorities):
        raise ValueError("selection_priority contains an unknown metric")
    if len(set(priorities)) != len(priorities):
        raise ValueError("selection_priority contains duplicates")

    normalized: dict[str, Any] = {}
    for metric, rule in requirements.items():
        if metric not in DIRECTIONS or not isinstance(rule, dict):
            raise ValueError(f"invalid requirement for {metric}")
        allowed_operator = "at_least" if DIRECTIONS[metric] == "higher" else "at_most"
        if set(rule) != {allowed_operator}:
            raise ValueError(
                f"requirement {metric} must contain only {allowed_operator}"
            )
        normalized[metric] = {
            allowed_operator: finite_metric(rule[allowed_operator], metric)
        }
    return normalized, priorities


def extract_e3_candidates(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if manifest.get("schema_version") != 1 or manifest.get("experiment_id") not in {
        "E3",
        "E3b",
        "E3c",
        "E3d",
    }:
        raise ValueError(
            "planner input must be a schema-1 E3, E3b, E3c, or E3d manifest"
        )
    if not str(manifest.get("status", "")).startswith("valid_"):
        raise ValueError("planner input is not a valid experiment result")
    validation = manifest.get("validation", {})
    if validation.get("quality_policy_predeclared") is not True:
        raise ValueError("manifest lacks a predeclared quality policy")
    if validation.get("performance_comparison_allowed") is not True:
        raise ValueError("manifest does not allow performance comparison")

    application = manifest.get("application")
    quality_variants = manifest.get("quality", {}).get("variants")
    if not isinstance(application, dict) or not isinstance(quality_variants, dict):
        raise ValueError("manifest lacks application or quality candidates")
    if set(application) != set(quality_variants):
        raise ValueError("application and quality candidate sets differ")

    candidates: dict[str, dict[str, Any]] = {}
    eligible: list[str] = []
    for name in sorted(application):
        record = application[name]
        quality = quality_variants[name]
        if not isinstance(record, dict) or not isinstance(quality, dict):
            raise ValueError(f"candidate {name} is malformed")
        quality_eligible = record.get("quality_eligible")
        if not isinstance(quality_eligible, bool):
            raise ValueError(f"candidate {name} lacks a quality decision")
        if quality.get("quality_eligible") is not quality_eligible:
            raise ValueError(f"candidate {name} has conflicting quality decisions")
        if quality_eligible:
            eligible.append(name)
        metrics = {
            "minimum_accuracy": finite_metric(
                record.get("minimum_accuracy"), "minimum_accuracy"
            ),
            "same_text_total_ms_median": finite_metric(
                record.get("same_text_total_ms", {}).get("median"),
                "same_text_total_ms_median",
            ),
            "maximum_quality_process_rss_kib": finite_metric(
                record.get("quality_process", {})
                .get("maximum_rss_kib", {})
                .get("max"),
                "maximum_quality_process_rss_kib",
            ),
            "package_size_bytes": finite_metric(
                record.get("package_size_bytes"), "package_size_bytes"
            ),
            "model_load_ms_median": finite_metric(
                record.get("model_load_ms", {}).get("median"),
                "model_load_ms_median",
            ),
        }
        candidates[name] = {
            "name": name,
            "framework": quality.get("framework"),
            "quality_eligible": quality_eligible,
            "metrics": metrics,
        }

    declared_eligible = validation.get("quality_eligible_variants")
    if declared_eligible != sorted(eligible):
        raise ValueError("declared quality-eligible set differs from candidate evidence")
    return candidates


def rejection_reasons(
    candidate: dict[str, Any], requirements: Mapping[str, Mapping[str, float]]
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    if not candidate["quality_eligible"]:
        reasons.append({"kind": "quality_gate", "detail": "quality_ineligible"})
    for metric, rule in requirements.items():
        observed = candidate["metrics"][metric]
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


def selection_key(candidate: Mapping[str, float], priorities: Sequence[str]) -> tuple[Any, ...]:
    values: list[float] = []
    for metric in priorities:
        value = candidate[metric]
        values.append(-value if DIRECTIONS[metric] == "higher" else value)
    return tuple(values)


def build_plan(
    manifest: dict[str, Any],
    constraints: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    constraints_path: Path | None = None,
) -> dict[str, Any]:
    requirements, priorities = validate_constraints(constraints)
    candidates = extract_e3_candidates(manifest)
    evaluated: dict[str, dict[str, Any]] = {}
    feasible: dict[str, dict[str, float]] = {}
    for name, candidate in candidates.items():
        reasons = rejection_reasons(candidate, requirements)
        evaluated[name] = {**candidate, "rejections": reasons}
        if not reasons:
            feasible[name] = candidate["metrics"]

    frontier_names = pareto_front(feasible, DIRECTIONS)
    selected_name = (
        min(
            frontier_names,
            key=lambda name: (selection_key(feasible[name], priorities), name),
        )
        if frontier_names
        else None
    )
    selected = evaluated[selected_name] if selected_name else None
    return {
        "schema_version": 1,
        "planner": "Pareto64",
        "status": "selected" if selected else "no_feasible_candidate",
        "inputs": {
            "experiment_id": manifest["experiment_id"],
            "experiment_status": manifest["status"],
            "github_run_url": manifest.get("source", {}).get("github_run_url"),
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
            "directions": DIRECTIONS,
            "weighted_score_used": False,
        },
        "evaluated": evaluated,
        "feasible_candidates": sorted(feasible),
        "pareto_frontier": [evaluated[name] for name in frontier_names],
        "selected": selected,
        "decision": (
            "No measured candidate passed both the predeclared quality gate and SLOs."
            if selected is None
            else "Selected lexicographically from the Pareto frontier using the explicit priority list."
        ),
    }
