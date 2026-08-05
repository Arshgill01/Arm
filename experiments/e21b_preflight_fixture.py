#!/usr/bin/env python3
"""Materialize and replay a complete deterministic E21b preflight artifact."""

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
    from experiments.e21a_online_policy import OnlineCertificate, identity_sha256
    from experiments.e21b_openai_probe import (
        canonical_sha256,
        openai_request_payload,
    )
    from experiments.e21b_preflight_ingest import build_summary
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import summarize
    from e5b_inference_probe import summarize_process_cpu
    from e9a_ingest import expected_server_argv
    from e21a_online_policy import OnlineCertificate, identity_sha256
    from e21b_openai_probe import canonical_sha256, openai_request_payload
    from e21b_preflight_ingest import build_summary


SERVER_BYTES = b"synthetic E21b OpenAI-compatible llama-server fixture\n"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def synthetic_call(
    *,
    call_index: int,
    served_index: int,
    task: dict[str, Any],
    instruction: str,
    fingerprint: str,
    response: str,
    cache_prompt: bool,
    cached_tokens: int,
    role: str,
    contract: dict[str, Any],
    http_ms: float,
) -> dict[str, Any]:
    payload = openai_request_payload(
        candidate=contract["selected"]["candidate"],
        instruction=instruction,
        task=task,
        cache_prompt=cache_prompt,
        maximum_output_tokens=contract["workload"]["maximum_output_tokens"],
        seed=contract["workload"]["seed"],
    )
    return {
        "http_call_index": call_index,
        "served_index": served_index,
        "task_id": task["id"],
        "api_path": contract["client"]["api_path"],
        "request_payload": payload,
        "request_payload_sha256": canonical_sha256(payload),
        "prompt_sha256": fingerprint,
        "prompt_tokens": 128,
        "cache_prompt": cache_prompt,
        "role": role,
        "http_status": 200,
        "response": response,
        "prediction": response,
        "stop_type": "stop",
        "generated_tokens": 1,
        "cached_tokens": cached_tokens,
        "evaluated_prompt_tokens": 128 - cached_tokens,
        "encode_ms": http_ms * 0.8,
        "decode_ms": http_ms * 0.2,
        "http_ms": http_ms,
        "error": None,
    }


