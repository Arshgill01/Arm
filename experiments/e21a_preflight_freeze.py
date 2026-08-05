#!/usr/bin/env python3
"""Freeze the two-cell native E21a online-certificate preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import reference_predictions
    from experiments.e21a_online_policy import identity_sha256, synthetic_replay
    from experiments.evidence_readiness import evaluate_readiness
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import reference_predictions
    from e21a_online_policy import identity_sha256, synthetic_replay
    from evidence_readiness import evaluate_readiness


INPUT_PATHS = {
    "e13b_contract": "experiments/e13b_contract.json",
    "e13b_manifest": "results/manifests/e13b-30833985784.json",
    "selected_manifest": "results/manifests/e3f-30656151957.json",
    "models": "experiments/e3f_models.json",
    "tasks": "experiments/e3_tasks.json",
    "e9a_contract": "experiments/e9a_contract.json",
    "online_policy": "experiments/e21a_online_policy.py",
    "probe": "experiments/e21a_preflight_probe.py",
    "cell_runner": "experiments/e21a_preflight_cell.sh",
    "ingest": "experiments/e21a_preflight_ingest.py",
    "freeze": "experiments/e21a_preflight_freeze.py",
    "tests": "tests/test_e21a_online_policy.py",
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
    e13b = load_object(root / INPUT_PATHS["e13b_contract"])
    e13b_manifest = load_object(root / INPUT_PATHS["e13b_manifest"])
    selected_manifest = load_object(root / INPUT_PATHS["selected_manifest"])
    readiness_policy = load_object(root / INPUT_PATHS["readiness_policy"])
    if (
        e13b_manifest.get("status") != "valid_certified_cache_policy"
        or e13b_manifest.get("eligible") is not True
        or e13b.get("experiment_id") != "E13b"
    ):
        raise ValueError("E21a requires the valid retained E13b certificate")
    prior_fingerprints = sorted(
        item["prompt_sha256"]
        for name in ("certified_allowlist", "fallback_denylist")
        for item in e13b["policy"][name]
    )
    if len(prior_fingerprints) != 48 or len(set(prior_fingerprints)) != 48:
        raise ValueError("E13b prompt fingerprint set differs")
    predictions = reference_predictions(selected_manifest, e13b["selected"]["candidate"])
    task_ids = ["arithmetic-01", "arithmetic-02"]
    selected_predictions = {task_id: predictions[task_id] for task_id in task_ids}
    if selected_predictions != {"arithmetic-01": "B", "arithmetic-02": "C"}:
        raise ValueError("E21a selected reference predictions differ")
    service_sha256 = hashlib.sha256(
        json.dumps(e13b["service"], separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    identity = {
        "model_sha256": e13b["selected"]["model_sha256"],
        "server_sha256": e13b["acceptance"]["server_binary_sha256"],
        "source_diff_sha256": e13b["service"]["source_diff_sha256"],
        "service_sha256": service_sha256,
    }
    synthetic = synthetic_replay()
    if (
        synthetic.get("status")
        != "valid_online_transition_certificate_synthetic_replay"
        or synthetic.get("unknown_cached_attempts_served") != 0
        or synthetic.get("certified_transitions") != 2
    ):
        raise ValueError("E21a synthetic mechanism replay differs")
    share = 0.46
    system_ceiling = 1.0 / (1.0 - share) - 1.0
    readiness_plan = {
        "schema_version": 1,
        "experiment_id": "E21a-preflight",
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
            "command": "python3 -m unittest tests.test_e21a_online_policy",
            "control_cells": 1,
            "candidate_cells": 1,
            "byte_stable": synthetic_replay() == synthetic,
        },
        "native_preflight": {
            "status": "planned",
            "command": "gh workflow run online-cache-certificate-preflight.yml",
            "runner": "ubuntu-24.04-arm",
            "architecture": "aarch64",
            "control_cells": 1,
            "candidate_cells": 1,
        },
        "value_contract": {
            "minimum_product_result": {
                "metric": "throughput",
                "relative_delta": 0.10,
            },
            "claim_unlocked": (
                "identity-bound online admission of previously unseen exact transitions"
            ),
            "alternate_values": ["deployability", "novelty"],
        },
        "budget": {
            "maximum_runtime_minutes": 45,
            "maximum_storage_bytes": 4294967296,
        },
    }
    readiness = evaluate_readiness(readiness_plan, readiness_policy)
    if readiness["decision"] != "await_native_preflight":
        raise ValueError("E21a readiness gate did not stop at native preflight")
    return {
        "schema_version": 1,
        "experiment_id": "E21a-preflight",
        "title": "Unseen-transition online cache-certificate native preflight",
        "state": (
            "frozen after mechanism/unit and synthetic replay, before native "
            "preflight answers, decisions, timings, or results"
        ),
        "inputs": {
            name: {"path": path, "sha256": sha256_file(root / path)}
            for name, path in sorted(INPUT_PATHS.items())
        },
        "selected": e13b["selected"],
        "service": e13b["service"],
        "identity": identity,
        "identity_sha256": identity_sha256(identity),
        "runtime": {
            "source_run_id": e13b["calibration"]["run_id"],
            "source_artifact": e13b["calibration"]["artifact_name"],
        },
        "calibration": e13b["calibration"],
        "prior_certificate": {
            "source": "E13b exact prompt certificate",
            "prompt_fingerprints": prior_fingerprints,
            "required_unseen_preflight_prompts": True,
        },
        "mechanism": {
            "transition_key": (
                "identity + previous served prompt + previous served response + "
                "current prompt"
            ),
            "unknown_route": (
                "run cached shadow first, never serve it, then run and serve the "
                "uncached oracle"
            ),
            "admission": (
                "certify only exact output-signature equality with minimum observed "
                "cache reuse; otherwise deny"
            ),
            "known_route": "serve one cached call for an exact certified transition",
            "corrupt_or_foreign_registry": "fail closed before routing",
        },
        "workload": {
            "task_ids": task_ids,
            "task_sequence": [
                "arithmetic-01",
                "arithmetic-02",
                "arithmetic-01",
                "arithmetic-02",
                "arithmetic-01",
                "arithmetic-02",
            ],
            "reference_predictions": selected_predictions,
            "served_requests": 6,
            "maximum_output_tokens": 8,
            "minimum_cached_tokens": 8,
            "seed": 424242,
            "timeout_seconds": 30.0,
            "client_concurrency": 1,
        },
        "execution": {
            "cell_order": ["all_uncached", "online"],
            "fresh_server_per_cell": True,
            "performance_timings_diagnostic_only": True,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "server_binary_sha256": e13b["acceptance"]["server_binary_sha256"],
            "server_exit_statuses": [0, 130],
            "online_vs_uncached_response_mismatches": 0,
            "online_route_counts": {
                "certified_cache": 3,
                "unknown_shadow_then_oracle": 3,
            },
            "online_admission_counts": {
                "certified": 2,
                "denied": 1,
                "retained": 3,
            },
            "certified_transitions": 2,
            "denied_transitions": 1,
            "certified_served_requests": 3,
            "unknown_shadow_calls": 3,
            "baseline_http_calls": 6,
            "online_http_calls": 9,
            "request_failures": 0,
        },
        "readiness": {
            "plan": readiness_plan,
            "evaluation": readiness,
            "synthetic_replay": synthetic,
        },
        "negative_result_rule": (
            "Retain any identity, unseen-prompt, route-count, oracle, output, "
            "cache-mechanism, timing-schema, failure, process, runtime, or artifact "
            "failure without changing the state machine, tasks, sequence, calls, or gates."
        ),
        "claim_boundary": (
            "A passing E21a preflight establishes only API, timing-schema, exact "
            "shadow/oracle, transition-registry, and cache-reuse compatibility for two "
            "unseen prompts on one native Arm64 process per policy. Timings are "
            "diagnostic and authorize no performance, broad quality, concurrency, "
            "energy, PMU, device, fleet, cost, or other-runtime claim."
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
