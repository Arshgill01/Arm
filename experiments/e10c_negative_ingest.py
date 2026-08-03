#!/usr/bin/env python3
"""Validate and summarize a complete E10c run that failed promotion gates."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from experiments import e10c_ingest as e10c
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    import e10c_ingest as e10c


def validate_observed_calibration(
    cell_dir: Path, calibration: dict[str, Any], contract: dict[str, Any]
) -> None:
    expected = contract["workload"]["multi_token_calibration_candidates"]
    serial = calibration.get("serial_sum_logprobs")
    forked = calibration.get("forked_sum_logprobs")
    token_delta = calibration.get("maximum_absolute_token_logprob_delta")
    sum_delta = calibration.get("maximum_absolute_sum_logprob_delta")
    if (
        calibration.get("error") is not None
        or calibration.get("candidate_tokens") != expected
        or not isinstance(serial, list)
        or len(serial) != len(expected)
        or not isinstance(forked, list)
        or len(forked) != len(expected)
        or not isinstance(token_delta, (int, float))
        or not math.isfinite(token_delta)
        or token_delta < 0
        or not isinstance(sum_delta, (int, float))
        or not math.isfinite(sum_delta)
        or sum_delta < 0
    ):
        raise ValueError(f"{cell_dir.name} calibration evidence is malformed")
    serial_raw = calibration.get("serial_raw_responses")
    forked_raw = calibration.get("forked_raw_responses")
    if (
        not isinstance(serial_raw, list)
        or len(serial_raw) != sum(len(candidate) for candidate in expected)
        or not isinstance(forked_raw, list)
        or len(forked_raw) != 1
    ):
        raise ValueError(f"{cell_dir.name} calibration raw response count differs")
    for record in serial_raw + forked_raw:
        e10c.validate_raw(cell_dir, record)


def predictions_equal(cells: list[dict[str, Any]]) -> bool:
    predictions = [[case["prediction"] for case in cell["cases"]] for cell in cells]
    return all(current == predictions[0] for current in predictions[1:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = e10c.validate_inputs(args.evidence_dir, args.contract, args.root)
    build = e10c.validate_source_and_build(args.evidence_dir, contract)
    tasks_manifest = e10c.load_object(args.evidence_dir / "tasks-manifest.json")
    tasks = tasks_manifest.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != contract["workload"]["task_count"]:
        raise ValueError("E10c task manifest differs")

    original_calibration_validator = e10c.validate_calibration
    e10c.validate_calibration = validate_observed_calibration
    try:
        cells = []
        for index, point in enumerate(contract["execution"]["cell_order"], start=1):
            cell_dir = (
                args.evidence_dir
                / "cells"
                / f"{index:02d}-{point['mode']}-r{point['repetition']}"
            )
            cells.append(
                e10c.validate_cell(
                    cell_dir,
                    contract=contract,
                    tasks=tasks,
                    mode=point["mode"],
                    repetition=point["repetition"],
                )
            )
    finally:
        e10c.validate_calibration = original_calibration_validator

    combined = e10c.aggregate(cells, contract)
    exact_predictions_equal = predictions_equal(cells)
    combined["parity"]["all_predictions_equal"] = exact_predictions_equal
    acceptance = contract["acceptance"]
    gates = {
        "request_failures": all(cell["result"]["failures"] == 0 for cell in cells),
        "single_token_parity": combined["parity"][
            "maximum_absolute_single_token_logprob_delta"
        ]
        <= acceptance["maximum_single_token_logprob_delta"],
        "multi_token_sum_parity": combined["maximum_multi_token_sum_logprob_delta"]
        <= acceptance["maximum_multi_token_sum_logprob_delta"],
        "multi_token_token_parity": combined["maximum_token_logprob_delta"]
        <= acceptance["maximum_token_logprob_delta"],
        "prediction_parity": exact_predictions_equal,
        "prompt_identity": combined["parity"]["all_prompt_hashes_equal"],
        "latency": combined["ratios"]["median_http_latency"]
        <= acceptance["maximum_forked_to_serial_median_http_latency_ratio"],
        "cpu": combined["ratios"]["median_cpu_seconds_per_task"]
        <= acceptance["maximum_forked_to_serial_median_cpu_ratio"],
        "prompt_evaluations": combined["ratios"]["prompt_evaluations"]
        == acceptance["expected_forked_to_serial_prompt_evaluations_ratio"],
        "rss": combined["ratios"]["maximum_rss"]
        <= acceptance["maximum_forked_to_serial_rss_ratio"],
    }
    lscpu = e10c.parse_lscpu((args.evidence_dir / "lscpu.txt").read_text())
    provenance = e10c.load_object(args.evidence_dir / "provenance.json")
    if (
        lscpu.get("architecture") != "aarch64"
        or provenance.get("experiment_id") != "E10c"
    ):
        raise ValueError("E10c platform or provenance differs")
    failed_gates = sorted(name for name, passed in gates.items() if not passed)
    if not failed_gates:
        raise ValueError(
            "negative ingest was used for an E10c run with no failed gates"
        )

    summary = {
        "schema_version": 1,
        "experiment_id": "E10c",
        "status": "fail",
        "promote_candidate_scorer": False,
        "failed_gates": failed_gates,
        "validation": gates,
        "platform": {
            "lscpu": lscpu,
            "environment": e10c.load_object(args.evidence_dir / "environment.json"),
        },
        "source_and_build": build,
        "aggregate": combined,
        "cells": cells,
        "provenance": provenance,
        "decision": contract["decision"]["next_step_on_failure"],
        "claim_boundary": contract["claim_boundary"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": summary["status"],
                "failed_gates": failed_gates,
                "validation": gates,
                "aggregate": combined,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
