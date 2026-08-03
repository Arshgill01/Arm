#!/usr/bin/env python3
"""Freeze a bounded asymmetric prefill/decode scheduler experiment."""

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
    "manifest": Path("results/manifests/e3f-30656151957.json"),
    "models": Path("experiments/e3f_models.json"),
    "tasks": Path("experiments/e3_tasks.json"),
    "e9a_contract": Path("experiments/e9a_contract.json"),
    "e9a_manifest": Path("results/manifests/e9a-30764802071.json"),
    "e9a_report": Path("results/reports/e9a-final-service-comparison.md"),
    "e5j_manifest": Path("results/manifests/e5j-30677332825.json"),
    "e5j_report": Path("results/reports/e5j-thread-efficiency-profile.md"),
    "probe": Path("experiments/e5b_inference_probe.py"),
    "cell_runner": Path("experiments/e15a_split_scheduler_cell.sh"),
    "freeze": Path("experiments/e15a_split_scheduler_freeze.py"),
    "ingest": Path("experiments/e15a_split_scheduler_ingest.py"),
    "test": Path("tests/test_e15a.py"),
}


def require_true(value: dict[str, Any], names: tuple[str, ...], label: str) -> None:
    validation = value.get("validation")
    if not isinstance(validation, dict) or not all(
        validation.get(name) is True for name in names
    ):
        raise ValueError(f"{label} required validation differs")


