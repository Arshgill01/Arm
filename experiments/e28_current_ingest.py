#!/usr/bin/env python3
"""Validate the E28 current-upstream stock-versus-combined campaign."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from e28_ingest import (
    NMSE_PATTERN,
    PPL_PATTERN,
    bootstrap_ratio,
    extract_answer,
    load_object,
    median_summary,
    parse_time,
)


VARIANTS = ("stock", "combined")


def inference_summary(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    confidence = contract["performance"]["confidence_interval"]
    for case_id in contract["current_upstream"]["matched_cases"]:
        result[case_id] = {}
        values_by_variant: dict[str, list[float]] = {}
        for variant in VARIANTS:
            values = []
            rss = []
            internal = []
            for path in sorted((root / "inference" / case_id).glob(f"*-{variant}.jsonl")):
                rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                if len(rows) != 1 or len(rows[0].get("samples_ts", [])) != 3:
                    raise ValueError(f"invalid current-upstream sample: {path}")
                values.append(float(rows[0]["avg_ts"]))
                internal.extend(float(value) for value in rows[0]["samples_ts"])
                rss.append(float(parse_time(path.with_suffix(".time"))["maximum_rss_kib"]))
            summary = median_summary(values, "tokens_per_second")
            summary["internal_samples_tokens_per_second"] = internal
            summary["maximum_rss_kib"] = median_summary(rss, "rss_kib")
            result[case_id][variant] = summary
            values_by_variant[variant] = values
        result[case_id]["combined_over_stock"] = {
            "ratio": result[case_id]["combined"]["median_tokens_per_second"]
            / result[case_id]["stock"]["median_tokens_per_second"],
            "confidence_interval": bootstrap_ratio(
                values_by_variant["combined"],
                values_by_variant["stock"],
                seed=int(confidence["seed"]),
                resamples=int(confidence["resamples"]),
            ),
        }
    return result


def quality_summary(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    tasks = load_object(root / contract["quality"]["tasks_path"])["tasks"]
    answers = {task["id"]: task["answer"] for task in tasks}
    result: dict[str, Any] = {}
    for variant in VARIANTS:
        repetitions = []
        for repetition in (1, 2):
            cell = root / "quality" / variant / f"repeat-{repetition}"
            raw = load_object(cell / "quality.json")
            predictions = {
                case["id"]: extract_answer(case["response"]) for case in raw["cases"]
            }
            if predictions.keys() != answers.keys():
                raise ValueError(f"incomplete quality repetition: {cell}")
            repetitions.append(
                {
                    "score": sum(predictions[key] == answers[key] for key in answers),
                    "total": len(answers),
                    "predictions": predictions,
                    "readiness_ms": float(load_object(cell / "readiness.json")["ready_ms"]),
                    "maximum_rss_kib": parse_time(cell / "server.time")["maximum_rss_kib"],
                }
            )
        result[variant] = {
            "repetitions": repetitions,
            "predictions_stable": repetitions[0]["predictions"] == repetitions[1]["predictions"],
            "minimum_score": min(item["score"] for item in repetitions),
            "median_readiness_ms": statistics.median(item["readiness_ms"] for item in repetitions),
            "median_maximum_rss_kib": statistics.median(item["maximum_rss_kib"] for item in repetitions),
        }
    return result


def perplexity_summary(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for variant in VARIANTS:
        values = []
        for repetition in (1, 2):
            text = "\n".join(
                (root / "perplexity" / f"{variant}-{repetition}.{suffix}").read_text(
                    encoding="utf-8", errors="replace"
                )
                for suffix in ("stdout", "stderr")
            )
            matches = PPL_PATTERN.findall(text)
            if not matches:
                raise ValueError(f"missing perplexity for {variant} repetition {repetition}")
            values.append(float(matches[-1]))
        result[variant] = {"samples": values, "median": statistics.median(values)}
    result["combined_over_stock"] = result["combined"]["median"] / result["stock"]["median"]
    result["maximum_relative_increase"] = contract["quality"]["maximum_relative_increase"]
    return result


def correctness_summary(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    flash = []
    for path in sorted((root / "correctness").glob("flash-*.jsonl")):
        flash.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    direct_nmse = []
    for path in sorted((root / "correctness").glob("*.txt")):
        direct_nmse.extend(float(value) for value in NMSE_PATTERN.findall(path.read_text()))
    if len(flash) != 9 or not direct_nmse:
        raise ValueError("current-upstream correctness evidence is incomplete")
    return {
        "flash_case_count": len(flash),
        "maximum_flash_nmse": max(float(row["nmse"]) for row in flash),
        "maximum_direct_nmse": max(direct_nmse),
        "flash_passed": all(row.get("pass") is True for row in flash),
        "dispatch": {
            "e24_q6": "E28_DISPATCH e24" in (root / "dispatch/e24.txt").read_text(),
            "e25_q4_decoded": "E28_DISPATCH e25" in (root / "dispatch/e25.txt").read_text(),
            "e27_neon_fmla": (root / "dispatch/e27-neon-fmla.txt").stat().st_size > 0,
        },
    }


def build_summary(root: Path) -> dict[str, Any]:
    contract = load_object(root / "contract.json")
    correctness = correctness_summary(root, contract)
    quality = quality_summary(root, contract)
    perplexity = perplexity_summary(root, contract)
    inference = inference_summary(root, contract)
    sidecar = load_object(root / "source/e25-decoded-sidecar-bytes.json")
    if sidecar.get("decoded_sidecar_bytes", 0) <= 0:
        raise ValueError("decoded Q4_K sidecar byte evidence is missing")
    gates = {
        "direct_correctness": correctness["flash_passed"]
        and correctness["maximum_flash_nmse"] <= contract["correctness"]["maximum_flash_attention_nmse"]
        and correctness["maximum_direct_nmse"] <= 0.0005,
        "all_dispatch_paths": all(correctness["dispatch"].values()),
        "quality_stable": all(quality[v]["predictions_stable"] for v in VARIANTS),
        "quality_no_loss": quality["combined"]["minimum_score"] >= quality["stock"]["minimum_score"],
        "perplexity": perplexity["combined_over_stock"]
        <= 1 + perplexity["maximum_relative_increase"],
        "profile_evidence": all(
            (root / "profile" / case / "perf-report-symbol.txt").stat().st_size > 0
            for case in contract["current_upstream"]["profile_cases"]
        ),
    }
    gates["accepted"] = all(gates.values())
    return {
        "schema_version": 1,
        "experiment_id": "E28-current-upstream",
        "correctness": correctness,
        "quality": quality,
        "perplexity": perplexity,
        "decoded_sidecar": sidecar,
        "inference": inference,
        "gates": gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    summary = build_summary(args.evidence_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary["gates"], sort_keys=True))
    return 0 if summary["gates"]["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
