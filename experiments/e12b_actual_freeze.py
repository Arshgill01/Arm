#!/usr/bin/env python3
"""Freeze E12b from the actual recovered stock ladder and complete imatrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e12b_freeze import enrich_candidates
    from experiments.e12b_actual_cell import render, sha256_bytes
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e12b_freeze import enrich_candidates
    from e12b_actual_cell import render, sha256_bytes


INPUT_PATHS = {
    "plan": Path("experiments/e12b_plan.json"),
    "adapter_contract": Path("experiments/e10d_contract.json"),
    "cell_runner": Path("experiments/e12b_cell.sh"),
    "base_freeze": Path("experiments/e12b_freeze.py"),
    "base_ingest": Path("experiments/e12b_ingest.py"),
    "base_test": Path("tests/test_e12b.py"),
    "successor_wrapper": Path("experiments/e12b_successor_cell.py"),
    "successor_freeze": Path("experiments/e12b_successor_freeze.py"),
    "successor_ingest": Path("experiments/e12b_successor_ingest.py"),
    "successor_test": Path("tests/test_e12b_successor.py"),
    "actual_wrapper": Path("experiments/e12b_actual_cell.py"),
    "actual_freeze": Path("experiments/e12b_actual_freeze.py"),
    "actual_ingest": Path("experiments/e12b_actual_ingest.py"),
    "actual_test": Path("tests/test_e12b_actual.py"),
    "safe_contract": Path("experiments/e10f_contract.json"),
    "safe_probe": Path("experiments/e10f_probe.py"),
    "safe_ingest": Path("experiments/e10f_ingest.py"),
    "safe_manifest": Path("results/manifests/e10f-30829237582.json"),
    "e12a_metadata_contract": Path(
        "experiments/e12a_metadata_recovery_contract.json"
    ),
    "e12a_metadata_manifest": Path(
        "results/manifests/e12a-metadata-recovery-30855550027.json"
    ),
    "e12a_workflow_summary": Path(
        "results/manifests/e12a-metadata-recovery-workflow-30855550027.json"
    ),
    "e12a_resume_contract": Path("experiments/e12a_resume_contract.json"),
    "e11a_successor_contract": Path("experiments/e11a_successor_contract.json"),
}


def require_true(value: dict[str, Any], names: tuple[str, ...], label: str) -> None:
    validation = value.get("validation")
    if not isinstance(validation, dict) or not all(
        validation.get(name) is True for name in names
    ):
        raise ValueError(f"{label} required validation differs")


def build_contract(
    root: Path,
    *,
    e11a_contract_path: Path,
    e11a_summary_path: Path,
    e11a_run_id: str,
    e11a_artifact: str,
) -> dict[str, Any]:
    plan = load_object(root / INPUT_PATHS["plan"])
    safe_contract = load_object(root / INPUT_PATHS["safe_contract"])
    safe = load_object(root / INPUT_PATHS["safe_manifest"])
    e12a_contract_path = root / INPUT_PATHS["e12a_metadata_contract"]
    e12a_retained = load_object(root / INPUT_PATHS["e12a_metadata_manifest"])
    e12a_summary_path = root / INPUT_PATHS["e12a_workflow_summary"]
    e12a = load_object(e12a_summary_path)
    e11a_contract = load_object(e11a_contract_path)
    e11a = load_object(e11a_summary_path)
    if (
        plan.get("experiment_id") != "E12b-plan"
        or safe_contract.get("experiment_id") != "E10f"
        or safe.get("status") != "valid_safe_sampled_external_holdout"
        or safe.get("contract_sha256")
        != sha256_file(root / INPUT_PATHS["safe_contract"])
        or safe.get("prepared_sha256") != safe_contract["workload"]["prepared_sha256"]
    ):
        raise ValueError("E12b actual safe-scoring prerequisite differs")
    require_true(
        safe,
        (
            "native_arm64",
            "same_frozen_workload",
            "both_models_complete",
            "zero_request_failures",
            "per_sample_logs_retained",
            "all_raw_responses_retained_once",
        ),
        "E10f",
    )

    imatrix = e12a.get("imatrix")
    if (
        e12a.get("status")
        != "valid_application_conditioned_imatrix_metadata_recovery"
        or e12a.get("contract_sha256") != sha256_file(e12a_contract_path)
        or e12a.get("decision", {}).get(
            "metadata_success_authorizes_generated_quant_successor"
        )
        is not True
        or not isinstance(imatrix, dict)
        or imatrix.get("sha256")
        != e12a_retained.get("imatrix", {}).get("sha256")
        or imatrix.get("size_bytes")
        != e12a_retained.get("imatrix", {}).get("size_bytes")
        or e12a_retained.get("status") != e12a.get("status")
        or e12a_retained.get("contract_sha256") != e12a.get("contract_sha256")
        or e12a_retained.get("imatrix") != imatrix
        or e12a_retained.get("github", {}).get("run_id") != "30855550027"
        or e12a_retained.get("github", {}).get("artifact_name")
        != "e12a-metadata-recovery-30855550027-1"
    ):
        raise ValueError("E12b actual imatrix prerequisite differs")
    require_true(
        e12a,
        (
            "native_arm64",
            "exact_retained_statistics",
            "exact_source_artifact_inventory",
            "matrix_bytes_unchanged",
            "ordered_dataset_metadata",
            "complete_chunk_count",
            "entry_names_match_checkpoint",
            "gguf_metadata_valid",
            "generated_quant_dispatch_allowed",
        ),
        "E12a metadata recovery",
    )
    # These three recovery flags are required to be false, not true.
    for name in ("matrix_recomputed", "native_tool_rebuilt", "model_downloaded"):
        if e12a["validation"].get(name) is not False:
            raise ValueError(f"E12a recovery boundary differs for {name}")

    if (
        e11a_contract.get("experiment_id")
        != "E11a-successor-actual-recovery"
        or e11a.get("status")
        != "valid_stock_quant_ladder_with_two_resource_infeasible_points"
        or e11a.get("contract_sha256") != sha256_file(e11a_contract_path)
        or e11a.get("prepared_sha256") != safe.get("prepared_sha256")
        or not e11a_run_id.isdigit()
        or not e11a_artifact
    ):
        raise ValueError("E12b actual stock prerequisite differs")
    require_true(
        e11a,
        (
            "native_arm64",
            "same_frozen_workload",
            "all_valid_source_cells_complete",
            "two_complete_scoring_resource_failures_retained",
            "resource_failures_excluded_from_deployable_frontier",
            "exact_e10f_anchor_reused_without_rerun",
            "zero_scoring_request_failures",
            "per_sample_logs_retained_in_source_artifacts",
        ),
        "E11a actual recovery",
    )
    if (
        len(e11a.get("deployable_models", [])) != 7
        or len(e11a.get("resource_infeasible_models", [])) != 2
        or e11a.get("accounting", {}).get("all_attempted_candidates_accounted_for")
        is not True
    ):
        raise ValueError("E12b actual stock accounting differs")

    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    for name, path in (
        ("e11a_recovery_contract", e11a_contract_path),
        ("e11a_recovery_summary", e11a_summary_path),
    ):
        try:
            relative = path.relative_to(root)
        except ValueError as error:
            raise ValueError(f"E12b {name} must be retained in the repository") from error
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(path)

    resolved = render((root / INPUT_PATHS["cell_runner"]).read_text())
    metadata = imatrix["metadata"]
    return {
        "schema_version": 1,
        "experiment_id": "E12b",
        "campaign_variant": "actual-recovered-prerequisites",
        "title": "Application-imatrix generated-quant frontier",
        "state": (
            "frozen after independent validation of the exact E10f scorer, complete "
            "E12a matrix recovery, and terminal E11a stock accounting, before any "
            "generated-model outcome was observed"
        ),
        "hypothesis": plan["hypothesis"],
        "inputs": inputs,
        "prerequisites": {
            "e10f": {
                "run_id": safe["github"]["run_id"],
                "run_attempt": safe["github"]["run_attempt"],
                "artifact": safe["github"]["artifacts"]["aggregate"]["name"],
                "contract_sha256": safe["contract_sha256"],
                "summary_sha256": sha256_file(root / INPUT_PATHS["safe_manifest"]),
                "prepared_sha256": safe["prepared_sha256"],
                "required_status": safe["status"],
            },
            "e12a": {
                "run_id": "30855550027",
                "run_attempt": 1,
                "artifact": "e12a-metadata-recovery-30855550027-1",
                "artifact_id": e12a_retained["github"]["artifact_id"],
                "artifact_digest": e12a_retained["github"]["artifact_digest"],
                "contract_sha256": e12a["contract_sha256"],
                "summary_sha256": sha256_file(e12a_summary_path),
                "imatrix_artifact_relative_path": (
                    "source-artifact/completed/imatrix.gguf"
                ),
                "imatrix_sha256": imatrix["sha256"],
                "imatrix_size_bytes": imatrix["size_bytes"],
                "imatrix_entries": metadata["entries"],
                "imatrix_chunks": metadata["chunk_count"],
                "required_status": e12a["status"],
            },
            "e11a": {
                "run_id": e11a_run_id,
                "run_attempt": 1,
                "artifact": e11a_artifact,
                "contract_sha256": e11a["contract_sha256"],
                "summary_sha256": sha256_file(e11a_summary_path),
                "required_status": e11a["status"],
                "deployable_models": len(e11a["deployable_models"]),
                "resource_infeasible_models": len(
                    e11a["resource_infeasible_models"]
                ),
            },
            "failure_rule": (
                "Do not dispatch if any exact referenced artifact, matrix, source "
                "summary, or retained manifest is absent or fails validation."
            ),
        },
        "source_model": plan["source_model"],
        "quantizer": plan["quantizer"],
        "candidates": enrich_candidates(plan),
        "matched_pairs": plan["matched_pairs"],
        "quality": {
            **plan["quality"],
            "adapter": (
                "Exact validated E10f serial safe-sampled probability scorer; the "
                "forced token is never used for score or prefix construction."
            ),
            "prepared_sha256": safe["prepared_sha256"],
        },
        "scoring": safe_contract["scoring"],
        "safe_sampling": safe_contract["safe_sampling"],
        "workload": safe_contract["workload"],
        "frontier": plan["frontier"],
        "acceptance": {
            **safe_contract["acceptance"],
            "quantize_exit_status": plan["acceptance"]["quantize_exit_status"],
            "required_imatrix_metadata_on_imatrix_candidates": True,
            "forbidden_imatrix_metadata_on_controls": True,
            "required_tensor_override_log_on_mixed_candidates": True,
            "raw_responses_per_model": safe_contract["workload"]["expected_summary"][
                "token_score_requests"
            ],
        },
        "execution": {
            "runner": "ubuntu-24.04-arm",
            "cell_timeout_minutes": 360,
            "aggregate_timeout_minutes": 30,
            "fresh_build_and_process_per_model": True,
            "resolved_cell_runner_sha256": sha256_bytes(resolved.encode()),
            "all_nine_candidates_required": True,
            "same_bf16_source_and_quantizer": True,
            "exact_safe_sampled_workload": True,
        },
        "decision": {
            **plan["decision"],
            "quality_result_can_promote_product": False,
            "matched_native_service_required": True,
            "e11c_sealed_confirmation_required": True,
            "failed_prerequisite_runs_rehabilitated": False,
        },
        "negative_result_rule": plan["decision"]["negative_result_rule"],
        "claim_boundary": (
            "E12b can establish only an exploratory quality-size frontier and "
            "matched imatrix deltas for nine exact b10216-generated recipes using "
            "E10f's scorer on native Arm64. It cannot promote a model before matched "
            "native service evidence and sealed confirmation, and supports no energy, "
            "PMU, local-device, fleet, cost, pruning, causal-kernel, or other-runtime claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--e11a-contract", type=Path, required=True)
    parser.add_argument("--e11a-summary", type=Path, required=True)
    parser.add_argument("--e11a-run-id", required=True)
    parser.add_argument("--e11a-artifact", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    contract = build_contract(
        root,
        e11a_contract_path=(root / args.e11a_contract).resolve(),
        e11a_summary_path=(root / args.e11a_summary).resolve(),
        e11a_run_id=args.e11a_run_id,
        e11a_artifact=args.e11a_artifact,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
