#!/usr/bin/env python3
"""Mechanically freeze E12b after its exact prerequisite runs validate."""

from __future__ import annotations

import argparse
import copy
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
    "plan": Path("experiments/e12b_plan.json"),
    "adapter_contract": Path("experiments/e10d_contract.json"),
    "cell_runner": Path("experiments/e12b_cell.sh"),
    "ingest": Path("experiments/e12b_ingest.py"),
    "freeze": Path("experiments/e12b_freeze.py"),
    "test": Path("tests/test_e12b.py"),
}


OVERRIDE_VALIDATION = {
    "e12b_q3_k_m_output_embed_q6": {
        "minimum_manual_override_lines": 0,
        "exact_tensor_types": {"token_embd.weight": "Q6_K"},
        "tensor_type_patterns": [],
        "structural_note": "The exact tied-embedding BF16 source has token_embd.weight and no output.weight tensor. The frozen output flag is retained, but only the token embedding can change this file.",
    },
    "e12b_iq4_xs_v_down_q5": {
        "minimum_manual_override_lines": 52,
        "exact_tensor_types": {},
        "tensor_type_patterns": [
            {
                "pattern": r"^blk\.\d+\.attn_v\.weight$",
                "expected_tensors": 26,
                "type": "Q5_K",
            },
            {
                "pattern": r"^blk\.\d+\.ffn_down\.weight$",
                "expected_tensors": 26,
                "type": "Q5_K",
            },
        ],
    },
    "e12b_q4_k_s_edge_layers_q6": {
        "minimum_manual_override_lines": 28,
        "exact_tensor_types": {},
        "tensor_type_patterns": [
            {
                "pattern": r"^blk\.(0|1|24|25)\.(attn_q|attn_k|attn_v|attn_output|ffn_gate|ffn_up|ffn_down)\.weight$",
                "expected_tensors": 28,
                "type": "Q6_K",
            }
        ],
    },
}


def required_true(value: dict[str, Any], names: tuple[str, ...], label: str) -> None:
    validation = value.get("validation")
    if not isinstance(validation, dict) or not all(
        validation.get(name) is True for name in names
    ):
        raise ValueError(f"{label} required validation differs")


