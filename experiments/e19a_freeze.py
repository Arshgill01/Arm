#!/usr/bin/env python3
"""Freeze composed prefix-affinity, cache-certificate, and shared-arena serving."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


INPUT_PATHS = {
    "e13b_contract": Path("experiments/e13b_contract.json"),
    "e13b_result": Path("results/manifests/e13b-30833985784.json"),
    "e16c_contract": Path("experiments/e16c_contract.json"),
    "e16c_result": Path("results/manifests/e16c-30851609576.json"),
    "selected_manifest": Path("results/manifests/e3f-30656151957.json"),
    "models": Path("experiments/e3f_models.json"),
    "tasks": Path("experiments/e3_tasks.json"),
    "patch_1": Path(
        "patches/llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch"
    ),
    "patch_2": Path("patches/llama.cpp/0002-arm-q8-vector-narrowing-stores.patch"),
    "patch_3": Path(
        "patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch"
    ),
    "dump_patch": Path(
        "patches/llama.cpp/b10216/0006-repack-sidecar-feasibility-dump.patch"
    ),
    "loader_patch": Path(
        "patches/llama.cpp/b10216/0007-repack-sidecar-readonly-loader.patch"
    ),
    "sidecar_builder": Path("experiments/e16a_sidecar.py"),
    "constructor": Path("experiments/e16b_construct.sh"),
    "runtime_closure": Path("experiments/e7a_runtime_closure.py"),
    "calibration_probe": Path("experiments/e9c_probe.py"),
    "certificate_probe": Path("experiments/e13b_probe.py"),
    "certificate_ingest": Path("experiments/e13b_ingest.py"),
    "sidecar_source_ingest": Path("experiments/e16a_ingest.py"),
    "sidecar_loader_ingest": Path("experiments/e16b_ingest.py"),
    "probe": Path("experiments/e19a_probe.py"),
    "group_runner": Path("experiments/e19a_group.sh"),
    "freeze": Path("experiments/e19a_freeze.py"),
    "ingest": Path("experiments/e19a_ingest.py"),
    "test": Path("tests/test_e19a.py"),
}


def worker_inventory(workload: dict[str, Any]) -> list[dict[str, Any]]:
    workers = [
        {"worker": 1, "trace_requests": 0, "measured_requests": 0},
        {"worker": 2, "trace_requests": 0, "measured_requests": 0},
    ]
    for point_index, point in enumerate(workload["point_warmups"]):
        requests = [
            ("point_warmup", item) for item in point["requests"]
        ] + [("measured", item) for item in point["measured_requests"]]
        for phase, request in requests:
            worker_index = (point_index + request["prefix_marker_index"]) % 2
            workers[worker_index]["trace_requests"] += 1
            workers[worker_index]["measured_requests"] += phase == "measured"
    return workers


def build_contract(root: Path) -> dict[str, Any]:
    cache_contract = load_object(root / INPUT_PATHS["e13b_contract"])
    cache_result = load_object(root / INPUT_PATHS["e13b_result"])
    arena_contract = load_object(root / INPUT_PATHS["e16c_contract"])
    arena_result = load_object(root / INPUT_PATHS["e16c_result"])
    if (
        cache_result.get("status") != "valid_certified_cache_policy"
        or cache_result.get("decision", {}).get("policy_admitted") is not True
        or arena_result.get("status") != "valid_shared_sidecar_workers_promoted"
        or arena_result.get("promoted") is not True
        or arena_result.get("decision", {}).get(
            "multi_process_physical_sharing_claim_permitted"
        )
        is not True
        or any(
            cache_contract["selected"].get(name)
            != arena_contract["selected"].get(name)
            for name in ("candidate", "model_sha256", "model_size_bytes")
        )
        or cache_contract["service"]["source_commit"]
        != arena_contract["source"]["commit"]
    ):
        raise ValueError("E19a admitted prerequisites differ")

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    order = [
        {"policy": "all_uncached", "repetition": 1},
        {"policy": "certificate", "repetition": 1},
        {"policy": "certificate", "repetition": 2},
        {"policy": "all_uncached", "repetition": 2},
    ]
    inventory = worker_inventory(cache_contract["workload"])
    return {
        "schema_version": 1,
        "experiment_id": "E19a",
        "title": "Prefix-affined cache certificate on a shared Arm repack arena",
        "state": (
            "frozen after E13b admitted the exact cache certificate and E16c admitted "
            "two-worker physical sharing, before their composed service was launched"
        ),
        "hypothesis": (
            "The E13b fail-closed certificate retains at least 1.60x aggregate "
            "throughput with byte-exact uncached outputs when requests are bound by "
            "prefix affinity across two simultaneous workers mapping one E16c arena."
        ),
        "inputs": inputs,
        "prerequisites": {
            "cache_certificate": {
                "run_id": cache_result["github"]["run_id"],
                "status": cache_result["status"],
                "manifest_sha256": sha256_file(root / INPUT_PATHS["e13b_result"]),
                "promoted": True,
            },
            "shared_arena": {
                "run_id": arena_result["github"]["run_id"],
                "status": arena_result["status"],
                "manifest_sha256": sha256_file(root / INPUT_PATHS["e16c_result"]),
                "promoted": True,
            },
        },
        "selected": arena_contract["selected"],
        "source": arena_contract["source"],
        "build": arena_contract["build"],
        "service": arena_contract["service"],
        "mechanism": {
            **arena_contract["mechanism"],
            "worker_count": 2,
            "worker_ports": [18081, 18082],
            "all_groups_use_one_shared_sidecar": True,
            "prefix_affinity_assignment": (
                "worker = 1 + ((point_index + prefix_marker_index) modulo 2)"
            ),
            "prefix_never_moves_within_a_point": True,
            "simultaneous_measurement_barrier_required": True,
        },
        "prompt_construction": cache_contract["prompt_construction"],
        "workload": cache_contract["workload"],
        "policy": cache_contract["policy"],
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "order": order,
            "order_design": "ABBA",
            "workers_per_group": 2,
            "repetitions_per_policy": 2,
            "fresh_workers_per_group": True,
            "worker_request_inventory": inventory,
            "expected_controller_requests_per_trace": cache_contract["execution"][
                "expected_controller_requests_per_trace"
            ],
            "total_fresh_server_processes": 8,
            "total_trace_requests": 4 * cache_contract["workload"]["trace_requests"],
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "required_logical_cpus": 4,
            "required_model_name": "Neoverse-N2",
            "minimum_tensor_count": 100,
            "minimum_packed_buffer_coverage_fraction": 0.99,
            "accepted_server_shell_exit_statuses": [0, 130],
            "maximum_ready_ms_per_worker": 120000.0,
            "maximum_process_rss_kib": 7340032,
            "loader_mapping_permissions": "r--s",
            "loader_mapping_offset_hex": "00100000",
            "maximum_measurement_start_skew_ms": 10.0,
            "maximum_throughput_coefficient_of_variation": 0.05,
            "request_failures": 0,
            "exact_baseline_repeat_mismatches": 0,
            "exact_controller_repeat_mismatches": 0,
            "exact_controller_vs_uncached_mismatches": 0,
            "required_uncached_cached_tokens": 0,
            "minimum_certified_measured_cache_hit_fraction": 0.80,
            "minimum_throughput_ratio": 1.60,
            "maximum_p95_http_latency_ratio": 1.05,
            "maximum_cpu_seconds_per_request_ratio": 0.70,
            "maximum_summed_pss_ratio": 1.02,
            "maximum_summed_pss_kib": 6000000,
            "generated_sidecar_cleanup_required": True,
            "post_result_gate_change_permitted": False,
        },
        "decision": {
            "promote_only_if_every_gate_passes": True,
            "both_policies_use_identical_shared_sidecar_workers": True,
            "normal_repack_control_not_repeated": True,
            "e13b_and_e16c_remain_independently_bounded": True,
            "no_unseen_prefix_or_more_than_two_worker_claim": True,
        },
        "negative_result_rule": (
            "Retain output drift, prefix movement, cache miss, sidecar mapping failure, "
            "imbalance, throughput/latency/CPU/PSS regression, startup failure, or "
            "scheduler dispersion without changing the trace, assignment, order, "
            "repetitions, controller, source, sidecar, or acceptance gates."
        ),
        "claim_boundary": (
            "E19a can establish only composition of the exact E13b certificate and "
            "E16c read-only arena for 48 calibrated fingerprints, two prefix-affined "
            "workers, one frozen temporal trace, and one four-core native GitHub Arm "
            "host. Unknown prompts still fail closed. It makes no unseen-task, more-"
            "worker, fleet, energy, PMU, local-device, or cost claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