def build_contract(root: Path) -> dict[str, Any]:
    e9a_contract = load_object(root / INPUT_PATHS["e9a_contract"])
    e9a = load_object(root / INPUT_PATHS["e9a_manifest"])
    e5j = load_object(root / INPUT_PATHS["e5j_manifest"])
    if (
        e9a.get("status") != "valid_final_service_win"
        or e9a.get("selection", {}).get("candidate") != "ministral3_3b_q4_k_m"
        or e9a.get("selection", {}).get("model_sha256")
        != "fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4"
        or e9a.get("platform", {}).get("architecture") != "aarch64"
        or e9a.get("platform", {}).get("logical_cpus") != 2
        or e9a.get("platform", {}).get("model_name") != "Neoverse-N2"
    ):
        raise ValueError("E15a exact E9a prerequisite differs")
    require_true(
        e9a,
        (
            "binary_and_dependency_closures_hashed",
            "fresh_server_per_cell",
            "measured_window_process_cpu_validated",
            "native_arm64_same_job",
            "raw_answers_retained_in_manifest",
            "reverse_balanced_four_repetitions",
        ),
        "E9a",
    )
    if (
        e5j.get("status") != "valid_selected_inference_no_thread_efficiency_win"
        or e5j.get("selection", {}).get("selected_configuration") != "threads4"
        or e5j.get("selection", {}).get("selected_threads") != 4
    ):
        raise ValueError("E15a exact E5j tied-thread prerequisite differs")

    service = e9a_contract["profiles"]["e7c_final"]
    base = {
        **service["service"],
        "client_concurrency": 1,
        "threads_decode": 4,
        "threads_batch": 4,
    }
    base.pop("threads")
    configurations = {
        "tied4_4": {**base, "threads_decode": 4, "threads_batch": 4},
        "split2_4": {**base, "threads_decode": 2, "threads_batch": 4},
        "split1_4": {**base, "threads_decode": 1, "threads_batch": 4},
        "prefill_control4_2": {
            **base,
            "threads_decode": 4,
            "threads_batch": 2,
        },
    }
    order_names = (
        ("tied4_4", "split2_4", "prefill_control4_2", "split1_4"),
        ("split2_4", "split1_4", "tied4_4", "prefill_control4_2"),
        ("split1_4", "prefill_control4_2", "split2_4", "tied4_4"),
        ("prefill_control4_2", "tied4_4", "split1_4", "split2_4"),
    )
    order = [
        {"configuration": name, "repetition": repetition}
        for repetition, names in enumerate(order_names, 1)
        for name in names
    ]
    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    return {
        "schema_version": 1,
        "experiment_id": "E15a",
        "title": "Bounded asymmetric prefill/decode scheduler boundary",
        "state": (
            "frozen before observing any independent thread-pool result; the four "
            "points are mechanism-selected from E9a's two-core topology and E5j's "
            "rejected tied-thread result, not from a broad knob sweep"
        ),
        "hypothesis": (
            "Retaining four batch/prefill threads while reducing only decode threads "
            "to the physical two-core count can reduce measured CPU seconds per request "
            "by at least two percent without more than two percent throughput, median, "
            "or p95 regression on the exact prefill-dominated E9a end-product workload."
        ),
        "scope": (
            "Four causal scheduler points on the exact E9a E7c service: tied 4/4, "
            "decode 2 with prefill 4, decode 1 with prefill 4, and a prefill-reduced "
            "4/2 negative control. No placement, polling, priority, chunk, model, "
            "cache, batch, context, or build knob changes."
        ),
        "inputs": inputs,
        "prerequisites": {
            "e9a": {
                "run_id": "30764802071",
                "run_attempt": 1,
                "artifact_name": "e9a-final-service-30764802071-1",
                "artifact_id": 8838874234,
                "artifact_digest": "sha256:3d360aed5fd02abf5421c3a23309f1abda56bf5f96c0e406a5c13897c15aae70",
                "artifact_size_bytes": 18440490,
                "workflow_summary_sha256": "39424e7f3a43a3a05b4139609224584945c8da7c1de66a9f224e8c7184de012d",
                "retained_manifest_sha256": sha256_file(
                    root / INPUT_PATHS["e9a_manifest"]
                ),
                "required_status": e9a["status"],
            },
            "e5j": {
                "run_id": "30677332825",
                "retained_manifest_sha256": sha256_file(
                    root / INPUT_PATHS["e5j_manifest"]
                ),
                "required_status": e5j["status"],
                "finding": (
                    "Tied 2/2 and 3/3 reduced CPU time by only 1.36% and 0.11% "
                    "while losing 48.82% and 24.48% throughput."
                ),
            },
        },
        "selected": {
            "candidate": e9a["selection"]["candidate"],
            "reference_correct": e9a["selection"]["correct"],
            "reference_total": e9a["selection"]["total"],
            "reference_accuracy": e9a["selection"]["accuracy"],
            "model_sha256": e9a["selection"]["model_sha256"],
            "model_size_bytes": e9a["selection"]["model_size_bytes"],
            "repository": "unsloth/Ministral-3-3B-Instruct-2512-GGUF",
            "revision": "7564922f37fa5bbb62b87f09a55c12f1f91d7a6a",
            "path": "Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
        },
        "runtime": {
            "source": service["source"],
            "build": service["build"],
            "server_sha256": "e15e14bd5d4f86e09a79603862f52db841de758ecc21b2c476a2ba92cc8ee40e",
            "server_size_bytes": 72488,
            "runtime_closure_sha256": "a441ab5943b5dea87ae713afff6573c62a874cf919fa1b0fa8908073ecabdf8b",
            "runtime_closure_file_count": 8,
            "runtime_closure_total_size_bytes": 19857448,
            "binary_reuse": (
                "Reuse the exact E9a E7c artifact closure; do not rebuild or add a "
                "later endpoint, selective-repack, or sidecar patch."
            ),
        },
        "request": {
            "instruction_role": "system",
            "chat_template_mode": "model_jinja_system_instruction",
            "temperature": 0.0,
            "seed": 424242,
            "max_output_tokens": 8,
            "timeout_seconds": 30.0,
            "warmup_task_ids": ["arithmetic-02", "logic-01"],
            "measured_tasks": 30,
            "client_concurrency": 1,
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "required_logical_cpus": 2,
            "configurations": configurations,
            "baseline_configuration": "tied4_4",
            "candidate_configurations": ["split2_4", "split1_4"],
            "negative_control_configuration": "prefill_control4_2",
            "repetitions_per_configuration": 4,
            "fresh_server_per_cell": True,
            "same_job": True,
            "order_design": "four-sequence Williams balanced order",
            "order": order,
            "total_fresh_processes": 16,
            "total_measured_requests": 480,
        },
        "acceptance": {
            "required_architecture": "aarch64",
            "required_model_name": "Neoverse-N2",
            "required_logical_cpus": 2,
            "http_status": 200,
            "termination_reason": "stop",
            "request_failures": 0,
            "reference_prediction_mismatches": 0,
            "minimum_cached_tokens_per_request": 1,
            "minimum_candidate_throughput_ratio": 0.98,
            "maximum_candidate_median_http_latency_ratio": 1.02,
            "maximum_candidate_p95_http_latency_ratio": 1.02,
            "maximum_candidate_cpu_seconds_per_request_ratio": 0.98,
            "maximum_candidate_encode_latency_ratio": 1.02,
            "maximum_throughput_coefficient_of_variation": 0.05,
            "maximum_ready_ms": 15000.0,
            "maximum_process_rss_kib": 8388608,
            "accepted_server_shell_exit_statuses": [0, 130],
            "weighted_score_used": False,
        },
        "selection": {
            "eligible": (
                "Only split2_4 and split1_4 may promote, and only after every exact "
                "quality, cache, throughput, median, p95, encode, CPU, dispersion, "
                "readiness, RSS, runtime, and mechanism gate passes."
            ),
            "tie_breakers": [
                "lowest median server CPU seconds per request",
                "highest median throughput",
                "more decode threads",
                "configuration name",
            ],
            "no_win_rule": "Retain tied4_4 when no split candidate passes every gate.",
        },
        "measurement_boundary": (
            "Linux server-process CPU counters are sampled after two warmups and only "
            "around the 30 measured requests. Artifact download, model download, "
            "readiness, warmups, client CPU, metrics, and shutdown are excluded. CPU "
            "time is not energy or power."
        ),
        "negative_result_rule": (
            "Retain quality drift, mechanism mismatch, scheduler noise, tail regression, "
            "CPU non-improvement, or a no-win result without changing configurations, "
            "order, repetitions, workload, or thresholds."
        ),
        "claim_boundary": (
            "E15a can establish only an exact end-product split-thread result on one "
            "two-core native GitHub Arm64 runner. It does not establish long-context, "
            "long-generation, placement, polling, priority, KleidiAI chunk, many-core, "
            "energy, PMU, local-device, fleet, cost, or other-runtime behavior."
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
