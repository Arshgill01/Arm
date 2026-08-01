from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .planner import build_plan, sha256_file
from .service_planner import build_service_plan

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


def _run_git(source_root: Path, *arguments: str, binary: bool = False) -> Any:
    result = subprocess.run(
        ["git", "-C", str(source_root), *arguments],
        check=False,
        capture_output=True,
        text=not binary,
        timeout=30,
    )
    if result.returncode != 0:
        stderr = result.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        raise ValueError(f"runtime source git verification failed: {stderr.strip()}")
    return result.stdout


def validate_runtime_upgrade(
    *,
    runtime_manifest: dict[str, Any],
    runtime_contract: dict[str, Any],
    runtime_manifest_path: Path,
    runtime_contract_path: Path,
    model_manifest_path: Path,
    source_root: Path,
    build_root: Path,
    server_path: Path,
    selected_candidate: str,
    baseline_commit: str,
) -> dict[str, Any]:
    """Bind an opt-in runtime upgrade to exact evidence, source, and build."""
    if (
        json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
        != runtime_manifest
        or json.loads(runtime_contract_path.read_text(encoding="utf-8"))
        != runtime_contract
    ):
        raise ValueError("runtime upgrade objects differ from their input files")
    manifest_record = runtime_contract.get("runtime_manifest", {})
    model_record = runtime_contract.get("model_selection_manifest", {})
    runtime_record = runtime_contract.get("runtime", {})
    build_record = runtime_contract.get("build", {})
    if (
        runtime_contract.get("schema_version") != 1
        or runtime_contract.get("promotion_mode")
        != "explicit_evidence_bound_upgrade"
        or runtime_contract.get("selected_candidate") != selected_candidate
        or manifest_record.get("experiment_id") != "E6f"
        or manifest_record.get("sha256") != sha256_file(runtime_manifest_path)
        or model_record.get("experiment_id") != "E3f"
        or model_record.get("sha256") != sha256_file(model_manifest_path)
        or runtime_record.get("baseline_commit") != baseline_commit
    ):
        raise ValueError("runtime upgrade contract differs from selected evidence")

    manifest_contract = runtime_manifest.get("contract", {})
    manifest_runtimes = manifest_contract.get("runtimes", {})
    candidate_runtime = manifest_contract.get("execution", {}).get(
        "candidate_runtime"
    )
    selected_source = manifest_runtimes.get(candidate_runtime, {})
    selected_commit = runtime_record.get("selected_commit")
    expected_patches = [
        {"name": patch.get("name"), "sha256": patch.get("sha256")}
        for patch in selected_source.get("patches", [])
    ]
    quality_profiles = list(runtime_manifest.get("performance", {}).values())
    validation = runtime_manifest.get("validation", {})
    if (
        runtime_manifest.get("schema_version") != 1
        or runtime_manifest.get("experiment_id") != "E6f"
        or runtime_manifest.get("status")
        != "valid_current_runtime_upgrade_candidate"
        or manifest_contract.get("inputs", {}).get("manifest_sha256")
        != model_record.get("sha256")
        or manifest_contract.get("selected", {}).get("candidate")
        != selected_candidate
        or selected_source.get("commit") != selected_commit
        or runtime_record.get("patches") != expected_patches
        or runtime_manifest.get("selection", {}).get("selected_runtime")
        != candidate_runtime
        or runtime_manifest.get("selection", {}).get("selected_commit")
        != selected_commit
        or runtime_manifest.get("hypothesis", {}).get("passed") is not True
        or validation.get("upgrade_candidate_claim_allowed") is not True
        or validation.get("automatic_product_promotion_allowed") is not False
        or validation.get("exact_patch_series_verified") is not True
        or validation.get("exact_model_verified") is not True
        or not quality_profiles
        or any(
            profile.get("quality", {}).get("exact_selected_predictions") is not True
            for profile in quality_profiles
        )
    ):
        raise ValueError("runtime upgrade manifest is not an accepted E6f result")

    resolved_source = source_root.resolve()
    resolved_build = build_root.resolve()
    resolved_server = server_path.resolve()
    relative_server = Path(str(build_record.get("server_relative_path", "")))
    expected_server = resolved_build / relative_server
    if (
        relative_server.is_absolute()
        or not relative_server.parts
        or ".." in relative_server.parts
        or not resolved_source.is_dir()
        or not resolved_build.is_dir()
        or not resolved_server.is_relative_to(resolved_build)
        or resolved_server != expected_server.resolve()
        or not resolved_server.is_file()
        or not os.access(resolved_server, os.X_OK)
    ):
        raise ValueError("runtime server is not the contract-bound build output")

    observed_commit = str(_run_git(resolved_source, "rev-parse", "HEAD")).strip()
    changed_files = str(
        _run_git(resolved_source, "diff", "--name-only", "HEAD", "--")
    ).splitlines()
    source_diff = _run_git(
        resolved_source,
        "diff",
        "--binary",
        "--full-index",
        "HEAD",
        "--",
        binary=True,
    )
    source_diff_sha256 = hashlib.sha256(source_diff).hexdigest()
    if (
        observed_commit != selected_commit
        or changed_files != runtime_record.get("changed_files")
        or source_diff_sha256 != runtime_record.get("source_diff_sha256")
    ):
        raise ValueError("runtime source tree differs from the exact patched series")

    cache_path = resolved_build / "CMakeCache.txt"
    if not cache_path.is_file():
        raise ValueError("runtime build lacks CMakeCache.txt")
    cache_lines = set(
        cache_path.read_text(encoding="utf-8", errors="replace").splitlines()
    )
    required_cache = set(build_record.get("cmake_cache_entries", []))
    if (
        not required_cache
        or not required_cache.issubset(cache_lines)
        or f"CMAKE_HOME_DIRECTORY:INTERNAL={resolved_source}" not in cache_lines
    ):
        raise ValueError("runtime build cache differs from the upgrade contract")

    return {
        "contract_id": runtime_contract.get("contract_id"),
        "promotion_mode": runtime_contract["promotion_mode"],
        "runtime_manifest_sha256": sha256_file(runtime_manifest_path),
        "runtime_contract_sha256": sha256_file(runtime_contract_path),
        "source_root": str(resolved_source),
        "source_commit": observed_commit,
        "source_diff_sha256": source_diff_sha256,
        "changed_files": changed_files,
        "patches": expected_patches,
        "build_root": str(resolved_build),
        "cmake_cache_sha256": sha256_file(cache_path),
        "server_sha256": sha256_file(resolved_server),
        "selected_commit": selected_commit,
        "claim_boundary": runtime_contract.get("claim_boundary"),
    }