def enrich_candidates(plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = copy.deepcopy(plan["candidates"])
    names = {item["candidate"] for item in candidates}
    if set(OVERRIDE_VALIDATION) - names:
        raise ValueError("E12b override validation references an unknown candidate")
    for candidate in candidates:
        name = candidate["candidate"]
        if name in OVERRIDE_VALIDATION:
            if candidate["role"] != "predefined mixed-tensor candidate":
                raise ValueError("E12b override validation role differs")
            candidate["override_validation"] = OVERRIDE_VALIDATION[name]
    return candidates


def build_contract(
    *,
    e10d_summary_path: Path,
    e12a_summary_path: Path,
    e12a_imatrix_path: Path,
    e11a_summary_path: Path,
    e11a_run_id: str,
) -> dict[str, Any]:
    plan = load_object(INPUT_PATHS["plan"])
    e10d = load_object(e10d_summary_path)
    e12a = load_object(e12a_summary_path)
    e11a = load_object(e11a_summary_path)
    if (
        e10d.get("status") != "valid_external_holdout"
        or e10d.get("contract_sha256")
        != plan["prerequisites"]["e10d"]["contract_sha256"]
        or e10d.get("prepared_sha256") != e11a.get("prepared_sha256")
    ):
        raise ValueError("E12b exact E10d prerequisite differs")
    required_true(
        e10d,
        (
            "native_arm64",
            "same_frozen_workload",
            "both_models_complete",
            "zero_request_failures",
            "per_sample_logs_retained",
        ),
        "E10d",
    )
    if len(e10d.get("models", [])) != 2 or not all(
        model.get("validation", {}).get("all_raw_responses_retained") is True
        for model in e10d["models"]
    ):
        raise ValueError("E10d raw response validation differs")
    e12a_plan = plan["prerequisites"]["e12a"]
    imatrix = e12a.get("imatrix")
    if (
        e12a.get("status") != e12a_plan["required_status"]
        or e12a.get("contract_sha256") != e12a_plan["contract_sha256"]
        or not isinstance(imatrix, dict)
        or imatrix.get("sha256") != sha256_file(e12a_imatrix_path)
        or imatrix.get("size_bytes") != e12a_imatrix_path.stat().st_size
    ):
        raise ValueError("E12b exact E12a prerequisite differs")
    required_true(
        e12a,
        (
            "native_arm64",
            "exact_source_build_model",
            "deterministic_frozen_corpus",
            "holdouts_excluded",
            "complete_chunk_count",
            "gguf_metadata_valid",
            "statistics_retained",
        ),
        "E12a",
    )
    e11a_contract_path = Path("experiments/e11a_contract.json")
    if (
        e11a.get("status") != "valid_stock_quant_quality_ladder"
        or e11a.get("contract_sha256") != sha256_file(e11a_contract_path)
        or e11a.get("prepared_sha256") != e10d.get("prepared_sha256")
        or len(e11a.get("models", [])) != 9
        or not e11a_run_id.isdigit()
    ):
        raise ValueError("E12b exact E11a prerequisite differs")
    required_true(
        e11a,
        (
            "native_arm64",
            "same_frozen_workload",
            "all_candidates_complete",
            "e10d_anchor_reused_without_rerun",
            "zero_request_failures",
            "per_sample_logs_retained",
        ),
        "E11a",
    )

    inputs: dict[str, str] = {}
    for name, path in INPUT_PATHS.items():
        inputs[f"{name}_path"] = str(path)
        inputs[f"{name}_sha256"] = sha256_file(path)
    e12a_metadata = imatrix["metadata"]
    return {
        "schema_version": 1,
        "experiment_id": "E12b",
        "title": plan["title"],
        "state": "frozen after independent validation of the exact E10d, E12a, and E11a prerequisites and before any E12b generated-model result is observed",
        "hypothesis": plan["hypothesis"],
        "inputs": inputs,
        "prerequisites": {
            "e10d": {
                **plan["prerequisites"]["e10d"],
                "summary_sha256": sha256_file(e10d_summary_path),
                "prepared_sha256": e10d["prepared_sha256"],
            },
            "e12a": {
                **e12a_plan,
                "summary_sha256": sha256_file(e12a_summary_path),
                "imatrix_sha256": imatrix["sha256"],
                "imatrix_size_bytes": imatrix["size_bytes"],
                "imatrix_entries": e12a_metadata["entries"],
                "imatrix_chunks": e12a_metadata["chunk_count"],
            },
            "e11a": {
                "run_id": e11a_run_id,
                "run_attempt": 1,
                "artifact": f"e11a-aggregate-{e11a_run_id}-1",
                "contract_sha256": e11a["contract_sha256"],
                "summary_sha256": sha256_file(e11a_summary_path),
                "required_status": "valid_stock_quant_quality_ladder",
            },
            "failure_rule": "Do not dispatch if any exact referenced run is incomplete, fails, lacks its artifact, or does not independently validate. Never silently substitute a rerun.",
        },
        "source_model": plan["source_model"],
        "quantizer": plan["quantizer"],
        "candidates": enrich_candidates(plan),
        "matched_pairs": plan["matched_pairs"],
        "quality": plan["quality"],
        "frontier": plan["frontier"],
        "acceptance": {
            **plan["acceptance"],
            "accepted_server_shell_exit_statuses": [0, 130],
        },
        "decision": plan["decision"],
        "negative_result_rule": plan["decision"]["negative_result_rule"],
        "claim_boundary": plan["claim_boundary"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e10d-summary", type=Path, required=True)
    parser.add_argument("--e12a-summary", type=Path, required=True)
    parser.add_argument("--e12a-imatrix", type=Path, required=True)
    parser.add_argument("--e11a-summary", type=Path, required=True)
    parser.add_argument("--e11a-run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = build_contract(
        e10d_summary_path=args.e10d_summary,
        e12a_summary_path=args.e12a_summary,
        e12a_imatrix_path=args.e12a_imatrix,
        e11a_summary_path=args.e11a_summary,
        e11a_run_id=args.e11a_run_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"sha256": sha256_file(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
