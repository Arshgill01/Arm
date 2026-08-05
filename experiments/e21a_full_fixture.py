#!/usr/bin/env python3
"""Generate and replay a complete deterministic synthetic E21a artifact."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import summarize
    from experiments.e5b_inference_probe import summarize_process_cpu
    from experiments.e9a_ingest import expected_server_argv
    from experiments.e21a_full_ingest import build_summary, expected_cell_path
    from experiments.e21a_online_policy import OnlineCertificate, identity_sha256
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import summarize_process_cpu
    from e9a_ingest import expected_server_argv
    from e21a_full_ingest import build_summary, expected_cell_path
    from e21a_online_policy import OnlineCertificate, identity_sha256


SERVER_BYTES = b"synthetic E21a llama-server fixture\n"
LATENCY_SCALE = {1: 1.00, 2: 1.02, 3: 0.99, 4: 1.01}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def call_record(
    *,
    index: int,
    served_index: int,
    task_id: str,
    fingerprint: str,
    response: str,
    cache_prompt: bool,
    cached_tokens: int,
    role: str,
    http_ms: float,
) -> dict[str, Any]:
    return {
        "http_call_index": index,
        "served_index": served_index,
        "task_id": task_id,
        "prompt_sha256": fingerprint,
        "prompt_tokens": 128,
        "cache_prompt": cache_prompt,
        "role": role,
        "http_status": 200,
        "response": response,
        "prediction": response,
        "stop_type": "limit",
        "generated_tokens": 1,
        "cached_tokens": cached_tokens,
        "evaluated_prompt_tokens": 128 - cached_tokens,
        "encode_ms": http_ms * 0.8,
        "decode_ms": http_ms * 0.2,
        "http_ms": http_ms,
        "error": None,
    }


def build_probe(
    contract: dict[str, Any], root: Path, policy: str, repetition: int, pid: int
) -> dict[str, Any]:
    tasks = json.loads((root / "experiments/e3_tasks.json").read_text())
    task_by_id = {item["id"]: item for item in tasks["tasks"]}
    fingerprints = {
        task_id: hashlib.sha256(f"e21a-full-fixture:{task_id}".encode()).hexdigest()
        for task_id in contract["workload"]["task_ids"]
    }
    if set(fingerprints.values()) & set(
        contract["prior_certificate"]["prompt_fingerprints"]
    ):
        raise ValueError("synthetic E21a fingerprint unexpectedly overlaps E13b")
    controller = OnlineCertificate(
        contract["identity"],
        minimum_cached_tokens=contract["workload"]["minimum_cached_tokens"],
    )
    scale = LATENCY_SCALE[repetition]
    raw: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    tasks_per_cycle = contract["workload"]["unique_prompts"]
    for served_index, task_id in enumerate(contract["workload"]["task_sequence"]):
        task = task_by_id[task_id]
        response = contract["workload"]["reference_predictions"][task_id]
        fingerprint = fingerprints[task_id]
        if policy == "all_uncached":
            first = call_record(
                index=len(raw),
                served_index=served_index,
                task_id=task_id,
                fingerprint=fingerprint,
                response=response,
                cache_prompt=False,
                cached_tokens=0,
                role="baseline_uncached",
                http_ms=1000.0 * scale,
            )
            raw.append(first)
            record = {
                "route": "baseline_uncached",
                "admission": None,
                "served_source": "baseline_uncached",
                "shadow_cached_attempt_served": False,
                "served_response": response,
                "served_call": first,
                "user_http_ms": first["http_ms"],
            }
        else:
            plan = controller.plan(fingerprint)
            unknown = plan["route"] == "unknown_shadow_then_oracle"
            first = call_record(
                index=len(raw),
                served_index=served_index,
                task_id=task_id,
                fingerprint=fingerprint,
                response=response,
                cache_prompt=plan["first_call_cache_prompt"],
                cached_tokens=0 if served_index == 0 else 64,
                role="unknown_cached_shadow" if unknown else plan["route"],
                http_ms=(1000.0 if unknown else 400.0) * scale,
            )
            raw.append(first)
            oracle = None
            if plan["oracle_required"]:
                oracle = call_record(
                    index=len(raw),
                    served_index=served_index,
                    task_id=task_id,
                    fingerprint=fingerprint,
                    response=response,
                    cache_prompt=False,
                    cached_tokens=0,
                    role="uncached_oracle",
                    http_ms=1000.0 * scale,
                )
                raw.append(oracle)
            completed = controller.complete(plan, first, oracle)
            record = {
                "route": completed["route"],
                "admission": completed["admission"],
                "served_source": completed["served_source"],
                "shadow_cached_attempt_served": completed[
                    "shadow_cached_attempt_served"
                ],
                "served_response": completed["served_response"],
                "served_call": completed["served_call"],
                "user_http_ms": first["http_ms"] + (oracle["http_ms"] if oracle else 0),
                "transition_sha256": completed["transition_sha256"],
            }
        record.update(
            {
                "served_index": served_index,
                "cycle_index": served_index // tasks_per_cycle + 1,
                "cycle_task_index": served_index % tasks_per_cycle,
                "task_id": task_id,
                "prompt_sha256": fingerprint,
                "expected": task["answer"],
                "reference_prediction": response,
                "prediction": response,
                "correct": response == task["answer"],
                "reference_match": True,
            }
        )
        records.append(record)

    elapsed = sum(record["user_http_ms"] for record in records) / 1000.0
    total_ticks = round((36000 if policy == "all_uncached" else 32400) * scale)
    user_ticks = round(total_ticks * 0.9)
    process_cpu = summarize_process_cpu(
        {"pid": pid, "user_ticks": 0, "system_ticks": 0, "total_ticks": 0},
        {
            "pid": pid,
            "user_ticks": user_ticks,
            "system_ticks": total_ticks - user_ticks,
            "total_ticks": total_ticks,
        },
        clock_ticks_per_second=100,
        measured_requests=len(records),
        elapsed_seconds=elapsed,
    )
    routes = Counter(record["route"] for record in records)
    admissions = Counter(
        record["admission"] for record in records if record["admission"]
    )
    return {
        "schema_version": 1,
        "experiment_id": "E21a",
        "policy": policy,
        "repetition": repetition,
        "identity_sha256": identity_sha256(contract["identity"]),
        "unseen_prompt_fingerprints": fingerprints,
        "served_records": records,
        "raw_calls": raw,
        "process_cpu": process_cpu,
        "result": {
            "served_requests": len(records),
            "actual_http_calls": len(raw),
            "elapsed_seconds": elapsed,
            "served_requests_per_second": len(records) / elapsed,
            "request_failures": 0,
            "correct": sum(record["correct"] for record in records),
            "reference_prediction_mismatches": 0,
            "route_counts": dict(sorted(routes.items())),
            "admission_counts": dict(sorted(admissions.items())),
            "user_http_ms": summarize([record["user_http_ms"] for record in records]),
            "raw_http_ms": summarize([record["http_ms"] for record in raw]),
        },
        "registry": controller.export_registry() if policy == "online" else None,
    }


def materialize_fixture(
    destination: Path, contract: dict[str, Any], root: Path
) -> tuple[Path, Path]:
    synthetic = copy.deepcopy(contract)
    server_sha = hashlib.sha256(SERVER_BYTES).hexdigest()
    synthetic["acceptance"]["server_binary_sha256"] = server_sha
    synthetic["identity"]["server_sha256"] = server_sha
    synthetic["identity_sha256"] = identity_sha256(synthetic["identity"])
    contract_path = destination / "contract.json"
    write_json(contract_path, synthetic)
    evidence = destination / "evidence"
    write_json(evidence / "contract.json", synthetic)
    write_json(
        evidence / "github.json",
        {
            "run_id": "synthetic",
            "run_attempt": 1,
            "sha": "synthetic",
            "ref": "synthetic",
            "runner_os": "Linux",
            "runner_arch": "ARM64",
        },
    )
    (evidence / "lscpu.txt").write_text(
        "Architecture: aarch64\nCPU(s): 4\nModel name: Neoverse-N2\n"
        "Socket(s): 1\nThread(s) per core: 1\nFlags: asimd asimddp i8mm sve sve2\n"
    )
    runtime = evidence / "build/runtime-files/bin/llama-server"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(SERVER_BYTES)
    closure = {
        "build_root": "/synthetic/build",
        "server_relative_path": "bin/llama-server",
        "file_count": 1,
        "files": [
            {
                "relative_path": "bin/llama-server",
                "artifact_relative_path": "runtime-files/bin/llama-server",
                "size_bytes": len(SERVER_BYTES),
                "sha256": server_sha,
            }
        ],
        "runtime_dependencies": [],
        "ldd_output": "synthetic static fixture\n",
    }
    write_json(evidence / "build/runtime-closure.json", closure)
    write_json(
        evidence / "source.json",
        {
            "commit": synthetic["service"]["source_commit"],
            "tag": synthetic["service"]["source_tag"],
        },
    )
    (evidence / "source-diff.patch").write_bytes(
        (root / "patches/llama.cpp/b10216/e6f-current-series.patch").read_bytes()
    )
    server_path = "/synthetic/runtime/bin/llama-server"
    model_path = "/synthetic/models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf"
    for spec in synthetic["execution"]["cell_order"]:
        cell = evidence / "cells" / expected_cell_path(spec)
        cell.mkdir(parents=True, exist_ok=True)
        pid = 4200 + spec["index"]
        recipe = {
            "schema_version": 1,
            "experiment_id": "E21a",
            "policy": spec["policy"],
            "repetition": spec["repetition"],
            "profile_name": "e7c_final",
            "service": synthetic["service"],
            "server_path": server_path,
            "server_version": f"synthetic {synthetic['service']['source_commit'][:9]}",
            "model": {
                "candidate": synthetic["selected"]["candidate"],
                "path": model_path,
                "sha256": synthetic["selected"]["model_sha256"],
                "size_bytes": synthetic["selected"]["model_size_bytes"],
            },
            "argv": expected_server_argv(
                server_path,
                model_path,
                candidate=synthetic["selected"]["candidate"],
                profile_name="e7c_final",
            ),
        }
        write_json(cell / "recipe.json", recipe)
        write_json(
            cell / "probe.json",
            build_probe(synthetic, root, spec["policy"], spec["repetition"], pid),
        )
        write_json(
            cell / "readiness.json",
            {"status": "ok", "ready_ms": 2500.0 * LATENCY_SCALE[spec["repetition"]]},
        )
        write_json(cell / "slots.json", [{"id": 0, "state": 0}])
        (cell / "server-pid.txt").write_text(f"{pid}\n")
        (cell / "server-shell-exit.txt").write_text("130\n")
        (cell / "server-time.log").write_text(
            "\tCommand being timed: synthetic llama-server\n"
            f"\tMaximum resident set size (kbytes): {4290000 + spec['repetition']}\n"
            "\tPercent of CPU this job got: 350%\n"
            "\tElapsed (wall clock) time (h:mm:ss or m:ss): 2:00.00\n"
            "\tExit status: 130\n"
        )
    return evidence, contract_path


def run_synthetic_replay(
    contract: dict[str, Any], root: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    values = []
    payloads = []
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        for name in ("one", "two"):
            evidence, contract_path = materialize_fixture(
                temporary / name, contract, root
            )
            value = build_summary(evidence, contract_path, root)
            payload = canonical_bytes(value)
            values.append(value)
            payloads.append(payload)
    if payloads[0] != payloads[1]:
        raise ValueError("E21a complete synthetic replay is not byte-stable")
    return values[0], {
        "complete_cells": contract["execution"]["total_cells"],
        "served_requests": contract["execution"]["total_served_requests"],
        "independent_replays": 2,
        "byte_stable": True,
        "summary_bytes": len(payloads[0]),
        "summary_sha256": hashlib.sha256(payloads[0]).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    summary, replay = run_synthetic_replay(contract, args.root.resolve())
    result = {"summary": summary, "replay": replay}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(replay, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
