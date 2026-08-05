#!/usr/bin/env python3
"""Freeze the bounded full native E21b cache-certificate matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from experiments.e21b_full_fixture import run_synthetic_replay
    from experiments.evidence_readiness import evaluate_readiness
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e21b_full_fixture import run_synthetic_replay
    from evidence_readiness import evaluate_readiness


INPUT_PATHS = {
    "preflight_contract": "experiments/e21b_preflight_contract.json",
    "preflight_manifest": "results/manifests/e21b-preflight-30983800871.json",
    "models": "experiments/e3f_models.json",
    "tasks": "experiments/e3_tasks.json",
    "e9a_contract": "experiments/e9a_contract.json",
    "online_policy": "experiments/e21a_online_policy.py",
    "openai_request": "experiments/e21b_openai_probe.py",
    "probe": "experiments/e21b_full_probe.py",
    "cell_runner": "experiments/e21b_full_cell.sh",
    "ingest": "experiments/e21b_full_ingest.py",
    "synthetic_fixture": "experiments/e21b_full_fixture.py",
    "freeze": "experiments/e21b_full_freeze.py",
    "tests": "tests/test_e21b_full.py",
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


def maximum_denied_known_routes(sequence: list[str], denied: int) -> int:
    transitions = Counter(
        ("start" if index == 0 else sequence[index - 1], current)
        for index, current in enumerate(sequence)
    )
    known_occurrences = sorted(
        (count - 1 for count in transitions.values()), reverse=True
    )
    return sum(known_occurrences[:denied])


def build_contract(root: Path) -> dict[str, Any]:
    preflight_contract = load_object(root / INPUT_PATHS["preflight_contract"])
    preflight = load_object(root / INPUT_PATHS["preflight_manifest"])
    tasks = load_object(root / INPUT_PATHS["tasks"])
    readiness_policy = load_object(root / INPUT_PATHS["readiness_policy"])
    if (
        preflight_contract.get("experiment_id") != "E21b-preflight"
        or preflight.get("status") != "valid_openai_online_certificate_preflight"
        or not all(preflight.get("gates", {}).values())
        or preflight.get("decision", {}).get("full_experiment_authorized") is not True
        or preflight.get("decision", {}).get("native_performance_claim_allowed")
        is not False
        or preflight.get("preflight_decision", {}).get("all_frozen_gates_passed")
        is not True
        or preflight.get("github", {}).get("run_id") != "30983800871"
    ):
        raise ValueError("E21b full matrix lacks its passing native preflight")
    task_ids = [item["id"] for item in tasks["tasks"]]
    if task_ids != preflight_contract["workload"]["task_ids"]:
        raise ValueError("E21b full task order differs from the passing preflight")
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
    known = served - unknown
    maximum_denied_transitions = preflight_contract["acceptance"][
        "maximum_denied_transitions"
    ]
    maximum_denied_routes = maximum_denied_known_routes(
        sequence, maximum_denied_transitions
    )
    minimum_certified_routes = known - maximum_denied_routes
    contract: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": "E21b",
        "title": "Full-quality adaptive online cache-certificate service matrix",
        "state": (
            "frozen after byte-stable complete synthetic replay and the passing "
            "native E21b preflight; before any full-matrix answer, admission, "
            "timing, resource, or result was observed"
        ),
        "inputs": {
            name: {"path": path, "sha256": sha256_file(root / path)}
            for name, path in sorted(INPUT_PATHS.items())
        },
        "selected": preflight_contract["selected"],
        "service": preflight_contract["service"],
        "client": preflight_contract["client"],
        "client_identity_sha256": preflight_contract["client_identity_sha256"],
        "identity": preflight_contract["identity"],
        "identity_sha256": preflight_contract["identity_sha256"],
        "runtime": preflight_contract["runtime"],
        "calibration": preflight_contract["calibration"],
        "preflight": {
            "run_id": preflight["github"]["run_id"],
            "run_attempt": preflight["github"]["run_attempt"],
            "artifact_id": preflight["github"]["artifact_id"],
            "artifact_digest": preflight["github"]["artifact_digest"],
            "repository_commit": preflight["github"]["repository_commit"],
            "contract_sha256": preflight["contract_sha256"],
            "summary_sha256": preflight["retention_validation"][
                "workflow_summary_sha256"
            ],
            "quality": preflight["quality"],
            "online_decisions": preflight["online_decisions"],
        },
        "prior_certificate": preflight_contract["prior_certificate"],
        "mechanism": {
            **preflight_contract["mechanism"],
            "registry_scope": "one fresh process and exact bound identity",
            "revocation": (
                "no periodic post-certification re-probe; identity changes reject "
                "the complete registry and observed revocations are counted"
            ),
        },
        "workload": {
            "task_ids": task_ids,
            "task_sequence": sequence,
            "reference_predictions": preflight_contract["workload"][
                "reference_predictions"
            ],
            "unique_prompts": len(task_ids),
            "cycles_per_cell": cycles,
            "served_requests_per_cell": served,
            "correct_per_cycle": preflight_contract["workload"]["correct_per_cycle"],
            "correct_per_cell": preflight_contract["workload"]["correct_per_cycle"]
            * cycles,
            "maximum_output_tokens": preflight_contract["workload"][
                "maximum_output_tokens"
            ],
            "minimum_cached_tokens": preflight_contract["workload"][
                "minimum_cached_tokens"
            ],
            "seed": preflight_contract["workload"]["seed"],
            "timeout_seconds": preflight_contract["workload"]["timeout_seconds"],
            "client_concurrency": 1,
        },
        "execution": {
            "cell_order": cell_order,
            "order_design": "ABBA/BAAB",
            "repetitions_per_policy": repetitions,
            "total_cells": len(cell_order),
            "total_served_requests": len(cell_order) * served,
            "total_raw_http_calls": repetitions * (served + served + unknown),
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
            "online_vs_uncached_response_mismatches": 0,
            "reference_prediction_mismatches_per_cell": 0,
            "correct_per_cell": preflight_contract["workload"]["correct_per_cycle"]
            * cycles,
            "baseline_http_calls_per_cell": served,
            "online_http_calls_per_cell": served + unknown,
            "unknown_routes": unknown,
            "unknown_shadow_calls": unknown,
            "known_routes": known,
            "minimum_certified_transitions": preflight_contract["acceptance"][
                "minimum_certified_transitions"
            ],
            "maximum_denied_transitions": maximum_denied_transitions,
            "minimum_certified_routes": minimum_certified_routes,
            "maximum_denied_fallback_routes": maximum_denied_routes,
            "minimum_transition_certification_fraction": preflight_contract[
                "acceptance"
            ]["minimum_transition_certification_fraction"],
            "revocations": 0,
        },
        "threshold_rationale": {
            "adaptive_not_exact": preflight_contract["threshold_rationale"][
                "adaptive_not_exact"
            ],
            "minimum_certified_transitions": preflight_contract["threshold_rationale"][
                "minimum_certified_transitions"
            ],
            "minimum_certified_routes": (
                f"At least {minimum_certified_routes}/{known} later-known routes "
                f"must be cached. This is the worst case implied by at most "
                f"{maximum_denied_transitions} denied transitions when the denied "
                "transitions are the most frequently repeated ones."
            ),
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
                "The preflight exposed synchronous first-use median and p95 "
                "regressions. Promotion preserves that cost and requires at least "
                "10% lifecycle throughput, at least 5% CPU/request reduction, "
                "bounded lifecycle p95, certified steady-state p95 nonregression, "
                "and cumulative break-even in every repetition. These are the same "
                "performance thresholds frozen for E21a, not post-result tuning."
            ),
        },
        "negative_result_rule": (
            "Retain every failed validity or promotion gate without changing the "
            "tasks, client, cycles, order, repetitions, adaptive ranges, state "
            "machine, calls, thresholds, or synchronous first-use accounting."
        ),
        "claim_boundary": (
            "A valid E21b result establishes exact-output adaptive online "
            "transition admission and its observed certification, denial, fallback, "
            "first-use, steady-state and break-even boundaries only for the exact "
            "E7c Q4_K_M OpenAI-compatible service, this frozen sequential 30-task "
            "four-cycle workload, and native four-vCPU GitHub Arm64 runners. It "
            "does not certify arbitrary prompts, semantic equivalence, concurrency, "
            "post-certification revocation, another model/runtime, energy, PMU, "
            "device, fleet, cost or Mac behavior."
        ),
    }
    synthetic, replay = run_synthetic_replay(contract, root)
    if (
        synthetic.get("status") != "valid_openai_online_certificate_promoted"
        or not all(synthetic.get("validity_gates", {}).values())
        or not all(synthetic.get("promotion_gates", {}).values())
        or not replay.get("byte_stable")
        or replay.get("complete_cells") != 8
        or replay.get("served_requests") != 960
    ):
        raise ValueError("E21b full complete synthetic replay differs")
    share = preflight_contract["readiness"]["plan"]["mechanism_unit"][
        "affected_runtime_share"
    ]
    readiness_plan = {
        "schema_version": 1,
        "experiment_id": "E21b",
        "target": {"runner": "ubuntu-24.04-arm", "architecture": "aarch64"},
        "mechanism_unit": {
            "status": "passed",
            "command": "python3 -m unittest tests.test_e21b_full",
            "affected_runtime_share": share,
            "component_speedup_ceiling": "unbounded",
            "system_throughput_gain_ceiling": 1.0 / (1.0 - share) - 1.0,
        },
        "synthetic_replay": {
            "status": "passed",
            "command": (
                "python3 experiments/e21b_full_fixture.py --contract "
                "experiments/e21b_full_contract.json --output /tmp/e21b-full.json"
            ),
            "control_cells": 1,
            "candidate_cells": 1,
            "complete_matrix_cells": replay["complete_cells"],
            "complete_matrix_served_requests": replay["served_requests"],
            "independent_replays": replay["independent_replays"],
            "byte_stable": replay["byte_stable"],
        },
        "native_preflight": {
            "status": "passed",
            "command": (
                "python3 experiments/e21b_preflight_retain.py --evidence-dir "
                ".scratch/e21b-preflight-30983800871 --contract "
                "experiments/e21b_preflight_contract.json --output /tmp/e21b.json"
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
                "quality-equivalent identity-bound online admission with measured "
                "first-use, steady-state and break-even boundaries"
            ),
            "alternate_values": ["deployability", "novelty", "quality"],
        },
        "budget": {
            "maximum_runtime_minutes": 45,
            "maximum_storage_bytes": 4294967296,
        },
    }
    readiness = evaluate_readiness(readiness_plan, readiness_policy)
    if readiness["decision"] != "matrix_allowed":
        raise ValueError("E21b full matrix was not authorized by readiness gate")
    contract["synthetic_replay"] = {
        "complete_cells": replay["complete_cells"],
        "served_requests": replay["served_requests"],
        "independent_replays": replay["independent_replays"],
        "byte_stable": replay["byte_stable"],
    }
    contract["readiness"] = {"plan": readiness_plan, "evaluation": readiness}
    return contract


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
