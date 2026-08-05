#!/usr/bin/env python3
"""Retain the independently replayed nine-artifact E12b frontier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e12b_artifact_recovery import build_recovered_aggregate
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e12b_artifact_recovery import build_recovered_aggregate
    from e5b_ingest import load_object, sha256_file


RUN_ID = 30869536393
AGGREGATE_JOB_ID = 91905283851
HEAD_SHA = "3ab529e82e9a981857be3ebe108c58a774c65581"
INVENTORIED_FILES_PER_CELL = 14497
RAW_RESPONSES_PER_CELL = 14374
ARTIFACTS = {
    "e12b_q3_k_m_control": {
        "job_id": 91868485741,
        "artifact_id": 8881548408,
        "size_bytes": 44984860,
        "digest": "sha256:a4f1b40f73f50602215db682d265f5de19f634786c50afa2f0242876b0eddff1",
    },
    "e12b_q3_k_m_imatrix": {
        "job_id": 91868485795,
        "artifact_id": 8881506284,
        "size_bytes": 45007401,
        "digest": "sha256:f61b735d43a42a7d2406a543e59290ca8eb855046622cc9ba841fec006679e68",
    },
    "e12b_iq4_xs_control": {
        "job_id": 91868485714,
        "artifact_id": 8880346107,
        "size_bytes": 44971278,
        "digest": "sha256:6b63c8959a82e0fea7d17ba074a7f69191137d8c2cdefdbb08465714fdd989ad",
    },
    "e12b_iq4_xs_imatrix": {
        "job_id": 91868485763,
        "artifact_id": 8880385034,
        "size_bytes": 44983722,
        "digest": "sha256:4017d47cfa832ea9f89dc9492a970f8c41835837725453c3a6702f51ad27caa4",
    },
    "e12b_q4_k_s_control": {
        "job_id": 91868485777,
        "artifact_id": 8879212437,
        "size_bytes": 44935583,
        "digest": "sha256:04887ad6298cfb745633bea5953dcdbdf0e046ebd26cbba7f2259a89170c1a69",
    },
    "e12b_q4_k_s_imatrix": {
        "job_id": 91868485790,
        "artifact_id": 8879212938,
        "size_bytes": 44959072,
        "digest": "sha256:02b057360e7ac5c3b5cc447faa5069aeef793b4ad22e71a966dcef9035c9c0e1",
    },
    "e12b_q3_k_m_output_embed_q6": {
        "job_id": 91868485766,
        "artifact_id": 8881643141,
        "size_bytes": 45108112,
        "digest": "sha256:b0be139c2a513810af1a42407c9957da6a87d8e5a6ba6777b42c2619e5e0055b",
    },
    "e12b_iq4_xs_v_down_q5": {
        "job_id": 91868485759,
        "artifact_id": 8880257780,
        "size_bytes": 45029361,
        "digest": "sha256:38a258c3f3f8bc237f605918143cd5591a7f6ff68d6d097fc445fd5514896b26",
    },
    "e12b_q4_k_s_edge_layers_q6": {
        "job_id": 91868485807,
        "artifact_id": 8879229796,
        "size_bytes": 45033332,
        "digest": "sha256:559252a05557cdf100e950a5578a48eaf3aea6b186467168762a1b67f63ee269",
    },
}


def artifact_name(candidate: str) -> str:
    return f"e12b-actual-{candidate}-{RUN_ID}-1"


def validate_workflow_inventory(evidence: Path, candidate: str) -> dict[str, Any]:
    inventory = evidence / "file-inventory-sha256.txt"
    marker = f"/results/raw/e12b-{candidate}-{RUN_ID}-1/"
    entries: dict[str, str] = {}
    total_bytes = 0
    for line in inventory.read_text().splitlines():
        digest, separator, absolute = line.partition("  ")
        if not separator or len(digest) != 64 or marker not in absolute:
            raise ValueError(f"E12b {candidate} inventory line differs")
        relative = absolute.split(marker, 1)[1]
        path = evidence / relative
        if (
            relative in entries
            or not path.is_file()
            or sha256_file(path) != digest
        ):
            raise ValueError(f"E12b {candidate} inventory differs for {relative}")
        entries[relative] = digest
        total_bytes += path.stat().st_size
    raw = [name for name in entries if name.startswith("raw/")]
    preflight = [
        name for name in entries if name.startswith("preflight-raw/")
    ]
    required = {
        "build/runtime-closure.json",
        "contract.json",
        "e12a/imatrix.gguf",
        "model-metadata.json",
        "probe.json",
        "quantize-command.json",
        "summary.json",
    }
    if (
        len(entries) != INVENTORIED_FILES_PER_CELL
        or len(raw) != RAW_RESPONSES_PER_CELL
        or len(preflight) != 8
        or not required.issubset(entries)
        or not (evidence / "disk-after.txt").is_file()
    ):
        raise ValueError(f"E12b {candidate} artifact inventory is incomplete")
    return {
        "workflow_inventory_sha256": sha256_file(inventory),
        "workflow_inventory_files": len(entries),
        "workflow_inventory_bytes": total_bytes,
        "raw_responses": len(raw),
        "preflight_raw_responses": len(preflight),
        "disk_after_sha256": sha256_file(evidence / "disk-after.txt"),
        "all_workflow_inventoried_files_verified": True,
    }


def validate_github(
    run: dict[str, Any], artifact_metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    jobs = {job.get("databaseId"): job for job in run.get("jobs", [])}
    artifacts = {item.get("id"): item for item in artifact_metadata.get("artifacts", [])}
    aggregate = jobs.get(AGGREGATE_JOB_ID, {})
    if (
        str(run.get("databaseId")) != str(RUN_ID)
        or run.get("status") != "completed"
        or run.get("conclusion") != "failure"
        or run.get("headSha") != HEAD_SHA
        or len(jobs) != 10
        or aggregate.get("conclusion") != "failure"
        or len(artifacts) != 9
    ):
        raise ValueError("E12b source run identity differs")
    retained = []
    for candidate, expected in ARTIFACTS.items():
        job = jobs.get(expected["job_id"], {})
        artifact = artifacts.get(expected["artifact_id"], {})
        name = artifact_name(candidate)
        if (
            job.get("conclusion") != "success"
            or not str(job.get("name", "")).startswith(candidate)
            or artifact.get("name") != name
            or artifact.get("size_in_bytes") != expected["size_bytes"]
            or artifact.get("digest") != expected["digest"]
            or artifact.get("expired") is not False
            or str(artifact.get("workflow_run", {}).get("id")) != str(RUN_ID)
            or artifact.get("workflow_run", {}).get("head_sha") != HEAD_SHA
        ):
            raise ValueError(f"E12b GitHub identity differs for {candidate}")
        retained.append(
            {
                "candidate": candidate,
                "job_id": str(expected["job_id"]),
                "artifact_id": str(expected["artifact_id"]),
                "artifact_name": name,
                "artifact_size_bytes": expected["size_bytes"],
                "artifact_digest": expected["digest"],
                "artifact_expires_at": artifact["expires_at"],
            }
        )
    return retained


def retain(
    *,
    cells_root: Path,
    contract_path: Path,
    stock_path: Path,
    root: Path,
    run_metadata: Path,
    artifact_metadata: Path,
) -> dict[str, Any]:
    github_artifacts = validate_github(
        load_object(run_metadata), load_object(artifact_metadata)
    )
    contract = load_object(contract_path)
    inventories = []
    for item in contract["candidates"]:
        candidate = item["candidate"]
        evidence = cells_root / artifact_name(candidate)
        summary = load_object(evidence / "summary.json")
        if (
            summary.get("status")
            != "valid_safe_sampled_generated_quant_quality_cell"
            or summary.get("model", {}).get("candidate") != candidate
            or summary.get("contract_sha256") != sha256_file(contract_path)
            or summary.get("request_failures") != 0
        ):
            raise ValueError(f"E12b workflow cell summary differs for {candidate}")
        inventories.append(
            {
                "candidate": candidate,
                **validate_workflow_inventory(evidence, candidate),
            }
        )
    aggregate = build_recovered_aggregate(
        cells_root=cells_root,
        contract_path=contract_path,
        stock_path=stock_path,
        run_id=str(RUN_ID),
    )
    return {
        **aggregate,
        "github": {
            "source_run_id": str(RUN_ID),
            "source_run_attempt": 1,
            "source_run_url": f"https://github.com/Arshgill01/Arm/actions/runs/{RUN_ID}",
            "source_run_conclusion": "failure",
            "repository_commit": HEAD_SHA,
            "aggregate_job_id": str(AGGREGATE_JOB_ID),
            "cell_artifacts": github_artifacts,
        },
        "artifact_recovery": {
            "source_workflow_remains_failed": True,
            "source_failure": (
                "recursive summary discovery selected nine root cell summaries "
                "and nine nested E12a prerequisite summaries, failing the exact-nine assertion"
            ),
            "recursive_summaries_observed": 18,
            "root_cell_summaries_selected": 9,
            "nested_prerequisite_summaries_excluded": 9,
            "cell_summaries_verified_against_workflow_inventories": 9,
            "raw_cell_replay_attempted": False,
            "raw_cell_replay_reason": (
                "relocated artifacts preserve runner-absolute imatrix paths; the "
                "failed source phase was aggregation, not cell validation"
            ),
            "source_python": "3.10.20",
            "native_measurements_added": 0,
            "native_rerun_required": False,
            "source_contract_or_gates_changed": False,
            "cell_inventories": inventories,
        },
        "campaign_decision": {
            "quality_result_can_promote_product": False,
            "product_promotion_made": False,
            "e12b_native_rerun_required": False,
            "terminal_model_decision_requires_e11b_service_evidence": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cells-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--run-metadata", type=Path, required=True)
    parser.add_argument("--artifact-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = retain(
        cells_root=args.cells_root,
        contract_path=args.contract,
        stock_path=args.stock,
        root=args.root,
        run_metadata=args.run_metadata,
        artifact_metadata=args.artifact_metadata,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
