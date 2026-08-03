#!/usr/bin/env python3
"""Run one E11b service cell against a frozen Q4_K_M reference."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from experiments.e5b_inference_probe import (
        load_object,
        load_reference_predictions,
        run_probe,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_inference_probe import (
        load_object,
        load_reference_predictions,
        run_probe,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_parameters(
    *,
    role: str,
    candidate: str,
    reference_candidate: str,
    repetition: int,
    concurrency: int,
    max_output_tokens: int,
    timeout: float,
    server_pid: int,
) -> None:
    if (
        repetition <= 0
        or concurrency <= 0
        or max_output_tokens <= 0
        or timeout <= 0
        or server_pid <= 0
    ):
        raise ValueError("E11b probe numeric parameters must be positive")
    if role == "anchor" and candidate != reference_candidate:
        raise ValueError("E11b anchor cell must use the reference candidate")
    if role == "candidate" and candidate == reference_candidate:
        raise ValueError("E11b candidate cell must differ from the anchor")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--reference-manifest", type=Path, required=True)
    parser.add_argument("--reference-candidate", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--role", choices=("anchor", "candidate"), required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--warmup-task", action="append", default=[])
    parser.add_argument("--warmup-slot", type=int, action="append")
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--max-output-tokens", type=int, default=8)
    parser.add_argument("--seed", type=int, default=424242)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--server-pid", type=int, required=True)
    cache = parser.add_mutually_exclusive_group(required=True)
    cache.add_argument("--cache-prompt", dest="cache_prompt", action="store_true")
    cache.add_argument("--no-cache-prompt", dest="cache_prompt", action="store_false")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validate_parameters(
        role=args.role,
        candidate=args.candidate,
        reference_candidate=args.reference_candidate,
        repetition=args.repetition,
        concurrency=args.concurrency,
        max_output_tokens=args.max_output_tokens,
        timeout=args.timeout,
        server_pid=args.server_pid,
    )

    reference_manifest = load_object(args.reference_manifest)
    evidence = run_probe(
        base_url=args.url,
        tasks_manifest=load_object(args.tasks),
        reference_predictions=load_reference_predictions(
            reference_manifest, args.reference_candidate
        ),
        candidate=args.candidate,
        configuration=args.role,
        repetition=args.repetition,
        warmup_task_ids=args.warmup_task,
        concurrency=args.concurrency,
        max_output_tokens=args.max_output_tokens,
        seed=args.seed,
        timeout=args.timeout,
        experiment_id="E11b",
        cache_prompt=args.cache_prompt,
        warmup_slot_ids=args.warmup_slot,
        server_pid=args.server_pid,
    )
    evidence["reference"] = {
        "candidate": args.reference_candidate,
        "manifest_path": str(args.reference_manifest),
        "manifest_sha256": sha256_file(args.reference_manifest),
        "interpretation": "reference_match measures agreement with the frozen Q4_K_M answer; it is reported but is not a candidate validity gate",
    }
    evidence["role"] = args.role
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