def validate_runtime_upgrade_service(
    runtime_manifest: dict[str, Any],
    runtime_contract: dict[str, Any],
    observed: dict[str, Any],
) -> None:
    manifest_service = dict(runtime_manifest.get("contract", {}).get("service", {}))
    manifest_service.pop("client_concurrency", None)
    manifest_service.pop("warmup_slot_ids", None)
    manifest_service["parallel_slots"] = manifest_service.pop(
        "server_parallel_slots", None
    )
    manifest_service["log_verbosity"] = None
    if manifest_service != runtime_contract.get("service") or observed != manifest_service:
        raise ValueError("runtime upgrade is limited to the exact E6f service profile")


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
    threads: int | None = None,
    prompt_cache: bool = True,
    context_per_slot: int | None = 256,
    kv_cache_type_k: str = "f16",
    kv_cache_type_v: str = "f16",
    batch_size: int | None = 64,
    micro_batch_size: int | None = 64,
    flash_attention: str = "auto",
    weight_repack: bool | None = None,
    log_verbosity: int | None = None,
    service_manifest: dict[str, Any] | None = None,
    service_constraints: dict[str, Any] | None = None,
    service_manifest_path: Path | None = None,
    service_constraints_path: Path | None = None,
    runtime_manifest: dict[str, Any] | None = None,
    runtime_contract: dict[str, Any] | None = None,
    runtime_manifest_path: Path | None = None,
    runtime_contract_path: Path | None = None,
    runtime_source_root: Path | None = None,
    runtime_build_root: Path | None = None,
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
    service_inputs = (
        service_manifest,
        service_constraints,
        service_manifest_path,
        service_constraints_path,
    )
    if any(item is not None for item in service_inputs) and not all(
        item is not None for item in service_inputs
    ):
        raise ValueError(
            "service launch requires both the manifest and constraints with paths"
        )
    runtime_inputs = (
        runtime_manifest,
        runtime_contract,
        runtime_manifest_path,
        runtime_contract_path,
        runtime_source_root,
        runtime_build_root,
    )
    if any(item is not None for item in runtime_inputs) and not all(
        item is not None for item in runtime_inputs
    ):
        raise ValueError(
            "runtime upgrade requires its manifest, contract, source, and build paths"
        )
    service_plan: dict[str, Any] | None = None
    service_selected: dict[str, Any] | None = None
    if service_manifest is not None:
        service_plan = build_service_plan(
            service_manifest,
            service_constraints,
            manifest_path=service_manifest_path,
            constraints_path=service_constraints_path,
        )
        service_selected = service_plan.get("selected")
        if service_plan.get("status") != "selected" or not isinstance(
            service_selected, dict
        ):
            raise ValueError("service policy has no selected measured profile")
        if service_plan.get("inputs", {}).get("selected_candidate") != candidate:
            raise ValueError("service profile differs from the selected model")
        selected_repack = service_selected.get("runtime", {}).get("weight_repack")
        if not isinstance(selected_repack, bool):
            raise ValueError("service plan lacks a bounded repack setting")
        if weight_repack is not None and weight_repack is not selected_repack:
            raise ValueError("manual repack setting conflicts with the service plan")
        resolved_weight_repack = selected_repack
    else:
        if weight_repack is not None and not isinstance(weight_repack, bool):
            raise ValueError("runtime weight repack setting must be boolean")
        resolved_weight_repack = True if weight_repack is None else weight_repack
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
    historical_commit = upstream.get("llama_cpp_commit")
    if historical_commit != provenance.get("llama_cpp_commit"):
        raise ValueError("runtime contract commit differs from selected evidence")
    runtime_upgrade: dict[str, Any] | None = None
    if runtime_manifest is not None:
        runtime_upgrade = validate_runtime_upgrade(
            runtime_manifest=runtime_manifest,
            runtime_contract=runtime_contract,
            runtime_manifest_path=runtime_manifest_path,
            runtime_contract_path=runtime_contract_path,
            model_manifest_path=manifest_path,
            source_root=runtime_source_root,
            build_root=runtime_build_root,
            server_path=server_path,
            selected_candidate=candidate,
            baseline_commit=historical_commit,
        )
        expected_commit = runtime_upgrade["selected_commit"]
    else:
        expected_commit = historical_commit
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
    contract_threads = configuration.get("threads")
    contract_context = configuration.get("context")
    temperature = configuration.get("temperature")
    seed = configuration.get("seed")
    if (
        not isinstance(contract_threads, int)
        or contract_threads <= 0
        or not isinstance(contract_context, int)
        or contract_context <= 0
        or not isinstance(temperature, (int, float))
        or not isinstance(seed, int)
    ):
        raise ValueError("runtime contract has invalid server configuration")
    resolved_threads = contract_threads if threads is None else threads
    if (
        type(resolved_threads) is not int
        or resolved_threads <= 0
        or resolved_threads > contract_threads
    ):
        raise ValueError(
            "runtime threads must be between 1 and the validated contract thread count"
        )
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
    if flash_attention not in {"auto", "on", "off"}:
        raise ValueError("flash attention must be auto, on, or off")
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
    if runtime_upgrade is not None:
        validate_runtime_upgrade_service(
            runtime_manifest,
            runtime_contract,
            {
                "batch_size": effective_batch_size,
                "context_per_slot": slot_context,
                "flash_attention": flash_attention,
                "kv_cache_type_k": kv_cache_type_k,
                "kv_cache_type_v": kv_cache_type_v,
                "log_verbosity": log_verbosity,
                "micro_batch_size": effective_micro_batch_size,
                "parallel_slots": parallel,
                "prompt_cache": prompt_cache,
                "threads": resolved_threads,
                "weight_repack": resolved_weight_repack,
            },
        )
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
        str(resolved_threads),
        "--threads-batch",
        str(resolved_threads),
        "--ctx-size",
        str(slot_context * parallel),
        "--cache-type-k",
        kv_cache_type_k,
        "--cache-type-v",
        kv_cache_type_v,
        "--flash-attn",
        flash_attention,
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
    if not resolved_weight_repack:
        argv.append("--no-repack")
    if log_verbosity is not None:
        argv.extend(["--log-verbosity", str(log_verbosity)])
    selection_record = {
        "plan_status": plan["status"],
        "feasible_candidates": plan["feasible_candidates"],
        "pareto_frontier": [item["name"] for item in plan["pareto_frontier"]],
        "metrics": selected["metrics"],
    }
    input_record = {
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "constraints_path": str(constraints_path),
        "constraints_sha256": sha256_file(constraints_path),
        "models_path": str(models_path),
        "models_sha256": sha256_file(models_path),
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
    }
    if service_plan is not None and service_selected is not None:
        selection_record["service_profile"] = {
            "plan_status": service_plan["status"],
            "name": service_selected["name"],
            "feasible_profiles": service_plan["feasible_profiles"],
            "pareto_frontier": [
                item["name"] for item in service_plan["pareto_frontier"]
            ],
            "metrics": service_selected["metrics"],
        }
        input_record.update(
            {
                "service_manifest_path": str(service_manifest_path),
                "service_manifest_sha256": sha256_file(service_manifest_path),
                "service_constraints_path": str(service_constraints_path),
                "service_constraints_sha256": sha256_file(
                    service_constraints_path
                ),
            }
        )
    if runtime_upgrade is not None:
        selection_record["runtime_upgrade"] = {
            "status": runtime_manifest["status"],
            "experiment_id": runtime_manifest["experiment_id"],
            "selected_commit": expected_commit,
            "promotion_mode": runtime_upgrade["promotion_mode"],
        }
        input_record.update(
            {
                "runtime_manifest_path": str(runtime_manifest_path),
                "runtime_manifest_sha256": sha256_file(runtime_manifest_path),
                "runtime_contract_path": str(runtime_contract_path),
                "runtime_contract_sha256": sha256_file(runtime_contract_path),
            }
        )
    return {
        "schema_version": 1,
        "service": "Pareto64",
        "status": "ready_to_launch",
        "selected_candidate": candidate,
        "selection": selection_record,
        "inputs": input_record,
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
            "threads": resolved_threads,
            "parallel_slots": parallel,
            "prompt_cache": prompt_cache,
            "kv_cache_type_k": kv_cache_type_k,
            "kv_cache_type_v": kv_cache_type_v,
            "flash_attention": flash_attention,
            "context_per_slot": slot_context,
            "context_total": context_total,
            "batch_size_requested": batch_size,
            "micro_batch_size_requested": micro_batch_size,
            "batch_size": effective_batch_size,
            "micro_batch_size": effective_micro_batch_size,
            "weight_repack": resolved_weight_repack,
            "log_verbosity": log_verbosity,
            "argv": argv,
            **(
                {"upgrade_provenance": runtime_upgrade}
                if runtime_upgrade is not None
                else {}
            ),
        },
        "weighted_score_used": False,
    }


def write_recipe(path: Path, recipe: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(recipe, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
