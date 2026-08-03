#!/usr/bin/env python3
"""Freeze the E13a fail-closed cache-certificate experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


INPUT_PATHS = {
    "calibration_manifest": "results/manifests/e9c-30770403695.json",
    "e9c_contract": "experiments/e9c_contract.json",
    "selected_manifest": "results/manifests/e3f-30656151957.json",
    "models": "experiments/e3f_models.json",
    "tasks": "experiments/e3_tasks.json",
    "e9a_contract": "experiments/e9a_contract.json",
    "probe": "experiments/e13a_probe.py",
    "cell_runner": "experiments/e13a_cell.sh",
    "ingest": "experiments/e13a_ingest.py",
    "freeze": "experiments/e13a_freeze.py",
}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive_certificates(manifest: dict[str, Any]) -> dict[str, Any]:
    if (
        manifest.get("experiment_id") != "E9c"
        or manifest.get("status") != "valid_cache_generalization_output_regression"
    ):
        raise ValueError("E13a calibration is not the retained E9c negative result")

    observations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in manifest.get("points", []):
        cardinality = point.get("prefix_cardinality")
        shared_tokens = point.get("shared_prefix_tokens")
        samples = point.get("samples", {})
        for repetition in (1, 2):
            cache_off = samples.get(f"cache_off_r{repetition}", [])
            cache_on = samples.get(f"cache_on_r{repetition}", [])
            if len(cache_off) != 16 or len(cache_on) != 16:
                raise ValueError("E9c calibration cell is incomplete")
            for off, on in zip(cache_off, cache_on, strict=True):
                fingerprint = off.get("prompt_sha256")
                if (
                    not isinstance(fingerprint, str)
                    or len(fingerprint) != 64
                    or on.get("prompt_sha256") != fingerprint
                    or off.get("index") != on.get("index")
                    or off.get("task_id") != on.get("task_id")
                    or off.get("prefix_marker") != on.get("prefix_marker")
                ):
                    raise ValueError("E9c paired prompt identity differs")
                observations[fingerprint].append(
                    {
                        "prefix_cardinality": cardinality,
                        "shared_prefix_tokens": shared_tokens,
                        "repetition": repetition,
                        "index": off["index"],
                        "task_id": off["task_id"],
                        "prefix_marker": off["prefix_marker"],
                        "cache_off_http_status": off.get("http_status"),
                        "cache_on_http_status": on.get("http_status"),
                        "cache_off_error": off.get("error"),
                        "cache_on_error": on.get("error"),
                        "cache_off_response": off.get("response"),
                        "cache_on_response": on.get("response"),
                    }
                )

    if len(observations) != 48 or sum(map(len, observations.values())) != 288:
        raise ValueError("E9c calibration fingerprint inventory differs")

    allowlist: list[dict[str, Any]] = []
    denylist: list[dict[str, Any]] = []
    for fingerprint, records in sorted(observations.items()):
        responses = {
            record[key]
            for record in records
            for key in ("cache_off_response", "cache_on_response")
        }
        valid = all(
            record["cache_off_http_status"] == 200
            and record["cache_on_http_status"] == 200
            and record["cache_off_error"] is None
            and record["cache_on_error"] is None
            and isinstance(record["cache_off_response"], str)
            and isinstance(record["cache_on_response"], str)
            for record in records
        )
        entry = {
            "prompt_sha256": fingerprint,
            "paired_observations": len(records),
            "task_ids": sorted({record["task_id"] for record in records}),
            "prefix_markers": sorted({record["prefix_marker"] for record in records}),
            "points": [
                {"prefix_cardinality": cardinality, "shared_prefix_tokens": length}
                for cardinality, length in sorted(
                    {
                        (
                            record["prefix_cardinality"],
                            record["shared_prefix_tokens"],
                        )
                        for record in records
                    }
                )
            ],
            "observed_exact_responses": sorted(responses),
        }
        if valid and len(responses) == 1:
            allowlist.append(entry)
        else:
            denylist.append(entry)

    if len(allowlist) != 44 or len(denylist) != 4:
        raise ValueError("E9c calibration classification differs")
    return {
        "algorithm": (
            "Certify an exact tokenized-prompt SHA-256 only when every retained "
            "E9c cache-off/cache-on observation completed and every exact response "
            "byte string was identical. Deny any fingerprint with a failure or "
            "difference. Route fingerprints absent from both sets uncached."
        ),
        "calibration_paired_observations": 288,
        "certified_allowlist": allowlist,
        "fallback_denylist": denylist,
        "unknown_policy": "fail_closed_uncached",
        "post_observation_tuning_permitted": False,
    }


def build_contract(root: Path) -> dict[str, Any]:
    calibration = load_object(root / INPUT_PATHS["calibration_manifest"])
    e9c_contract = load_object(root / INPUT_PATHS["e9c_contract"])
    certificates = derive_certificates(calibration)
    return {
        "schema_version": 1,
        "experiment_id": "E13a",
        "title": "Fail-closed exact-fingerprint cache certificate",
        "hypothesis": (
            "A static certificate derived only from the complete retained E9c "
            "calibration can preserve byte-exact uncached outputs on a fresh "
            "native Arm64 E9c-style trace while retaining at least 1.70x aggregate "
            "throughput."
        ),
        "scope": (
            "A temporal holdout of one bounded, application-specific cache "
            "controller on the exact E7c service. This is not a server-knob sweep, "
            "an unseen-task generalization claim, or a universal cache-safety claim."
        ),
        "inputs": {
            name: {"path": path, "sha256": sha256_file(root / path)}
            for name, path in INPUT_PATHS.items()
        },
        "calibration": {
            "run_id": "30770403695",
            "run_attempt": 1,
            "artifact_name": "e9c-prompt-cache-30770403695-1",
            "artifact_id": 8840851593,
            "manifest_sha256": sha256_file(root / INPUT_PATHS["calibration_manifest"]),
            "new_holdout_results_observed_during_freeze": False,
        },
        "selected": e9c_contract["selected"],
        "service": e9c_contract["service"],
        "prompt_construction": e9c_contract["prompt_construction"],
        "workload": {
            **e9c_contract["workload"],
            "point_order": e9c_contract["execution"]["point_order"],
            "trace_requests": 165,
            "measured_requests": 144,
            "point_warmup_requests": 21,
            "fresh_process_trace": True,
        },
        "policy": certificates,
        "execution": {
            "cell_order": [
                {"policy": "all_uncached", "repetition": 1},
                {"policy": "certificate", "repetition": 1},
                {"policy": "certificate", "repetition": 2},
                {"policy": "all_uncached", "repetition": 2},
            ],
            "fresh_server_per_cell": True,
            "total_fresh_processes": 4,
            "total_requests": 660,
            "expected_controller_requests_per_trace": {
                "certified_cache": 149,
                "calibration_fallback": 16,
                "unknown_fallback": 0,
            },
            "client_concurrency": 1,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "request_failures": 0,
            "exact_baseline_repeat_mismatches": 0,
            "exact_controller_repeat_mismatches": 0,
            "exact_controller_vs_uncached_mismatches": 0,
            "required_baseline_cached_tokens": 0,
            "required_fallback_cached_tokens": 0,
            "minimum_certified_measured_cache_hit_fraction": 0.80,
            "minimum_throughput_ratio": 1.70,
            "maximum_p95_http_latency_ratio": 1.0,
            "maximum_cpu_seconds_per_request_ratio": 1.0,
            "maximum_throughput_coefficient_of_variation": 0.05,
            "maximum_ready_ms": 15000.0,
            "maximum_process_rss_kib": 8388608,
            "accepted_server_shell_exit_statuses": [0, 130],
            "server_binary_sha256": "ec60d4975757948cd330dfa82c1f8d274ea67e73cb319ce623f02232dcf61dbd",
            "weighted_score_used": False,
        },
        "negative_result_rule": (
            "Retain any output, mechanism, scheduler-dispersion, throughput, "
            "latency, CPU, startup, or RSS gate failure without changing the "
            "calibration classification, trace, order, repetitions, or thresholds."
        ),
        "claim_boundary": (
            "A passing E13a result supports only the exact 48 calibrated tokenized "
            "prompt fingerprints, exact selected model, exact E7c b10216 one-slot "
            "service, sequential frozen trace, and tested native GitHub Arm64 host. "
            "Unknown fingerprints fail closed. It makes no unseen-task, untested-"
            "sequence, concurrency, fleet, energy, PMU, local-device, cost, or "
            "other-runtime claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root)
    args.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
