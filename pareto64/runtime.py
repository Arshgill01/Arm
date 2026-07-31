from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .planner import build_plan, sha256_file

K_CACHE_TYPES = {"f16", "q8_0", "q4_0"}
V_CACHE_TYPES = {"f16"}
UPSTREAM_DEFAULT_BATCH_SIZE = 2048
UPSTREAM_DEFAULT_MICRO_BATCH_SIZE = 512


def server_version(server_path: Path) -> str:
    if not server_path.is_file() or not os.access(server_path, os.X_OK):
        raise ValueError(f"llama-server is not executable: {server_path}")
    resolved_server = server_path.resolve()
    result = subprocess.run(
        [str(resolved_server), "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode != 0:
        raise ValueError(f"llama-server --version failed: {output}")
    return output


def validate_server_version(output: str, expected_commit: str) -> None:
    if not isinstance(expected_commit, str) or len(expected_commit) != 40:
        raise ValueError("runtime contract lacks a full llama.cpp commit")
    if expected_commit[:9] not in output and expected_commit not in output:
        raise ValueError("llama-server version differs from the selected evidence")


def validate_model_package(
    model_root: Path,
    candidate: str,
    model: dict[str, Any],
    expected_package_size: int,
) -> list[dict[str, Any]]:
    resolved_model_root = model_root.resolve()
    candidate_root = (resolved_model_root / candidate).resolve()
    if not candidate_root.is_relative_to(resolved_model_root):
        raise ValueError("candidate directory resolves outside the model root")
    files = model.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError(f"selected candidate {candidate} has no model files")
    expected_total = 0
    validated: list[dict[str, Any]] = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("model file record must be an object")
        relative = Path(str(item.get("path", "")))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError("model file path must stay within the candidate directory")
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if not isinstance(size, int) or size <= 0 or not isinstance(digest, str):
            raise ValueError("model file record lacks a valid size or SHA-256")
        path = (candidate_root / relative).resolve()
        if not path.is_relative_to(candidate_root):
            raise ValueError("model file resolves outside the candidate directory")
        if not path.is_file() or path.stat().st_size != size:
            raise ValueError(f"model file size differs: {path}")
        observed_digest = sha256_file(path)
        if observed_digest != digest:
            raise ValueError(f"model file SHA-256 differs: {path}")
        expected_total += size
        validated.append(
            {
                "path": str(path),
                "size_bytes": size,
                "sha256": observed_digest,
            }
        )
    if expected_total != expected_package_size:
        raise ValueError("model catalog size differs from selected experiment evidence")
    return validated


def prepare_launch(
    *,
    manifest: dict[str, Any],
    constraints: dict[str, Any],
    models: dict[str, Any],
    contract: dict[str, Any],
    manifest_path: Path,
    constraints_path: Path,
    models_path: Path,
    contract_path: Path,
    model_root: Path,
    server_path: Path,
    version_output: str,
    host: str,
    port: int,
    parallel: int,
    prompt_cache: bool = True,
    context_per_slot: int | None = 256,
    kv_cache_type_k: str = "f16",
    kv_cache_type_v: str = "f16",
    batch_size: int | None = 64,
    micro_batch_size: int | None = 64,
    log_verbosity: int | None = None,
) -> dict[str, Any]:
    plan = build_plan(
        manifest,
        constraints,
        manifest_path=manifest_path,
        constraints_path=constraints_path,
    )
    selected = plan.get("selected")
    if plan.get("status") != "selected" or not isinstance(selected, dict):
        raise ValueError("deployment policy has no selected runtime")
    candidate = selected.get("name")
    if not isinstance(candidate, str):
        raise ValueError("selected plan lacks a candidate name")
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != manifest.get("experiment_id")
        or candidate not in contract.get("variants", [])
    ):
        raise ValueError("runtime contract differs from selected experiment evidence")
    model_variants = models.get("variants")
    if not isinstance(model_variants, dict) or candidate not in model_variants:
        raise ValueError("model catalog does not contain the selected candidate")
    model = model_variants[candidate]
    if model.get("framework") != "llama.cpp":
        raise ValueError("selected runtime is not supported by the launch adapter")
    provenance = manifest.get("provenance", {})
    if model.get("revision") != provenance.get("model_revisions", {}).get(
        candidate
    ) or models.get("source_model", {}).get("revision") != provenance.get(
        "source_model_revision"
    ):
        raise ValueError("model catalog revisions differ from selected evidence")
    upstream = contract.get("upstream", {})
    expected_commit = upstream.get("llama_cpp_commit")
    if expected_commit != provenance.get("llama_cpp_commit"):
        raise ValueError("runtime contract commit differs from selected evidence")
    validate_server_version(version_output, expected_commit)
    if not isinstance(host, str) or not host.strip():
        raise ValueError("runtime host must be non-empty")
    if not isinstance(port, int) or port <= 0 or port > 65535:
        raise ValueError("runtime port must be between 1 and 65535")
    if not isinstance(parallel, int) or parallel <= 0 or parallel > 16:
        raise ValueError("runtime parallel slots must be between 1 and 16")
    if not isinstance(prompt_cache, bool):
        raise ValueError("runtime prompt cache setting must be boolean")
    configuration = contract.get("configuration", {})
    threads = configuration.get("threads")
    contract_context = configuration.get("context")
    temperature = configuration.get("temperature")
    seed = configuration.get("seed")
    if (
        not isinstance(threads, int)
        or threads <= 0
        or not isinstance(contract_context, int)
        or contract_context <= 0
        or not isinstance(temperature, (int, float))
        or not isinstance(seed, int)
    ):
        raise ValueError("runtime contract has invalid server configuration")
    slot_context = contract_context if context_per_slot is None else context_per_slot
    if (
        type(slot_context) is not int
        or slot_context < 128
        or slot_context > contract_context
        or slot_context % 32 != 0
    ):
        raise ValueError(
            "context per slot must be a multiple of 32 between 128 and the "
            "validated runtime context"
        )
    if kv_cache_type_k not in K_CACHE_TYPES or kv_cache_type_v not in V_CACHE_TYPES:
        raise ValueError("KV cache type is not allowed by the verified launcher")
    if (batch_size is None) != (micro_batch_size is None):
        raise ValueError("batch size and micro-batch size must be set together")
    context_total = slot_context * parallel
    if batch_size is None:
        effective_batch_size = min(context_total, UPSTREAM_DEFAULT_BATCH_SIZE)
        effective_micro_batch_size = min(
            effective_batch_size,
            UPSTREAM_DEFAULT_MICRO_BATCH_SIZE,
        )
    else:
        if (
            type(batch_size) is not int
            or type(micro_batch_size) is not int
            or batch_size < 32
            or batch_size > context_total
            or batch_size % 32 != 0
            or micro_batch_size < 32
            or micro_batch_size > batch_size
            or micro_batch_size % 32 != 0
        ):
            raise ValueError(
                "batch sizes must be multiples of 32, the micro-batch must not "
                "exceed the batch, and the batch must fit the total context"
            )
        effective_batch_size = batch_size
        effective_micro_batch_size = micro_batch_size
    if log_verbosity is not None and (
        type(log_verbosity) is not int or not 0 <= log_verbosity <= 5
    ):
        raise ValueError("log verbosity must be between 0 and 5")
    expected_package_size = int(selected["metrics"]["package_size_bytes"])
    validated_files = validate_model_package(
        model_root, candidate, model, expected_package_size
    )
    if len(validated_files) != 1:
        raise ValueError("llama.cpp launch currently requires one GGUF entrypoint")
    entrypoint = model.get("entrypoint")
    model_path = Path(validated_files[0]["path"])
    if Path(str(entrypoint)) != Path(model["files"][0]["path"]):
        raise ValueError("validated model file differs from the selected entrypoint")
    resolved_server = server_path.resolve()
    argv = [
        str(resolved_server),
        "--model",
        str(model_path),
        "--alias",
        candidate,
        "--threads",
        str(threads),
        "--threads-batch",
        str(threads),
        "--ctx-size",
        str(slot_context * parallel),
        "--cache-type-k",
        kv_cache_type_k,
        "--cache-type-v",
        kv_cache_type_v,
        "--flash-attn",
        "auto",
        "--parallel",
        str(parallel),
        "--cont-batching",
        "--cache-prompt" if prompt_cache else "--no-cache-prompt",
        "--host",
        host,
        "--port",
        str(port),
        "--no-webui",
        "--metrics",
        "--slots",
        "--jinja",
        "--temp",
        str(temperature),
        "--seed",
        str(seed),
        "--log-colors",
        "off",
    ]
    if batch_size is not None:
        argv.extend(
            [
                "--batch-size",
                str(batch_size),
                "--ubatch-size",
                str(micro_batch_size),
            ]
        )
    if log_verbosity is not None:
        argv.extend(["--log-verbosity", str(log_verbosity)])
    return {
        "schema_version": 1,
        "service": "Pareto64",
        "status": "ready_to_launch",
        "selected_candidate": candidate,
        "selection": {
            "plan_status": plan["status"],
            "feasible_candidates": plan["feasible_candidates"],
            "pareto_frontier": [item["name"] for item in plan["pareto_frontier"]],
            "metrics": selected["metrics"],
        },
        "inputs": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "constraints_path": str(constraints_path),
            "constraints_sha256": sha256_file(constraints_path),
            "models_path": str(models_path),
            "models_sha256": sha256_file(models_path),
            "contract_path": str(contract_path),
            "contract_sha256": sha256_file(contract_path),
        },
        "model": {
            "repository": model["repository"],
            "revision": model["revision"],
            "quantization": model["quantization"],
            "files": validated_files,
        },
        "runtime": {
            "llama_cpp_commit": expected_commit,
            "server_path": str(resolved_server),
            "server_version": version_output,
            "host": host,
            "port": port,
            "threads": threads,
            "parallel_slots": parallel,
            "prompt_cache": prompt_cache,
            "kv_cache_type_k": kv_cache_type_k,
            "kv_cache_type_v": kv_cache_type_v,
            "flash_attention": "auto",
            "context_per_slot": slot_context,
            "context_total": context_total,
            "batch_size_requested": batch_size,
            "micro_batch_size_requested": micro_batch_size,
            "batch_size": effective_batch_size,
            "micro_batch_size": effective_micro_batch_size,
            "log_verbosity": log_verbosity,
            "argv": argv,
        },
        "weighted_score_used": False,
    }


def write_recipe(path: Path, recipe: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(recipe, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
