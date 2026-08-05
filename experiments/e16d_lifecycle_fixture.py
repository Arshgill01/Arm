#!/usr/bin/env python3
"""Build and replay a complete deterministic E16d lifecycle artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_inference_probe import load_reference_predictions
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e16d_lifecycle_ingest import build_summary
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_inference_probe import load_reference_predictions
    from e5b_ingest import load_object, sha256_file
    from e16d_lifecycle_ingest import build_summary


def write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build_fixture(
    evidence: Path,
    contract_path: Path,
    contract: dict[str, Any],
    root: Path,
    *,
    private_second_mapping: bool = False,
) -> None:
    (evidence / "product/logs").mkdir(parents=True)
    (evidence / "contract.json").write_bytes(contract_path.read_bytes())
    write_object(
        evidence / "github.json",
        {
            "run_id": "synthetic",
            "run_attempt": 1,
            "sha": "synthetic",
            "runner_os": "Linux",
            "runner_arch": "ARM64",
            "source_artifact_run_id": contract["prerequisite"]["e16c_artifact_run_id"],
        },
    )
    e16c = load_object(root / contract["prerequisite"]["e16c_manifest_path"])
    identity = e16c["sidecar_identity"]
    sidecar_path = "/tmp/pareto64-e16d.sidecar"
    index_path = "/tmp/pareto64-e16d.index.json"
    sidecar_sha = e16c["construction"]["sidecar_index"]["sidecar_sha256"]
    synthetic_index_sha = "1" * 64
    receipt = {
        "schema_version": 1,
        "status": "valid_persistent_arm_sidecar",
        "contract": {
            "sha256": sha256_file(root / contract["prerequisite"]["e16c_contract_path"])
        },
        "evidence": {
            "sha256": sha256_file(root / contract["prerequisite"]["e16c_manifest_path"])
        },
        "model": {"sha256": contract["selected"]["model_sha256"]},
        "runtime": {"server_sha256": contract["runtime"]["server_sha256"]},
        "identity": identity,
        "sidecar": {
            "path": sidecar_path,
            "index_path": index_path,
            "index_sha256": synthetic_index_sha,
            "index_size_bytes": 1000,
            "sha256": sidecar_sha,
            "size_bytes": contract["acceptance"]["sidecar_size_bytes"],
            "tensor_count": contract["acceptance"]["tensor_count"],
            "mode": "0444",
            "mapping_protection": "PROT_READ",
            "mapping_sharing": "MAP_SHARED",
            "mapping_offset_bytes": contract["acceptance"]["data_offset_bytes"],
        },
        "construction": {
            "server_start_to_ready_seconds": 4.0,
            "server_process_seconds": 5.0,
            "server_returncode": 0,
            "sidecar_build_seconds": 6.0,
            "full_verification_seconds": 7.0,
            "total_prepack_seconds": 18.0,
            "cleanup": {
                "deleted_raw_tensor_bytes": contract["acceptance"]["arena_size_bytes"],
                "deleted_raw_tensor_count": contract["acceptance"]["tensor_count"],
                "raw_tensor_cleanup_complete": True,
            },
        },
        "storage": {
            "raw_repack_bytes": contract["acceptance"]["arena_size_bytes"],
            "sidecar_bytes": contract["acceptance"]["sidecar_size_bytes"],
            "raw_plus_sidecar_peak_bytes": (
                contract["acceptance"]["arena_size_bytes"]
                + contract["acceptance"]["sidecar_size_bytes"]
            ),
        },
        "boundaries": {
            "cold_storage": {"measured": False, "claim_permitted": False},
            "warm_process_start": {"matched_native_evidence": True},
            "multi_worker": {
                "matched_native_evidence": True,
                "per_process_rss_reduction_claim_permitted": False,
            },
            "amortization": {
                "estimate_boundary": (
                    "Warm same-job estimate; excludes energy, money, and cold storage."
                )
            },
        },
    }
    write_object(evidence / "product/receipt.json", receipt)
    verification = {
        "schema_version": 1,
        "status": "valid_persistent_arm_sidecar",
        "receipt_verified": True,
        "sidecar_sha256": sidecar_sha,
        "index_sha256": synthetic_index_sha,
        "tensor_count": contract["acceptance"]["tensor_count"],
        "binding": identity,
        "read_only": True,
    }
    write_object(evidence / "product/verification.json", verification)
    write_object(
        evidence / "product/corruption-rejection.json",
        {
            "schema_version": 1,
            "status": "corrupt_index_rejected",
            "exit_status": 1,
            "verification_output_absent": True,
            "failure_contains": "sidecar container differs from its index",
            "sidecar_sha256_before": sidecar_sha,
            "sidecar_sha256_after": sidecar_sha,
            "index_sha256_before": synthetic_index_sha,
            "index_sha256_after": synthetic_index_sha,
            "corrupted_index_sha256": "2" * 64,
        },
    )
    plan = {
        "schema_version": 1,
        "status": "ready_to_launch_shared_sidecar_workers",
        "worker_count": 2,
        "verification_passes": 2,
        "sidecar": {
            "path": sidecar_path,
            "sha256": sidecar_sha,
            "read_only": True,
            "inode": 4242,
        },
        "workers": [
            {"worker": worker, "port": port}
            for worker, port in enumerate(
                contract["acceptance"]["worker_ports"], start=1
            )
        ],
    }
    write_object(evidence / "product/launch-plan.json", plan)
    ready = {
        "schema_version": 1,
        "status": "shared_sidecar_workers_ready",
        "worker_count": 2,
        "sidecar": plan["sidecar"],
        "workers": [
            {
                "worker": worker,
                "pid": 9000 + worker,
                "host": "127.0.0.1",
                "port": port,
                "ready_seconds": 1.0 + worker / 10,
            }
            for worker, port in enumerate(
                contract["acceptance"]["worker_ports"], start=1
            )
        ],
    }
    write_object(evidence / "product/ready.json", ready)
    write_object(
        evidence / "product/outcome.json",
        {
            "status": "sidecar_worker_group_stopped",
            "error": None,
            "readiness": ready["workers"],
            "stop_requested": True,
            "worker_returncodes": [0, 0],
        },
    )

    tasks = load_object(root / "experiments/e3_tasks.json")
    references = load_reference_predictions(
        load_object(root / "results/manifests/e3f-30656151957.json"),
        contract["selected"]["candidate"],
    )
    cases = [
        {
            "id": task["id"],
            "response": references[task["id"]],
            "predicted": references[task["id"]],
            "reference_prediction": references[task["id"]],
            "expected": task["answer"],
        }
        for task in tasks["tasks"]
    ]
    correct = sum(case["predicted"] == case["expected"] for case in cases)
    probe = {
        "schema_version": 1,
        "experiment_id": "E16c",
        "configuration": "shared_sidecar_workers",
        "workers": [
            {
                "cases": cases,
                "result": {
                    "correct": correct,
                    "total": len(cases),
                    "failures": 0,
                    "reference_prediction_mismatches": 0,
                },
            }
            for _ in range(2)
        ],
        "group": {"workers": 2, "measured_requests": 60},
    }
    write_object(evidence / "product/probe.json", probe)
    for worker in (1, 2):
        permissions = "r--p" if private_second_mapping and worker == 2 else "r--s"
        (evidence / f"product/process-maps-worker-{worker}.txt").write_text(
            f"ffff0000-ffff1000 {permissions} 00100000 08:01 4242 {sidecar_path}\n",
            encoding="utf-8",
        )
        (evidence / f"product/logs/worker-{worker}.stderr.log").write_text(
            "CPU repack sidecar: mapped "
            f"{contract['acceptance']['arena_size_bytes']} bytes read-only from "
            f"{sidecar_path} with {contract['acceptance']['tensor_count']} bound tensors\n"
            "CPU repack sidecar: validated and loaded all "
            f"{contract['acceptance']['tensor_count']} tensors without runtime repacking\n",
            encoding="utf-8",
        )
    targets = [
        {
            "path": sidecar_path,
            "size_bytes": contract["acceptance"]["sidecar_size_bytes"],
        },
        {"path": index_path, "size_bytes": 1000},
    ]
    write_object(
        evidence / "product/cleanup-plan.json",
        {
            "schema_version": 1,
            "status": "sidecar_cleanup_planned",
            "receipt_retained": True,
            "targets": targets,
            "deleted": False,
            "targets_absent": False,
        },
    )
    write_object(
        evidence / "product/cleanup-complete.json",
        {
            "schema_version": 1,
            "status": "sidecar_cleanup_complete",
            "receipt_retained": True,
            "targets": targets,
            "deleted": True,
            "targets_absent": True,
        },
    )


def replay_once(
    contract: dict[str, Any], root: Path, *, private_second_mapping: bool = False
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        contract_path = scratch / "contract.json"
        write_object(contract_path, contract)
        evidence = scratch / "evidence"
        build_fixture(
            evidence,
            contract_path,
            contract,
            root,
            private_second_mapping=private_second_mapping,
        )
        return build_summary(evidence, contract_path, root)


def run_synthetic_replay(
    contract: dict[str, Any], root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    first = replay_once(contract, root)
    second = replay_once(contract, root)
    first_bytes = (json.dumps(first, indent=2, sort_keys=True) + "\n").encode()
    second_bytes = (json.dumps(second, indent=2, sort_keys=True) + "\n").encode()
    return first, {
        "schema_version": 1,
        "experiment_id": "E16d-synthetic-replay",
        "status": "valid_complete_synthetic_lifecycle_replay",
        "independent_replays": 2,
        "byte_stable": first_bytes == second_bytes,
        "summary_sha256": hashlib.sha256(first_bytes).hexdigest(),
        "complete_gates": len(first["gates"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load_object(args.contract)
    summary, replay = run_synthetic_replay(contract, args.root)
    result = {"summary": summary, "replay": replay}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(replay, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
