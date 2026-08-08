#!/usr/bin/env python3
"""Validate and summarize the E28 pinned A/B/C/D campaign."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
from pathlib import Path
from typing import Any


PPL_PATTERN = re.compile(r"(?:Final estimate:\s*)?PPL\s*=\s*([0-9]+(?:\.[0-9]+)?)")
NMSE_PATTERN = re.compile(r"nmse(?:8|4|_decoded)?=([0-9.eE+-]+)")
RSS_PATTERN = re.compile(r"Maximum resident set size \(kbytes\):\s*([0-9]+)")
ANSWER_PATTERN = re.compile(r"(?<![A-Z])([A-D])(?![A-Z])")
VARIANTS = ("A", "B", "C", "D")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def median_summary(values: list[float], unit: str) -> dict[str, Any]:
    if len(values) != 6 or any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError(f"expected six positive {unit} samples, got {values}")
    return {
        "samples": values,
        "count": len(values),
        f"median_{unit}": statistics.median(values),
        f"mean_{unit}": statistics.mean(values),
        "population_cv": statistics.pstdev(values) / statistics.mean(values),
        f"minimum_{unit}": min(values),
        f"maximum_{unit}": max(values),
    }


def bootstrap_ratio(
    numerator: list[float], denominator: list[float], *, seed: int, resamples: int
) -> dict[str, float | int]:
    if len(numerator) != 6 or len(denominator) != 6 or resamples <= 0:
        raise ValueError("bootstrap inputs must contain six samples and positive resamples")
    rng = random.Random(seed)
    ratios = []
    for _ in range(resamples):
        top = [rng.choice(numerator) for _ in numerator]
        bottom = [rng.choice(denominator) for _ in denominator]
        ratios.append(statistics.median(top) / statistics.median(bottom))
    ratios.sort()
    lower = ratios[math.floor(0.025 * (len(ratios) - 1))]
    upper = ratios[math.ceil(0.975 * (len(ratios) - 1))]
    return {"confidence": 0.95, "resamples": resamples, "lower": lower, "upper": upper}


def parse_time(path: Path) -> dict[str, int]:
    match = RSS_PATTERN.search(path.read_text(encoding="utf-8", errors="replace"))
    if not match:
        raise ValueError(f"{path} lacks maximum RSS")
    return {"maximum_rss_kib": int(match.group(1))}


def inference_summary(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    seed = int(contract["performance"]["confidence_interval"]["seed"])
    resamples = int(contract["performance"]["confidence_interval"]["resamples"])
    for case in contract["performance"]["whole_model_cases"]:
        case_id = case["id"]
        result[case_id] = {}
        raw_values: dict[str, list[float]] = {}
        for variant in VARIANTS:
            paths = sorted((root / "inference" / case_id).glob(f"*-{variant}.jsonl"))
            values = []
            internal = []
            rss = []
            for path in paths:
                rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                if len(rows) != 1 or len(rows[0].get("samples_ts", [])) != 1:
                    raise ValueError(f"invalid llama-bench sample: {path}")
                values.append(float(rows[0]["avg_ts"]))
                internal.extend(float(value) for value in rows[0]["samples_ts"])
                rss.append(parse_time(path.with_suffix(".time"))["maximum_rss_kib"])
            summary = median_summary(values, "tokens_per_second")
            summary["internal_samples_tokens_per_second"] = internal
            summary["maximum_rss_kib"] = median_summary(
                [float(value) for value in rss], "rss_kib"
            )
            result[case_id][variant] = summary
            raw_values[variant] = values
        for numerator, denominator in (("B", "A"), ("C", "A"), ("D", "B"), ("D", "C"), ("D", "A")):
            key = f"{numerator}_over_{denominator}"
            ratio = (
                result[case_id][numerator]["median_tokens_per_second"]
                / result[case_id][denominator]["median_tokens_per_second"]
            )
            result[case_id][key] = {
                "ratio": ratio,
                "confidence_interval": bootstrap_ratio(
                    raw_values[numerator], raw_values[denominator], seed=seed, resamples=resamples
                ),
            }
    return result


def extract_answer(text: str) -> str | None:
    match = ANSWER_PATTERN.search(text.upper())
    return match.group(1) if match else None


def quality_summary(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    tasks = load_object(root / contract["quality"]["tasks_path"])["tasks"]
    answers = {task["id"]: task["answer"] for task in tasks}
    result: dict[str, Any] = {}
    for variant in VARIANTS:
        repetitions = []
        for repetition in (1, 2):
            cell = root / "quality" / variant / f"repeat-{repetition}"
            raw = load_object(cell / "quality.json")
            if len(raw.get("cases", [])) != len(answers):
                raise ValueError(f"incomplete quality run: {cell}")
            predictions = {
                case["id"]: extract_answer(case["response"]) for case in raw["cases"]
            }
            score = sum(predictions[task_id] == answer for task_id, answer in answers.items())
            readiness = float(load_object(cell / "readiness.json")["ready_ms"])
            rss = parse_time(cell / "server.time")["maximum_rss_kib"]
            repetitions.append(
                {"score": score, "total": len(answers), "predictions": predictions,
                 "readiness_ms": readiness, "maximum_rss_kib": rss}
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
                raise ValueError(f"missing perplexity result for {variant} repetition {repetition}")
            values.append(float(matches[-1]))
        result[variant] = {"samples": values, "median": statistics.median(values)}
    result["B_over_A"] = result["B"]["median"] / result["A"]["median"]
    result["D_over_C"] = result["D"]["median"] / result["C"]["median"]
    result["maximum_relative_increase"] = contract["quality"]["maximum_relative_increase"]
    return result


def correctness_summary(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    flash_rows = []
    for path in sorted((root / "correctness").glob("flash-*.jsonl")):
        flash_rows.extend(json.loads(line) for line in path.read_text().splitlines() if line.strip())
    direct_nmse = []
    for path in sorted((root / "correctness").glob("*.txt")):
        direct_nmse.extend(float(value) for value in NMSE_PATTERN.findall(path.read_text()))
    if len(flash_rows) != 9 or not direct_nmse:
        raise ValueError("correctness evidence is incomplete")
    maximum_flash = max(float(row["nmse"]) for row in flash_rows)
    return {
        "flash_case_count": len(flash_rows),
        "maximum_flash_nmse": maximum_flash,
        "maximum_direct_nmse": max(direct_nmse),
        "flash_passed": all(row.get("pass") is True for row in flash_rows)
        and maximum_flash <= float(contract["correctness"]["maximum_flash_attention_nmse"]),
        "semantic_A_C_byte_identical": (root / "semantic/A-C.diff").stat().st_size == 0,
        "semantic_B_D_byte_identical": (root / "semantic/B-D.diff").stat().st_size == 0,
        "dispatch": {
            "e24_q6": "E28_DISPATCH e24" in (root / "dispatch/e24.txt").read_text(),
            "e25_q4_decoded": "E28_DISPATCH e25" in (root / "dispatch/e25.txt").read_text(),
            "e27_neon_fmla": (root / "dispatch/e27-neon-fmla.txt").stat().st_size > 0,
        },
    }


def gate_summary(
    contract: dict[str, Any], correctness: dict[str, Any], quality: dict[str, Any],
    perplexity: dict[str, Any], inference: dict[str, Any]
) -> dict[str, bool]:
    thresholds = contract["performance"]["gates"]
    gates = {
        "direct_correctness": correctness["flash_passed"]
        and correctness["maximum_direct_nmse"] <= 0.0005,
        "semantic_pairs": correctness["semantic_A_C_byte_identical"]
        and correctness["semantic_B_D_byte_identical"],
        "all_dispatch_paths": all(correctness["dispatch"].values()),
        "quality_stable": all(quality[v]["predictions_stable"] for v in VARIANTS),
        "B_quality_no_loss": quality["B"]["minimum_score"] >= quality["A"]["minimum_score"],
        "D_quality_no_loss": quality["D"]["minimum_score"] >= quality["C"]["minimum_score"],
        "B_perplexity": perplexity["B_over_A"] <= 1 + perplexity["maximum_relative_increase"],
        "D_perplexity": perplexity["D_over_C"] <= 1 + perplexity["maximum_relative_increase"],
        "B_A_tg128": inference["tg128"]["B_over_A"]["ratio"] >= thresholds["B_over_A_tg128"],
        "D_C_tg128": inference["tg128"]["D_over_C"]["ratio"] >= thresholds["D_over_C_tg128"],
    }
    for case in ("pp512", "pp2048", "pp4096"):
        gates[f"C_A_{case}"] = inference[case]["C_over_A"]["ratio"] >= thresholds[f"C_over_A_{case}"]
        gates[f"D_B_{case}"] = inference[case]["D_over_B"]["ratio"] >= thresholds[f"D_over_B_{case}"]
        gates[f"B_A_{case}_guard"] = inference[case]["B_over_A"]["ratio"] >= thresholds["minimum_non_target_ratio"]
        gates[f"D_C_{case}_guard"] = inference[case]["D_over_C"]["ratio"] >= thresholds["minimum_non_target_ratio"]
    gates["C_A_tg128_guard"] = inference["tg128"]["C_over_A"]["ratio"] >= thresholds["minimum_non_target_ratio"]
    gates["D_B_tg128_guard"] = inference["tg128"]["D_over_B"]["ratio"] >= thresholds["minimum_non_target_ratio"]
    gates["accepted"] = all(gates.values())
    return gates


def build_summary(root: Path) -> dict[str, Any]:
    contract = load_object(root / "contract.json")
    if contract.get("experiment_id") != "E28":
        raise ValueError("evidence does not contain the E28 contract")
    correctness = correctness_summary(root, contract)
    quality = quality_summary(root, contract)
    perplexity = perplexity_summary(root, contract)
    inference = inference_summary(root, contract)
    sidecar = load_object(root / "source/e25-decoded-sidecar-bytes.json")
    if sidecar.get("decoded_sidecar_bytes", 0) <= 0:
        raise ValueError("decoded Q4_K sidecar byte evidence is missing")
    gates = gate_summary(contract, correctness, quality, perplexity, inference)
    return {
        "schema_version": 1,
        "experiment_id": "E28-pinned-b10216",
        "correctness": correctness,
        "quality": quality,
        "perplexity": perplexity,
        "decoded_sidecar": sidecar,
        "inference": inference,
        "cumulative_D_over_A": {
            case: inference[case]["D_over_A"] for case in ("pp512", "pp2048", "pp4096", "tg128")
        },
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
