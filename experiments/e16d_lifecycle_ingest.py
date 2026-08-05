#!/usr/bin/env python3
"""Validate the clean-checkout E16d persistent-sidecar product lifecycle."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file


MAP_PATTERN = re.compile(
    r"^[0-9a-f]+-[0-9a-f]+\s+(?P<permissions>\S+)\s+"
    r"(?P<offset>[0-9a-f]+)\s+(?P<device>\S+)\s+"
    r"(?P<inode>\d+)\s+(?P<path>.+)$"
)


def validate_contract(contract: dict[str, Any], root: Path) -> None:
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E16d"
        or contract.get("state")
        != "frozen_after_byte_stable_synthetic_replay_before_native_lifecycle"
    ):
        raise ValueError("contract does not identify frozen E16d")
    for name, item in contract.get("inputs", {}).items():
        path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise ValueError(f"E16d frozen input differs for {name}")


def parse_sidecar_mapping(path: Path, expected_path: str) -> dict[str, Any] | None:
    matches = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = MAP_PATTERN.match(line)
        if match is not None and match.group("path") == expected_path:
            matches.append(match.groupdict())
    if len(matches) != 1:
        return None
    return {
        **matches[0],
        "inode": int(matches[0]["inode"]),
    }


def mechanism_log(path: Path, arena_bytes: int, tensors: int) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    mapped = (
        f"CPU repack sidecar: mapped {arena_bytes} bytes read-only" in text
        and f"with {tensors} bound tensors" in text
    )
    skipped = (
        f"CPU repack sidecar: validated and loaded all {tensors} tensors "
        "without runtime repacking"
    ) in text
    return {
        "mapped_read_only": mapped,
        "all_tensors_loaded_without_runtime_repacking": skipped,
        "identity_rejection_observed": "identity mismatch" in text.lower(),
    }


def quality_summary(probe: dict[str, Any]) -> dict[str, Any]:
    workers = probe.get("workers", [])
    answers = [
        [
            {
                "task_id": case.get("id"),
                "response": case.get("response"),
                "prediction": case.get("predicted"),
                "reference_prediction": case.get("reference_prediction"),
                "expected": case.get("expected"),
            }
            for case in worker.get("cases", [])
        ]
        for worker in workers
    ]
    return {
        "workers": [
            {
                "worker": index + 1,
                "correct": worker.get("result", {}).get("correct"),
                "total": worker.get("result", {}).get("total"),
                "request_failures": worker.get("result", {}).get("failures"),
                "reference_prediction_mismatches": worker.get("result", {}).get(
                    "reference_prediction_mismatches"
                ),
                "answers": answers[index],
            }
            for index, worker in enumerate(workers)
        ],
        "worker_answer_mismatches": (
            sum(
                left != right
                for left, right in zip(answers[0], answers[1], strict=True)
            )
            if len(answers) == 2 and len(answers[0]) == len(answers[1])
            else None
        ),
        "group_measured_requests": probe.get("group", {}).get("measured_requests"),
    }


def build_summary(evidence: Path, contract_path: Path, root: Path) -> dict[str, Any]:
    contract = load_object(contract_path)
    validate_contract(contract, root)
    retained_contract = evidence / "contract.json"
    if retained_contract.read_bytes() != contract_path.read_bytes():
        raise ValueError("E16d retained contract differs")

    github = load_object(evidence / "github.json")
    receipt = load_object(evidence / "product/receipt.json")
    verification = load_object(evidence / "product/verification.json")
    plan = load_object(evidence / "product/launch-plan.json")
    ready = load_object(evidence / "product/ready.json")
    outcome = load_object(evidence / "product/outcome.json")
    probe = load_object(evidence / "product/probe.json")
    cleanup_plan = load_object(evidence / "product/cleanup-plan.json")
    cleanup_complete = load_object(evidence / "product/cleanup-complete.json")
    corruption = load_object(evidence / "product/corruption-rejection.json")
    expected = contract["acceptance"]
    sidecar = receipt.get("sidecar", {})
    construction = receipt.get("construction", {})
    storage = receipt.get("storage", {})
    boundaries = receipt.get("boundaries", {})
    quality = quality_summary(probe)
    mappings = [
        parse_sidecar_mapping(
            evidence / f"product/process-maps-worker-{worker}.txt",
            sidecar.get("path", ""),
        )
        for worker in (1, 2)
    ]
    logs = [
        mechanism_log(
            evidence / f"product/logs/worker-{worker}.stderr.log",
            expected["arena_size_bytes"],
            expected["tensor_count"],
        )
        for worker in (1, 2)
    ]
    worker_ports = [item.get("port") for item in ready.get("workers", [])]
    worker_pids = [item.get("pid") for item in ready.get("workers", [])]
    target_paths = {item.get("path") for item in cleanup_complete.get("targets", [])}
    expected_paths = {sidecar.get("path"), sidecar.get("index_path")}
    gates = {
        "exact_frozen_product_inputs": (
            receipt.get("contract", {}).get("sha256")
            == sha256_file(root / contract["prerequisite"]["e16c_contract_path"])
            and receipt.get("evidence", {}).get("sha256")
            == sha256_file(root / contract["prerequisite"]["e16c_manifest_path"])
            and receipt.get("model", {}).get("sha256")
            == contract["selected"]["model_sha256"]
            and receipt.get("runtime", {}).get("server_sha256")
            == contract["runtime"]["server_sha256"]
        ),
        "native_arm64": (
            github.get("runner_arch") == "ARM64"
            and github.get("runner_os") == "Linux"
            and receipt.get("identity", {}).get("cpu", {}).get("architecture")
            == "aarch64"
        ),
        "prepack_constructed_full_read_only_sidecar": (
            receipt.get("status") == "valid_persistent_arm_sidecar"
            and sidecar.get("size_bytes") == expected["sidecar_size_bytes"]
            and sidecar.get("tensor_count") == expected["tensor_count"]
            and sidecar.get("mode") == "0444"
            and sidecar.get("mapping_protection") == "PROT_READ"
            and sidecar.get("mapping_sharing") == "MAP_SHARED"
            and sidecar.get("mapping_offset_bytes") == expected["data_offset_bytes"]
        ),
        "construction_and_storage_cost_recorded": (
            all(
                isinstance(construction.get(name), (int, float))
                and construction[name] > 0
                for name in (
                    "server_start_to_ready_seconds",
                    "server_process_seconds",
                    "sidecar_build_seconds",
                    "full_verification_seconds",
                    "total_prepack_seconds",
                )
            )
            and storage.get("raw_repack_bytes") == expected["arena_size_bytes"]
            and storage.get("sidecar_bytes") == expected["sidecar_size_bytes"]
            and storage.get("raw_plus_sidecar_peak_bytes")
            == expected["arena_size_bytes"] + expected["sidecar_size_bytes"]
        ),
        "generated_raw_tensors_cleaned": (
            construction.get("cleanup", {}).get("raw_tensor_cleanup_complete") is True
            and construction.get("cleanup", {}).get("deleted_raw_tensor_count")
            == expected["tensor_count"]
            and construction.get("cleanup", {}).get("deleted_raw_tensor_bytes")
            == expected["arena_size_bytes"]
        ),
        "warm_cold_amortized_boundaries_explicit": (
            boundaries.get("cold_storage", {}).get("measured") is False
            and boundaries.get("cold_storage", {}).get("claim_permitted") is False
            and boundaries.get("warm_process_start", {}).get("matched_native_evidence")
            is True
            and boundaries.get("multi_worker", {}).get("matched_native_evidence")
            is True
            and boundaries.get("multi_worker", {}).get(
                "per_process_rss_reduction_claim_permitted"
            )
            is False
            and "energy"
            in boundaries.get("amortization", {}).get("estimate_boundary", "")
        ),
        "independent_full_verification": (
            verification.get("status") == "valid_persistent_arm_sidecar"
            and verification.get("receipt_verified") is True
            and verification.get("sidecar_sha256") == sidecar.get("sha256")
            and verification.get("tensor_count") == expected["tensor_count"]
            and verification.get("binding") == receipt.get("identity")
            and verification.get("read_only") is True
            and verification.get("index_sha256") == sidecar.get("index_sha256")
        ),
        "corrupted_index_rejected_without_sidecar_change": (
            corruption.get("status") == "corrupt_index_rejected"
            and corruption.get("exit_status") not in {None, 0}
            and corruption.get("verification_output_absent") is True
            and corruption.get("failure_contains")
            == "sidecar container differs from its index"
            and corruption.get("sidecar_sha256_before") == sidecar.get("sha256")
            and corruption.get("sidecar_sha256_after") == sidecar.get("sha256")
            and corruption.get("index_sha256_before") == sidecar.get("index_sha256")
            and corruption.get("index_sha256_after") == sidecar.get("index_sha256")
            and corruption.get("corrupted_index_sha256")
            not in {None, sidecar.get("index_sha256")}
        ),
        "two_verified_workers_ready": (
            plan.get("status") == "ready_to_launch_shared_sidecar_workers"
            and plan.get("worker_count") == 2
            and plan.get("verification_passes") == 2
            and ready.get("status") == "shared_sidecar_workers_ready"
            and ready.get("worker_count") == 2
            and worker_ports == expected["worker_ports"]
            and len(set(worker_pids)) == 2
            and all(isinstance(pid, int) and pid > 1 for pid in worker_pids)
        ),
        "exact_quality_on_both_workers": (
            quality["group_measured_requests"] == 60
            and quality["worker_answer_mismatches"] == 0
            and len(quality["workers"]) == 2
            and all(
                item["correct"] == expected["correct_per_worker"]
                and item["total"] == expected["tasks_per_worker"]
                and item["request_failures"] == 0
                and item["reference_prediction_mismatches"] == 0
                for item in quality["workers"]
            )
        ),
        "runtime_repack_skipped_after_binding": (
            len(logs) == 2
            and all(
                item["mapped_read_only"]
                and item["all_tensors_loaded_without_runtime_repacking"]
                and not item["identity_rejection_observed"]
                for item in logs
            )
        ),
        "same_read_only_shared_inode_mapped": (
            all(item is not None for item in mappings)
            and all(item["permissions"] == "r--s" for item in mappings if item)
            and all(
                int(item["offset"], 16) == expected["data_offset_bytes"]
                for item in mappings
                if item
            )
            and len({item["inode"] for item in mappings if item}) == 1
            and mappings[0]["inode"] == plan.get("sidecar", {}).get("inode")
        ),
        "controlled_worker_group_shutdown": (
            outcome.get("status") == "sidecar_worker_group_stopped"
            and outcome.get("error") is None
            and outcome.get("stop_requested") is True
            and len(outcome.get("worker_returncodes", [])) == 2
            and all(
                status in expected["worker_exit_statuses"]
                for status in outcome.get("worker_returncodes", [])
            )
        ),
        "receipt_bound_cleanup_complete": (
            cleanup_plan.get("status") == "sidecar_cleanup_planned"
            and cleanup_plan.get("deleted") is False
            and cleanup_complete.get("status") == "sidecar_cleanup_complete"
            and cleanup_complete.get("deleted") is True
            and cleanup_complete.get("targets_absent") is True
            and cleanup_complete.get("receipt_retained") is True
            and target_paths == expected_paths
        ),
    }
    valid = all(gates.values())
    return {
        "schema_version": 1,
        "experiment_id": "E16d",
        "status": (
            "valid_product_sidecar_lifecycle"
            if valid
            else "invalid_product_sidecar_lifecycle"
        ),
        "contract_sha256": sha256_file(contract_path),
        "github": github,
        "identity": receipt.get("identity"),
        "sidecar": sidecar,
        "construction": construction,
        "storage": storage,
        "boundaries": boundaries,
        "verification": verification,
        "launch": {
            "plan": plan,
            "ready": ready,
            "outcome": outcome,
            "mappings": mappings,
            "mechanism_logs": logs,
        },
        "quality": quality,
        "cleanup": {
            "plan": cleanup_plan,
            "complete": cleanup_complete,
        },
        "corruption_rejection": corruption,
        "gates": gates,
        "failed_gates": sorted(name for name, passed in gates.items() if not passed),
        "decision": {
            "valid": valid,
            "clean_checkout_lifecycle_validated": valid,
            "product_sidecar_workflow_promoted": valid,
            "new_native_performance_claim_allowed": False,
            "cold_start_claim_allowed": False,
            "per_process_rss_reduction_claim_allowed": False,
        },
        "claim_boundary": contract["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_summary(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"status": result["status"], "failed_gates": result["failed_gates"]},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