def build_probe(
    contract: dict[str, Any], root: Path, policy: str, pid: int
) -> dict[str, Any]:
    task_data = json.loads((root / "experiments/e3_tasks.json").read_text())
    task_by_id = {item["id"]: item for item in task_data["tasks"]}
    fingerprints = {
        task_id: hashlib.sha256(f"e21b-fixture:{task_id}".encode()).hexdigest()
        for task_id in contract["workload"]["task_ids"]
    }
    if set(fingerprints.values()) & set(
        contract["prior_certificate"]["prompt_fingerprints"]
    ):
        raise ValueError("synthetic E21b fingerprint unexpectedly overlaps E13b")
    controller = OnlineCertificate(
        contract["identity"],
        minimum_cached_tokens=contract["workload"]["minimum_cached_tokens"],
    )
    raw: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for served_index, task_id in enumerate(contract["workload"]["task_sequence"]):
        task = task_by_id[task_id]
        response = contract["workload"]["reference_predictions"][task_id]
        fingerprint = fingerprints[task_id]
        if policy == "all_uncached":
            first = synthetic_call(
                call_index=len(raw),
                served_index=served_index,
                task=task,
                instruction=task_data["instruction"],
                fingerprint=fingerprint,
                response=response,
                cache_prompt=False,
                cached_tokens=0,
                role="baseline_uncached",
                contract=contract,
                http_ms=1000.0,
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
            cached_tokens = (
                0
                if plan["previous_prompt_sha256"] == "start"
                else 64
                if plan["first_call_cache_prompt"]
                else 0
            )
            first = synthetic_call(
                call_index=len(raw),
                served_index=served_index,
                task=task,
                instruction=task_data["instruction"],
                fingerprint=fingerprint,
                response=response,
                cache_prompt=plan["first_call_cache_prompt"],
                cached_tokens=cached_tokens,
                role="unknown_cached_shadow" if unknown else plan["route"],
                contract=contract,
                http_ms=1000.0 if unknown else 400.0,
            )
            raw.append(first)
            oracle = None
            if plan["oracle_required"]:
                oracle = synthetic_call(
                    call_index=len(raw),
                    served_index=served_index,
                    task=task,
                    instruction=task_data["instruction"],
                    fingerprint=fingerprint,
                    response=response,
                    cache_prompt=False,
                    cached_tokens=0,
                    role="uncached_oracle",
                    contract=contract,
                    http_ms=1000.0,
                )
                raw.append(oracle)
            completed = controller.complete(plan, first, oracle)
            record = {
                "route": completed["route"],
                "admission": completed["admission"],
                "served_source": completed["served_source"],
                "shadow_cached_attempt_served": False,
                "served_response": completed["served_response"],
                "served_call": completed["served_call"],
                "user_http_ms": first["http_ms"]
                + (oracle["http_ms"] if oracle else 0.0),
                "transition_sha256": completed["transition_sha256"],
            }
        record.update(
            {
                "served_index": served_index,
                "cycle_index": served_index // 30 + 1,
                "cycle_task_index": served_index % 30,
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

    elapsed = sum(item["user_http_ms"] for item in records) / 1000.0
    total_ticks = 18000 if policy == "all_uncached" else 16200
    process_cpu = summarize_process_cpu(
        {"pid": pid, "user_ticks": 0, "system_ticks": 0, "total_ticks": 0},
        {
            "pid": pid,
            "user_ticks": int(total_ticks * 0.9),
            "system_ticks": total_ticks - int(total_ticks * 0.9),
            "total_ticks": total_ticks,
        },
        clock_ticks_per_second=100,
        measured_requests=len(records),
        elapsed_seconds=elapsed,
    )
    routes = Counter(item["route"] for item in records)
    admissions = Counter(item["admission"] for item in records if item["admission"])
    return {
        "schema_version": 1,
        "experiment_id": "E21b-preflight",
        "policy": policy,
        "identity_sha256": identity_sha256(contract["identity"]),
        "client_identity_sha256": contract["client_identity_sha256"],
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
            "correct": sum(item["correct"] for item in records),
            "reference_prediction_mismatches": 0,
            "route_counts": dict(sorted(routes.items())),
            "admission_counts": dict(sorted(admissions.items())),
            "user_http_ms": summarize([item["user_http_ms"] for item in records]),
            "raw_http_ms": summarize([item["http_ms"] for item in raw]),
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
    write_json(
        evidence / "build/runtime-closure.json",
        {
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
        },
    )
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
    for index, policy in enumerate(synthetic["execution"]["cell_order"], start=1):
        cell = evidence / "cells" / f"{index:02d}-{policy}"
        cell.mkdir(parents=True, exist_ok=True)
        pid = 5200 + index
        write_json(
            cell / "recipe.json",
            {
                "schema_version": 1,
                "experiment_id": "E21b-preflight",
                "policy": policy,
                "profile_name": "e7c_final",
                "service": synthetic["service"],
                "client": synthetic["client"],
                "server_path": server_path,
                "server_version": (
                    f"synthetic {synthetic['service']['source_commit'][:9]}"
                ),
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
            },
        )
        write_json(cell / "probe.json", build_probe(synthetic, root, policy, pid))
        write_json(cell / "readiness.json", {"status": "ok", "ready_ms": 2500.0})
        write_json(cell / "slots.json", [{"id": 0, "state": 0}])
        (cell / "server-pid.txt").write_text(f"{pid}\n")
        (cell / "server-shell-exit.txt").write_text("130\n")
        (cell / "server-time.log").write_text(
            "\tCommand being timed: synthetic llama-server\n"
            "\tMaximum resident set size (kbytes): 4290000\n"
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
        raise ValueError("E21b complete synthetic replay is not byte-stable")
    return values[0], {
        "control_cells": 1,
        "candidate_cells": 1,
        "served_requests": 120,
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
    contract = json.loads(args.contract.read_text())
    summary, replay = run_synthetic_replay(contract, args.root.resolve())
    args.output.write_bytes(canonical_bytes({"summary": summary, "replay": replay}))
    print(json.dumps(replay, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
