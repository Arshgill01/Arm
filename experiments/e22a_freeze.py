#!/usr/bin/env python3
"""Freeze the product-path 1/2/4-worker sidecar scaling preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

INPUT_PATHS = (
    "experiments/e16c_contract.json",
    "results/manifests/e16c-30851609576.json",
    "experiments/e3_tasks.json",
    "results/manifests/e3f-30656151957.json",
    "experiments/e3f_models.json",
    "experiments/e22a_freeze.py",
    "experiments/e22a_cell.sh",
    "experiments/e22a_ingest.py",
    "experiments/e22a_probe.py",
    "pareto64/certificate.py",
    "pareto64/cli.py",
    "pareto64/deploy.py",
    "pareto64/gateway.py",
    "pareto64/repack.py",
    "pareto64/sidecar.py",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def build_contract(root: Path) -> dict[str, Any]:
    predecessor = load_object(root / "experiments/e16c_contract.json")
    evidence = load_object(root / "results/manifests/e16c-30851609576.json")
    if (
        predecessor.get("experiment_id") != "E16c"
        or evidence.get("status") != "valid_shared_sidecar_workers_promoted"
        or evidence.get("promoted") is not True
    ):
        raise ValueError("E22a requires the promoted E16c product boundary")
    worker_counts = [1, 2, 4]
    order = [
        {"position": 1, "mode": "normal", "workers": 1},
        {"position": 2, "mode": "shared", "workers": 1},
        {"position": 3, "mode": "shared", "workers": 2},
        {"position": 4, "mode": "normal", "workers": 2},
        {"position": 5, "mode": "normal", "workers": 4},
        {"position": 6, "mode": "shared", "workers": 4},
    ]
    return {
        "schema_version": 1,
        "experiment_id": "E22a-preflight",
        "created_utc": "2026-08-06",
        "stage": "native Arm product-path scaling preflight",
        "question": (
            "Does one verified shared Arm packed-weight sidecar retain exact output "
            "and useful service behavior while summed worker PSS scales better than "
            "ordinary private repack at 1, 2, and 4 workers?"
        ),
        "scientific_boundary": {
            "preflight_only": True,
            "final_performance_claim_permitted": False,
            "fixed_memory_cap_frozen_after_preflight": False,
            "host_class": "GitHub-hosted ubuntu-24.04-arm",
            "host_is_stable_performance_authority": False,
            "cold_page_cache_claim_permitted": False,
            "energy_claim_permitted": False,
            "cost_claim_permitted": False,
        },
        "source_artifact": {
            "repository": "Arshgill01/Arm",
            "run_id": "30851609576",
            "name": "e16c-shared-repack-arena-30851609576-1",
        },
        "selected": predecessor["selected"],
        "source": predecessor["source"],
        "build": predecessor["build"],
        "service": {
            **predecessor["service"],
            "threads": 1,
            "threads_batch": 1,
            "reason_for_thread_count": (
                "One matched thread per worker exposes aggregate scaling on the "
                "four-logical-CPU preflight host without changing arithmetic, model, "
                "request, cache, context, batch, or sidecar mechanism."
            ),
        },
        "matrix": {
            "modes": ["normal", "shared"],
            "worker_counts": worker_counts,
            "repetitions": 1,
            "order": order,
            "same_worker_count_pair_required": True,
            "full_quality_trace_per_worker": True,
            "gateway_smoke_after_direct_measurement": True,
        },
        "workload": {
            "tasks": 30,
            "warmup_task_ids": ["arithmetic-02", "logic-01"],
            "maximum_output_tokens": 8,
            "seed": 424242,
            "timeout_seconds": 60,
            "prompt_cache": True,
            "requests_per_worker": 30,
            "client_concurrency_per_worker": 1,
        },
        "measurements": [
            "exact response and reference prediction match per request",
            "successful request count",
            "aggregate requests per second",
            "per-worker and aggregate p50/p95/maximum latency",
            "per-worker and summed RSS/PSS after workload",
            "throughput per GiB of summed PSS",
            "one-worker and all-worker warm readiness",
            "minor and major page faults",
            "per-worker CPU time",
            "shared sidecar device/inode and read-only MAP_SHARED regions",
            "host topology, load, steal visibility, and perf availability",
            "sidecar construction time, storage, and peak-space accounting",
        ],
        "advance": {
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "response_differences_between_modes": 0,
            "minimum_shared_throughput_ratio_per_count": 0.90,
            "maximum_shared_p95_latency_ratio_per_count": 1.15,
            "minimum_pss_saved_kib_at_two_workers": 524288,
            "minimum_pss_saved_kib_at_four_workers": 1048576,
            "maximum_four_to_two_pss_savings_collapse_ratio": 0.90,
            "all_shared_workers_map_one_verified_inode_read_only": True,
            "post_result_gate_change_permitted": False,
        },
        "successor_rule": (
            "Freeze a stable-host fixed-memory contract only if exactness and "
            "mechanism gates pass and the 4-worker PSS curve remains materially "
            "better without a large throughput or p95 regression."
        ),
        "inputs": {path: {"sha256": sha256_file(root / path)} for path in INPUT_PATHS},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    contract = build_contract(arguments.root.resolve())
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
