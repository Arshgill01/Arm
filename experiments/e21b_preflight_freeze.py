#!/usr/bin/env python3
"""Freeze the full-quality OpenAI-compatible E21b native preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import reference_predictions
    from experiments.e21a_online_policy import identity_sha256
    from experiments.e21b_preflight_fixture import run_synthetic_replay
    from experiments.evidence_readiness import evaluate_readiness
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import reference_predictions
    from e21a_online_policy import identity_sha256
    from e21b_preflight_fixture import run_synthetic_replay
    from evidence_readiness import evaluate_readiness


INPUT_PATHS = {
    "e13b_contract": "experiments/e13b_contract.json",
    "e13b_manifest": "results/manifests/e13b-30833985784.json",
    "e21a_negative": "results/manifests/e21a-30980957266.json",
    "selected_manifest": "results/manifests/e3f-30656151957.json",
    "models": "experiments/e3f_models.json",
    "tasks": "experiments/e3_tasks.json",
    "e9a_contract": "experiments/e9a_contract.json",
    "online_policy": "experiments/e21a_online_policy.py",
    "probe": "experiments/e21b_openai_probe.py",
    "cell_runner": "experiments/e21b_preflight_cell.sh",
    "ingest": "experiments/e21b_preflight_ingest.py",
    "synthetic_fixture": "experiments/e21b_preflight_fixture.py",
    "freeze": "experiments/e21b_preflight_freeze.py",
    "tests": "tests/test_e21b_preflight.py",
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


def sha256_value(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def build_contract(root: Path) -> dict[str, Any]:
    e13b = load_object(root / INPUT_PATHS["e13b_contract"])
    e13b_manifest = load_object(root / INPUT_PATHS["e13b_manifest"])
    e21a = load_object(root / INPUT_PATHS["e21a_negative"])
    selected_manifest = load_object(root / INPUT_PATHS["selected_manifest"])
    tasks = load_object(root / INPUT_PATHS["tasks"])
    readiness_policy = load_object(root / INPUT_PATHS["readiness_policy"])
    if (
        e13b_manifest.get("status") != "valid_certified_cache_policy"
        or e13b_manifest.get("eligible") is not True
        or e21a.get("status") != "invalid_online_transition_certificate"
        or e21a.get("decision", {}).get("promoted") is not False
        or e21a.get("campaign_decision", {}).get(
            "corrected_successor_requires_full_quality_api_equivalence_preflight"
        )
        is not True
    ):
        raise ValueError("E21b lacks its retained positive and negative prerequisites")
    prior_fingerprints = sorted(
        item["prompt_sha256"]
        for name in ("certified_allowlist", "fallback_denylist")
        for item in e13b["policy"][name]
    )
    if len(prior_fingerprints) != 48 or len(set(prior_fingerprints)) != 48:
        raise ValueError("E21b prior fingerprint set differs")
    task_ids = [item["id"] for item in tasks["tasks"]]
    if len(task_ids) != 30 or len(set(task_ids)) != 30:
        raise ValueError("E21b requires the original 30-task set")
    predictions = reference_predictions(
        selected_manifest, e13b["selected"]["candidate"]
    )
    task_by_id = {item["id"]: item for item in tasks["tasks"]}
    correct = sum(predictions[name] == task_by_id[name]["answer"] for name in task_ids)
    if correct != 23:
        raise ValueError("E21b frozen reference quality differs")

    client = {
        "api_path": "/v1/chat/completions",
        "message_shape": "system instruction plus original task user prompt",
        "temperature": 0.0,
        "seed": 424242,
        "maximum_output_tokens": 8,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "cache_prompt": "explicit per route",
        "fingerprint_path": "/apply-template then /tokenize",
        "fingerprint_add_special": False,
        "fingerprint_parse_special": True,
    }
    client_identity = sha256_value(client)
    service_identity = {
        "service": e13b["service"],
        "client_identity_sha256": client_identity,
    }
    identity = {
        "model_sha256": e13b["selected"]["model_sha256"],
        "server_sha256": e13b["acceptance"]["server_binary_sha256"],
        "source_diff_sha256": e13b["service"]["source_diff_sha256"],
        "service_sha256": sha256_value(service_identity),
    }
    sequence = task_ids * 2
    contract: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": "E21b-preflight",
        "title": "Full-quality OpenAI-compatible online certificate preflight",
        "state": (
            "frozen after E21a negative recovery and before native E21b answers, "
            "admissions, timings, or results"
        ),
        "inputs": {
            name: {"path": path, "sha256": sha256_file(root / path)}
            for name, path in sorted(INPUT_PATHS.items())
        },
        "selected": e13b["selected"],
        "service": e13b["service"],
        "client": client,
        "client_identity_sha256": client_identity,
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
            "required_unseen_prompts": True,
        },
        "mechanism": {
            "transition_key": (
                "model + exact binary/source/service/client identity + previous "
                "served prompt/response + current prompt"
            ),
            "unknown_route": (
                "run cached shadow, never serve it, then run and serve uncached oracle"
            ),
            "adaptive_policy": (
                "certify exact output signature with at least eight reused tokens; "
                "otherwise persist a fail-closed denial"
            ),
            "post_result_exact_count_gate": False,
        },
        "workload": {
            "task_ids": task_ids,
            "task_sequence": sequence,
            "unique_prompts": 30,
            "cycles_per_cell": 2,
            "served_requests": len(sequence),
            "reference_predictions": predictions,
            "correct_per_cycle": correct,
            "maximum_output_tokens": 8,
            "minimum_cached_tokens": 8,
            "seed": 424242,
            "timeout_seconds": 30.0,
            "client_concurrency": 1,
        },
        "execution": {
            "cell_order": ["all_uncached", "online"],
            "fresh_server_per_cell": True,
            "empty_transition_registry": True,
            "performance_timings_diagnostic_only": True,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "server_binary_sha256": e13b["acceptance"]["server_binary_sha256"],
            "server_exit_statuses": [0, 130],
            "online_vs_uncached_response_mismatches": 0,
            "reference_prediction_mismatches_per_policy": 0,
            "correct_per_policy": correct * 2,
            "baseline_http_calls": 60,
            "online_http_calls": 91,
            "unknown_routes": 31,
            "unknown_shadow_calls": 31,
            "known_routes": 29,
            "minimum_certified_transitions": 24,
            "maximum_denied_transitions": 7,
            "minimum_certified_routes": 23,
            "maximum_denied_fallback_routes": 6,
            "minimum_transition_certification_fraction": 0.8,
        },
        "threshold_rationale": {
            "minimum_certified_transitions": (
                "At least 24 of the 30 repeating workload transitions (80%) must "
                "be reusable; this is stricter than merely repeating E21a's 10% "
                "performance target and was frozen before E21b native results."
            ),
            "adaptive_not_exact": (
                "An online safety policy must be allowed to discover unsafe "
                "transitions. Safety, quality, minimum retained share and maximum "
                "denial bounds are gates; the exact observed split is not."
            ),
        },
        "negative_result_rule": (
            "Retain any API, binary, quality, shadow/oracle, adaptive-bound, cache, "
            "process, runtime, or artifact failure. Do not relabel the E21a map or "
            "change E21b gates after native observation."
        ),
        "claim_boundary": (
            "A passing E21b preflight establishes full 30-task API/binary identity, "
            "quality, adaptive safety and timing-schema compatibility for one fresh "
            "native Arm64 process per policy. Timings are diagnostic and authorize "
            "no performance, arbitrary-prompt, concurrency, energy, PMU, device, "
            "fleet, cost or other-runtime claim."
        ),
    }
    synthetic, replay = run_synthetic_replay(contract, root)
    if (
        synthetic.get("status") != "valid_openai_online_certificate_preflight"
        or not replay.get("byte_stable")
        or replay.get("served_requests") != 120
    ):
        raise ValueError("E21b complete synthetic replay differs")
    share = 0.46
    readiness_plan = {
        "schema_version": 1,
        "experiment_id": "E21b-preflight",
        "target": {"runner": "ubuntu-24.04-arm", "architecture": "aarch64"},
        "mechanism_unit": {
            "status": "passed",
            "command": "python3 -m unittest tests.test_e21b_preflight",
            "affected_runtime_share": share,
            "component_speedup_ceiling": "unbounded",
            "system_throughput_gain_ceiling": 1.0 / (1.0 - share) - 1.0,
        },
        "synthetic_replay": {
            "status": "passed",
            "command": (
                "python3 experiments/e21b_preflight_fixture.py --contract "
                "experiments/e21b_preflight_contract.json --output /tmp/e21b.json"
            ),
            "control_cells": 1,
            "candidate_cells": 1,
            "served_requests": 120,
            "independent_replays": 2,
            "byte_stable": True,
        },
        "native_preflight": {
            "status": "planned",
            "command": "gh workflow run online-cache-certificate-openai-preflight.yml",
            "runner": "ubuntu-24.04-arm",
            "architecture": "aarch64",
            "control_cells": 1,
            "candidate_cells": 1,
        },
        "value_contract": {
            "minimum_product_result": {
                "metric": "certified_transition_fraction",
                "relative_delta": 0.8,
            },
            "claim_unlocked": (
                "quality-equivalent identity-bound online admission on the exact "
                "OpenAI-compatible service path"
            ),
            "alternate_values": ["deployability", "novelty"],
        },
        "budget": {
            "maximum_runtime_minutes": 20,
            "maximum_storage_bytes": 4294967296,
        },
    }
    readiness = evaluate_readiness(readiness_plan, readiness_policy)
    if readiness["decision"] != "await_native_preflight":
        raise ValueError("E21b readiness gate did not stop at native preflight")
    contract["readiness"] = {"plan": readiness_plan, "evaluation": readiness}
    return contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_contract(args.root.resolve())
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
