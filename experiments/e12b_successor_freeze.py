#!/usr/bin/env python3
"""Freeze E12b on the validated safe-sampled scorer and resumed imatrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e5b_ingest import load_object, sha256_file
    from experiments.e12b_freeze import enrich_candidates
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import load_object, sha256_file
    from e12b_freeze import enrich_candidates


INPUT_PATHS = {
    "plan": Path("experiments/e12b_plan.json"),
    "adapter_contract": Path("experiments/e10d_contract.json"),
    "cell_runner": Path("experiments/e12b_cell.sh"),
    "ingest": Path("experiments/e12b_successor_ingest.py"),
    "freeze": Path("experiments/e12b_freeze.py"),
    "test": Path("tests/test_e12b_successor.py"),
    "successor_wrapper": Path("experiments/e12b_successor_cell.py"),
    "successor_freeze": Path("experiments/e12b_successor_freeze.py"),
    "safe_contract": Path("experiments/e10f_contract.json"),
    "safe_probe": Path("experiments/e10f_probe.py"),
    "safe_ingest": Path("experiments/e10f_ingest.py"),
    "base_ingest": Path("experiments/e12b_ingest.py"),
    "base_freeze": Path("experiments/e12b_freeze.py"),
    "base_test": Path("tests/test_e12b.py"),
    "safe_manifest": Path("results/manifests/e10f-30829237582.json"),
    "e12a_resume_contract": Path("experiments/e12a_resume_contract.json"),
    "e11a_successor_contract": Path("experiments/e11a_successor_contract.json"),
}


def require_validation(
    value: dict[str, Any], names: tuple[str, ...], label: str
) -> None:
    validation = value.get("validation")
    if not isinstance(validation, dict) or not all(
        validation.get(name) is True for name in names
    ):
        raise ValueError(f"{label} required validation differs")


def build_contract(
    root: Path,
    *,
    e12a_summary_path: Path,
    e12a_imatrix_path: Path,
    e12a_run_id: str,
    e12a_artifact: str,
    e11a_summary_path: Path,
    e11a_run_id: str,
    e11a_artifact: str,
) -> dict[str, Any]:
    plan = load_object(root / INPUT_PATHS["plan"])
    safe_contract = load_object(root / INPUT_PATHS["safe_contract"])
    safe_manifest = load_object(root / INPUT_PATHS["safe_manifest"])
    resume_contract_path = root / INPUT_PATHS["e12a_resume_contract"]
    stock_contract_path = root / INPUT_PATHS["e11a_successor_contract"]
    e12a = load_object(e12a_summary_path)
    e11a = load_object(e11a_summary_path)

    if (
        plan.get("experiment_id") != "E12b-plan"
        or safe_contract.get("experiment_id") != "E10f"
        or safe_manifest.get("status") != "valid_safe_sampled_external_holdout"
        or safe_manifest.get("contract_sha256")
        != sha256_file(root / INPUT_PATHS["safe_contract"])
        or safe_manifest.get("prepared_sha256")
        != safe_contract["workload"]["prepared_sha256"]
    ):
        raise ValueError("E12b safe-sampled prerequisite differs")
    require_validation(
        safe_manifest,
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
        e12a.get("status") != "valid_resumed_application_conditioned_imatrix"
        or e12a.get("contract_sha256") != sha256_file(resume_contract_path)
        or e12a.get("decision", {}).get(
            "resume_success_authorizes_generated_quant_successor"
        )
        is not True
        or not isinstance(imatrix, dict)
        or imatrix.get("sha256") != sha256_file(e12a_imatrix_path)
        or imatrix.get("size_bytes") != e12a_imatrix_path.stat().st_size
        or not e12a_run_id.isdigit()
        or not e12a_artifact
    ):
        raise ValueError("E12b resumed-imatrix prerequisite differs")
    require_validation(
        e12a,
        (
            "native_arm64",
            "exact_source_build_model",
            "exact_checkpoint_identity",
            "deterministic_frozen_corpus",
            "holdouts_excluded",
            "ordered_chunk_24_resume",
            "complete_chunk_count",
            "entry_names_match_checkpoint",
            "gguf_metadata_valid",
            "statistics_retained",
        ),
        "E12a-resume",
    )

    if (
        e11a.get("status") != "valid_safe_sampled_stock_quant_quality_ladder"
        or e11a.get("contract_sha256") != sha256_file(stock_contract_path)
        or e11a.get("prepared_sha256") != safe_manifest.get("prepared_sha256")
        or len(e11a.get("models", [])) != 9
        or not e11a_run_id.isdigit()
        or not e11a_artifact
    ):
        raise ValueError("E12b stock-quant prerequisite differs")
    require_validation(
        e11a,
        (
            "native_arm64",
            "same_frozen_workload",
            "all_candidates_complete",
            "exact_e10f_anchor_reused_without_rerun",
            "zero_request_failures",
            "per_sample_logs_retained",
            "all_raw_responses_retained_once",
        ),
        "E11a-successor",
    )

    from experiments.e12b_successor_cell import render, sha256_bytes

    resolved = render((root / INPUT_PATHS["cell_runner"]).read_text())
    inputs: dict[str, str] = {}
    for name, relative in INPUT_PATHS.items():
        inputs[f"{name}_path"] = relative.as_posix()
        inputs[f"{name}_sha256"] = sha256_file(root / relative)
    metadata = imatrix["metadata"]
    return {
        "schema_version": 1,
        "experiment_id": "E12b",
        "campaign_variant": "safe-sampled-resumed-prerequisite-successor",
        "title": "Safe-sampled application-imatrix generated-quant frontier",
        "state": (
            "frozen after independent validation of the exact E10f scorer, resumed "
            "E12a matrix, and E11a-successor stock ladder, before any generated-model "
            "outcome is observed"
        ),
        "hypothesis": plan["hypothesis"],
        "inputs": inputs,
        "prerequisites": {
            "e10f": {
                "run_id": safe_manifest["github"]["run_id"],
                "run_attempt": safe_manifest["github"]["run_attempt"],
                "artifact": safe_manifest["github"]["artifacts"]["aggregate"]["name"],
                "contract_sha256": safe_manifest["contract_sha256"],
                "summary_sha256": sha256_file(root / INPUT_PATHS["safe_manifest"]),
                "prepared_sha256": safe_manifest["prepared_sha256"],
                "required_status": safe_manifest["status"],
            },
            "e12a": {
                "run_id": e12a_run_id,
                "run_attempt": 1,
                "artifact": e12a_artifact,
                "contract_sha256": e12a["contract_sha256"],
                "summary_sha256": sha256_file(e12a_summary_path),
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
            },
            "failure_rule": (
                "Do not dispatch if an exact referenced run is incomplete, fails, "
                "lacks its artifact, or does not independently validate. Retain a "
                "failure before any separately frozen repair."
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
            "prepared_sha256": safe_manifest["prepared_sha256"],
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
            "original_e10d_rewritten": False,
        },
        "negative_result_rule": plan["decision"]["negative_result_rule"],
        "claim_boundary": (
            "E12b can establish only an exploratory quality-size frontier and matched "
            "imatrix deltas for nine exact b10216-generated recipes using E10f's "
            "validated safe-sampled scorer on native Arm64. It cannot promote a model "
            "before matched native service evidence and sealed confirmation, and it "
            "supports no energy, PMU, local-device, fleet, cost, pruning, causal-kernel, "
            "or other-runtime claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--e12a-summary", type=Path, required=True)
    parser.add_argument("--e12a-imatrix", type=Path, required=True)
    parser.add_argument("--e12a-run-id", required=True)
    parser.add_argument("--e12a-artifact", required=True)
    parser.add_argument("--e11a-summary", type=Path, required=True)
    parser.add_argument("--e11a-run-id", required=True)
    parser.add_argument("--e11a-artifact", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(
        args.root,
        e12a_summary_path=args.e12a_summary,
        e12a_imatrix_path=args.e12a_imatrix,
        e12a_run_id=args.e12a_run_id,
        e12a_artifact=args.e12a_artifact,
        e11a_summary_path=args.e11a_summary,
        e11a_run_id=args.e11a_run_id,
        e11a_artifact=args.e11a_artifact,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
