#!/usr/bin/env python3
"""Freeze the bounded full native E21a cache-generalization experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import reference_predictions
    from experiments.e21a_online_policy import identity_sha256
    from experiments.evidence_readiness import evaluate_readiness
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import reference_predictions
    from e21a_online_policy import identity_sha256
    from evidence_readiness import evaluate_readiness


INPUT_PATHS = {
    "e13b_contract": "experiments/e13b_contract.json",
    "e13b_manifest": "results/manifests/e13b-30833985784.json",
    "preflight_contract": "experiments/e21a_preflight_contract.json",
    "preflight_manifest": "results/manifests/e21a-preflight-30979498751.json",
    "selected_manifest": "results/manifests/e3f-30656151957.json",
    "models": "experiments/e3f_models.json",
    "tasks": "experiments/e3_tasks.json",
    "e9a_contract": "experiments/e9a_contract.json",
    "online_policy": "experiments/e21a_online_policy.py",
    "probe": "experiments/e21a_full_probe.py",
    "cell_runner": "experiments/e21a_full_cell.sh",
    "ingest": "experiments/e21a_full_ingest.py",
    "synthetic_fixture": "experiments/e21a_full_fixture.py",
    "freeze": "experiments/e21a_full_freeze.py",
    "tests": "tests/test_e21a_full.py",
    "readiness_module": "experiments/evidence_readiness.py",
    "readiness_policy": "experiments/evidence_readiness_policy.json",
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


def build_contract(root: Path) -> dict[str, Any]:
    preflight_contract = load_object(root / INPUT_PATHS["preflight_contract"])
    preflight = load_object(root / INPUT_PATHS["preflight_manifest"])
    selected_manifest = load_object(root / INPUT_PATHS["selected_manifest"])
    tasks = load_object(root / INPUT_PATHS["tasks"])
    readiness_policy = load_object(root / INPUT_PATHS["readiness_policy"])
    if (
        preflight.get("status") != "valid_online_transition_certificate_preflight"
        or not all(preflight.get("gates", {}).values())
        or preflight.get("decision", {}).get("full_experiment_authorized") is not True
        or preflight.get("decision", {}).get("native_performance_claim_allowed")
        is not False
    ):
        raise ValueError("E21a full experiment lacks a passing native preflight")
    task_ids = [item["id"] for item in tasks["tasks"]]
    if len(task_ids) != 30 or len(set(task_ids)) != 30:
        raise ValueError("E21a full task set differs from the original 30 tasks")
    predictions = reference_predictions(
        selected_manifest, preflight_contract["selected"]["candidate"]
    )
    task_by_id = {item["id"]: item for item in tasks["tasks"]}
    correct_per_cycle = sum(
        predictions[task_id] == task_by_id[task_id]["answer"] for task_id in task_ids
    )
    if correct_per_cycle != 23:
        raise ValueError("E21a selected 30-task reference score differs")

    repetitions = 4
    cycles = 4
    sequence = task_ids * cycles
    cell_order = [
        {"index": 1, "policy": "all_uncached", "repetition": 1},
        {"index": 2, "policy": "online", "repetition": 1},
        {"index": 3, "policy": "online", "repetition": 2},
        {"index": 4, "policy": "all_uncached", "repetition": 2},
        {"index": 5, "policy": "online", "repetition": 3},
        {"index": 6, "policy": "all_uncached", "repetition": 3},
        {"index": 7, "policy": "all_uncached", "repetition": 4},
        {"index": 8, "policy": "online", "repetition": 4},
    ]
    served = len(sequence)
    unknown = len(task_ids) + 1
    certified_routes = served - unknown
    certified_transitions = len(task_ids)
    denied_transitions = 1
    service_sha256 = hashlib.sha256(
        json.dumps(
            preflight_contract["service"], separators=(",", ":"), sort_keys=True
        ).encode()
    ).hexdigest()
    identity = {
        "model_sha256": preflight_contract["selected"]["model_sha256"],
        "server_sha256": preflight_contract["acceptance"]["server_binary_sha256"],
        "source_diff_sha256": preflight_contract["service"]["source_diff_sha256"],
        "service_sha256": service_sha256,
    }
    share = preflight_contract["readiness"]["plan"]["mechanism_unit"][
        "affected_runtime_share"
    ]
    system_ceiling = 1.0 / (1.0 - share) - 1.0
    readiness_plan = {
        "schema_version": 1,
        "experiment_id": "E21a",
        "target": {"runner": "ubuntu-24.04-arm", "architecture": "aarch64"},
        "mechanism_unit": {
            "status": "passed",
            "command": "python3 -m unittest tests.test_e21a_online_policy",
            "affected_runtime_share": share,
            "component_speedup_ceiling": "unbounded",
            "system_throughput_gain_ceiling": system_ceiling,
        },
        "synthetic_replay": {
            "status": "passed",
            "command": "python3 -m unittest tests.test_e21a_full",
            "control_cells": 1,
            "candidate_cells": 1,
            "complete_matrix_cells": len(cell_order),
            "complete_matrix_served_requests": len(cell_order) * served,
            "byte_stable": True,
        },
        "native_preflight": {
            "status": "passed",
            "command": (
                "python3 experiments/e21a_preflight_retain.py --evidence-dir "
                ".scratch/e21a-preflight-30979498751 --contract "
                "experiments/e21a_preflight_contract.json --output /tmp/e21a.json"
            ),
            "runner": "ubuntu-24.04-arm",
            "architecture": "aarch64",
            "control_cells": 1,
            "candidate_cells": 1,
            "run_id": preflight["github"]["run_id"],
            "artifact_digest": preflight["github"]["artifact_digest"],
        },
        "value_contract": {
            "minimum_product_result": {
                "metric": "throughput",
                "relative_delta": 0.10,
            },
            "claim_unlocked": (
                "identity-bound online admission for a frozen 30-prompt unseen "
                "lifecycle with an explicit break-even boundary"
            ),
            "alternate_values": ["deployability", "novelty"],
        },
        "budget": {
            "maximum_runtime_minutes": 45,
            "maximum_storage_bytes": 4294967296,
        },
    }
    readiness = evaluate_readiness(readiness_plan, readiness_policy)
    if readiness["decision"] != "matrix_allowed":
        raise ValueError("E21a full matrix was not authorized by readiness gate")
    return {
        "schema_version": 1,
        "experiment_id": "E21a",
        "title": "Full unseen-transition online cache-certificate service matrix",
        "state": (
            "frozen after mechanism/unit, complete byte-stable synthetic replay, "
            "and passing native one-control/one-online preflight; before any full "
            "matrix answer, timing, route, resource, or result was observed"
        ),
        "inputs": {
            name: {"path": path, "sha256": sha256_file(root / path)}
            for name, path in sorted(INPUT_PATHS.items())
        },
        "selected": preflight_contract["selected"],
        "service": preflight_contract["service"],
        "identity": identity,
        "identity_sha256": identity_sha256(identity),
        "runtime": preflight_contract["runtime"],
        "calibration": preflight_contract["calibration"],
        "prior_certificate": preflight_contract["prior_certificate"],
        "mechanism": preflight_contract["mechanism"],
        "workload": {
            "task_ids": task_ids,
            "task_sequence": sequence,
            "reference_predictions": predictions,
            "unique_prompts": len(task_ids),
            "cycles_per_cell": cycles,
            "served_requests_per_cell": served,
            "correct_per_cycle": correct_per_cycle,
            "correct_per_cell": correct_per_cycle * cycles,
            "maximum_output_tokens": 8,
            "minimum_cached_tokens": 8,
            "seed": 424242,
            "timeout_seconds": 30.0,
            "client_concurrency": 1,
        },
        "execution": {
            "cell_order": cell_order,
            "order_design": "ABBA/BAAB",
            "repetitions_per_policy": repetitions,
            "total_cells": len(cell_order),
            "total_served_requests": len(cell_order) * served,
            "fresh_server_per_cell": True,
            "empty_transition_registry_per_online_cell": True,
            "runner": "ubuntu-24.04-arm",
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "server_binary_sha256": preflight_contract["acceptance"][
                "server_binary_sha256"
            ],
            "server_exit_statuses": [0, 130],
            "all_uncached_route_counts": {"baseline_uncached": served},
            "all_uncached_admission_counts": {},
            "online_route_counts": {
                "certified_cache": certified_routes,
                "unknown_shadow_then_oracle": unknown,
            },
            "online_admission_counts": {
                "certified": certified_transitions,
                "denied": denied_transitions,
                "retained": certified_routes,
            },
            "certified_transitions": certified_transitions,
            "denied_transitions": denied_transitions,
            "certified_served_requests": certified_routes,
            "unknown_shadow_calls": unknown,
            "all_uncached_http_calls": served,
            "online_http_calls": served + unknown,
            "exact_response_mismatches": 0,
            "request_failures": 0,
        },
        "promotion_thresholds": {
            "minimum_throughput_ratio": 1.10,
            "maximum_cpu_ratio": 0.95,
            "maximum_lifecycle_p95_ratio": 2.25,
            "maximum_certified_p95_ratio": 1.00,
            "maximum_break_even_cycle": cycles,
            "maximum_rss_ratio": 1.03,
            "maximum_readiness_ratio": 1.05,
            "first_use_p95_nonregression_required": False,
            "reason": (
                "The preflight already exposed synchronous calibration's first-use "
                "tail. Promotion requires bounded full-lifecycle p95, certified "
                "steady-state nonregression and break-even, while the first-use "
                "regression remains explicitly reported."
            ),
        },
        "readiness": {"plan": readiness_plan, "evaluation": readiness},
        "negative_result_rule": (
            "Retain every failed validity or promotion gate without changing the "
            "tasks, cycles, order, repetitions, state machine, calls, thresholds, "
            "or synchronous first-use latency accounting."
        ),
        "claim_boundary": (
            "A promoted E21a result establishes exact-output online transition "
            "admission and its measured first-use, break-even and certified "
            "steady-state boundaries only for the exact E7c Q4_K_M service, this "
            "frozen sequential 30-task four-cycle workload, and native four-vCPU "
            "GitHub Arm64 runners. It does not certify arbitrary prompts, semantic "
            "equivalence, concurrency, another model/runtime, energy, PMU, device, "
            "fleet, cost or Mac behavior."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
