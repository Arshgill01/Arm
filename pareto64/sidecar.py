"""Identity-bound lifecycle for persistent Arm repack sidecars."""

from __future__ import annotations

import json
import math
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .planner import sha256_file
from .repack import (
    build_sidecar,
    create_identity,
    parse_inventory,
    verify_sidecar,
)
from .runtime import server_version, validate_server_version

SIDECAR_ENVIRONMENT = {
    "GGML_CPU_REPACK_SIDECAR": lambda path, binding: str(path),
    "GGML_CPU_REPACK_SIDECAR_EXPERIMENT_ID": lambda path, binding: binding[
        "experiment_id"
    ],
    "GGML_CPU_REPACK_SIDECAR_MODEL_SHA256": lambda path, binding: binding[
        "source_model_sha256"
    ],
    "GGML_CPU_REPACK_SIDECAR_SOURCE_COMMIT": lambda path, binding: binding[
        "llama_cpp_commit"
    ],
    "GGML_CPU_REPACK_SIDECAR_SOURCE_DIFF_SHA256": lambda path, binding: binding[
        "source_diff_sha256"
    ],
    "GGML_CPU_REPACK_SIDECAR_ARCHITECTURE": lambda path, binding: binding["cpu"][
        "architecture"
    ],
    "GGML_CPU_REPACK_SIDECAR_CPU_FEATURES_SHA256": lambda path, binding: binding["cpu"][
        "common_features_sha256"
    ],
    "GGML_CPU_REPACK_SIDECAR_SVE_BYTES": lambda path, binding: str(
        binding["cpu"]["sve_vector_length_bytes"]
    ),
}
WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
SPACE_MARGIN_BYTES = 64 * 1024 * 1024


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object: {path}")
    return value


def write_object(path: Path, value: dict[str, Any], *, read_only: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if read_only:
        path.chmod(0o444)


def _regular_read_only(path: Path) -> bool:
    if path.is_symlink():
        return False
    mode = path.stat().st_mode
    return stat.S_ISREG(mode) and mode & WRITE_BITS == 0


def _runtime_root(server_path: Path) -> Path:
    resolved = server_path.resolve()
    if resolved.parent.name != "bin":
        raise ValueError("sidecar llama-server must be in a runtime bin directory")
    return resolved.parent.parent


def _validate_runtime_closure(
    server_path: Path, evidence: dict[str, Any]
) -> dict[str, Any]:
    closure = evidence.get("source_build", {}).get("runtime_closure", {})
    files = closure.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("E16 evidence lacks its runtime closure")
    root = _runtime_root(server_path)
    observed = []
    server_record = None
    for record in files:
        relative = Path(str(record.get("relative_path", "")))
        path = (root / relative).resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not path.is_relative_to(root.resolve())
            or not path.is_file()
            or path.stat().st_size != record.get("size_bytes")
            or sha256_file(path) != record.get("sha256")
        ):
            raise ValueError(f"sidecar runtime closure differs: {relative}")
        item = {
            "relative_path": relative.as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        observed.append(item)
        if relative.as_posix() == closure.get("server_relative_path"):
            server_record = item
            if path != server_path.resolve():
                raise ValueError("sidecar server path differs from runtime closure")
    if server_record is None or len(observed) != closure.get("file_count"):
        raise ValueError("sidecar runtime closure inventory differs")
    return {
        "runtime_root": str(root.resolve()),
        "file_count": len(observed),
        "files": observed,
        "server_sha256": server_record["sha256"],
    }


def validate_product_inputs(
    *,
    contract_path: Path,
    evidence_path: Path,
    model_path: Path,
    server_path: Path,
    require_cpu: bool = True,
) -> dict[str, Any]:
    contract = load_object(contract_path)
    evidence = load_object(evidence_path)
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E16c"
        or evidence.get("schema_version") != 1
        or evidence.get("experiment_id") != "E16c"
        or evidence.get("status") != "valid_shared_sidecar_workers_promoted"
        or evidence.get("promoted") is not True
        or not all(evidence.get("gates", {}).values())
        or evidence.get("decision", {}).get(
            "multi_process_physical_sharing_claim_permitted"
        )
        is not True
        or evidence.get("contract_sha256") != sha256_file(contract_path)
    ):
        raise ValueError("sidecar product inputs lack promoted E16c evidence")
    selected = contract.get("selected", {})
    resolved_model = model_path.resolve()
    if (
        not resolved_model.is_file()
        or resolved_model.stat().st_size != selected.get("model_size_bytes")
        or sha256_file(resolved_model) != selected.get("model_sha256")
    ):
        raise ValueError("sidecar model differs from the E16c identity")
    runtime = _validate_runtime_closure(server_path, evidence)
    version = server_version(server_path)
    validate_server_version(version, contract["source"]["commit"])
    identity = create_identity(contract_path)
    if require_cpu and identity.get("cpu", {}).get("architecture") != "aarch64":
        raise ValueError("sidecar lifecycle requires a native aarch64 host")
    if (
        identity.get("source_model_sha256") != selected.get("model_sha256")
        or identity.get("llama_cpp_commit") != contract["source"]["commit"]
        or identity.get("source_diff_sha256")
        != contract["source"]["aggregate_diff_sha256"]
    ):
        raise ValueError("sidecar generated identity differs from the E16c contract")
    return {
        "contract": contract,
        "contract_sha256": sha256_file(contract_path),
        "evidence": evidence,
        "evidence_sha256": sha256_file(evidence_path),
        "model_path": str(resolved_model),
        "model_sha256": selected["model_sha256"],
        "model_size_bytes": resolved_model.stat().st_size,
        "server_path": str(server_path.resolve()),
        "server_version": version,
        "runtime": runtime,
        "identity": identity,
    }


def _sidecar_environment(sidecar_path: Path, binding: dict[str, Any]) -> dict[str, str]:
    return {
        name: function(sidecar_path.resolve(), binding)
        for name, function in SIDECAR_ENVIRONMENT.items()
    }


def verify_product_sidecar(
    *,
    contract_path: Path,
    evidence_path: Path,
    model_path: Path,
    server_path: Path,
    sidecar_path: Path,
    index_path: Path,
    receipt_path: Path | None = None,
    require_cpu: bool = True,
) -> dict[str, Any]:
    inputs = validate_product_inputs(
        contract_path=contract_path,
        evidence_path=evidence_path,
        model_path=model_path,
        server_path=server_path,
        require_cpu=require_cpu,
    )
    started = time.perf_counter()
    verification = verify_sidecar(sidecar_path, index_path)
    elapsed = time.perf_counter() - started
    index = load_object(index_path)
    binding = index.get("header", {}).get("binding")
    if binding != inputs["identity"]:
        raise ValueError("sidecar header differs from the current model/source/CPU")
    if not _regular_read_only(sidecar_path) or not _regular_read_only(index_path):
        raise ValueError("sidecar and index must both be regular read-only files")
    receipt = None
    if receipt_path is not None:
        receipt = load_object(receipt_path)
        if (
            not _regular_read_only(receipt_path)
            or receipt.get("status") != "valid_persistent_arm_sidecar"
            or receipt.get("contract", {}).get("sha256") != inputs["contract_sha256"]
            or receipt.get("evidence", {}).get("sha256") != inputs["evidence_sha256"]
            or receipt.get("model", {}).get("sha256") != inputs["model_sha256"]
            or receipt.get("runtime", {}).get("server_sha256")
            != inputs["runtime"]["server_sha256"]
            or receipt.get("sidecar", {}).get("sha256")
            != verification["sidecar_sha256"]
            or receipt.get("sidecar", {}).get("path") != str(sidecar_path.resolve())
            or receipt.get("sidecar", {}).get("index_path") != str(index_path.resolve())
            or receipt.get("sidecar", {}).get("index_sha256") != sha256_file(index_path)
            or receipt.get("sidecar", {}).get("index_size_bytes")
            != index_path.stat().st_size
            or receipt.get("identity") != inputs["identity"]
        ):
            raise ValueError("sidecar receipt differs from verified product inputs")
    sidecar_stat = sidecar_path.stat()
    return {
        "schema_version": 1,
        "status": "valid_persistent_arm_sidecar",
        "verification_seconds": elapsed,
        "contract_sha256": inputs["contract_sha256"],
        "evidence_sha256": inputs["evidence_sha256"],
        "model_sha256": inputs["model_sha256"],
        "runtime_server_sha256": inputs["runtime"]["server_sha256"],
        "sidecar_sha256": verification["sidecar_sha256"],
        "index_sha256": sha256_file(index_path),
        "tensor_count": verification["tensor_count"],
        "binding": binding,
        "read_only": True,
        "mapping": {
            "protection": "PROT_READ",
            "sharing": "MAP_SHARED",
            "offset_bytes": index["header"]["data_offset"],
            "device": sidecar_stat.st_dev,
            "inode": sidecar_stat.st_ino,
        },
        "environment": _sidecar_environment(sidecar_path, binding),
        "receipt_verified": receipt is not None,
    }


def service_argv(
    server_path: Path,
    model_path: Path,
    contract: dict[str, Any],
    *,
    host: str,
    port: int,
    threads: int = 4,
) -> list[str]:
    if type(threads) is not int or not 1 <= threads <= 4:
        raise ValueError("sidecar worker threads must be between 1 and 4")
    argv = [
        str(server_path.resolve()),
        "--model",
        str(model_path.resolve()),
        "--alias",
        contract["selected"]["candidate"],
        "--threads",
        str(threads),
        "--threads-batch",
        str(threads),
        "--ctx-size",
        "256",
        "--cache-type-k",
        "f16",
        "--cache-type-v",
        "f16",
        "--flash-attn",
        "auto",
        "--parallel",
        "1",
        "--cont-batching",
        "--cache-prompt",
        "--host",
        host,
        "--port",
        str(port),
        "--no-webui",
        "--metrics",
        "--slots",
        "--jinja",
        "--temp",
        "0.0",
        "--seed",
        "424242",
        "--log-colors",
        "off",
        "--batch-size",
        "64",
        "--ubatch-size",
        "64",
    ]
    argv.extend(["--log-verbosity", str(contract["mechanism"]["proof_log_verbosity"])])
    return argv


def _wait_for_health(
    origin: str, process: subprocess.Popen[Any], timeout: float
) -> float:
    started = time.perf_counter()
    deadline = started + timeout
    while time.perf_counter() < deadline:
        if process.poll() is not None:
            raise ValueError(
                f"sidecar server exited before readiness: {process.returncode}"
            )
        try:
            with urllib.request.urlopen(f"{origin}/health", timeout=1.0) as response:
                if response.status == 200:
                    return time.perf_counter() - started
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise TimeoutError("sidecar server did not become ready")


def _stop_child(process: subprocess.Popen[Any]) -> int:
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
    try:
        return process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait(timeout=10)


def _space_check(
    *, scratch_root: Path, output_parent: Path, arena_bytes: int, sidecar_bytes: int
) -> dict[str, Any]:
    scratch_root.mkdir(parents=True, exist_ok=True)
    output_parent.mkdir(parents=True, exist_ok=True)
    scratch_free = shutil.disk_usage(scratch_root).free
    output_free = shutil.disk_usage(output_parent).free
    same_device = scratch_root.stat().st_dev == output_parent.stat().st_dev
    scratch_required = arena_bytes + SPACE_MARGIN_BYTES
    output_required = sidecar_bytes + SPACE_MARGIN_BYTES
    if same_device:
        if scratch_free < scratch_required + output_required:
            raise ValueError("insufficient free space for raw repack plus sidecar")
    elif scratch_free < scratch_required or output_free < output_required:
        raise ValueError("insufficient free space for sidecar lifecycle")
    return {
        "same_device": same_device,
        "scratch_free_before_bytes": scratch_free,
        "output_free_before_bytes": output_free,
        "scratch_required_bytes": scratch_required,
        "output_required_bytes": output_required,
    }


def _cleanup_generated_dump(dump_dir: Path) -> dict[str, Any]:
    tensors, _ = parse_inventory(dump_dir)
    raw_bytes = 0
    for tensor in tensors:
        path = dump_dir / tensor["file"]
        if not path.is_file() or path.stat().st_size != tensor["bytes"]:
            raise ValueError(f"generated tensor differs before cleanup: {path}")
        raw_bytes += path.stat().st_size
        path.unlink()
    if list(dump_dir.glob("*.bin")):
        raise ValueError("generated tensor cleanup is incomplete")
    parent = dump_dir.parent.resolve()
    resolved = dump_dir.resolve()
    if not resolved.is_relative_to(parent) or resolved == parent:
        raise ValueError("refusing unsafe generated dump cleanup")
    shutil.rmtree(resolved)
    return {
        "deleted_raw_tensor_bytes": raw_bytes,
        "deleted_raw_tensor_count": len(tensors),
        "raw_tensor_cleanup_complete": not resolved.exists(),
    }


def _evidence_boundaries(
    contract: dict[str, Any],
    evidence: dict[str, Any],
    identity: dict[str, Any],
    prepack_seconds: float,
) -> dict[str, Any]:
    matched_cpu = evidence.get("sidecar_identity") == identity
    root = Path(__file__).resolve().parents[1]
    single_path = root / contract["inputs"]["e16b_result_path"]
    if sha256_file(single_path) != contract["inputs"]["e16b_result_sha256"]:
        raise ValueError("E16b warm-start evidence differs from the E16c contract")
    single = load_object(single_path)
    normal_ready = single["performance"]["normal_repack"]["ready_ms"]["median"] / 1000
    sidecar_ready = single["performance"]["sidecar_loader"]["ready_ms"]["median"] / 1000
    saving = normal_ready - sidecar_ready
    starts = math.ceil(prepack_seconds / saving) if matched_cpu and saving > 0 else None
    return {
        "cold_storage": {
            "measured": False,
            "claim_permitted": False,
            "reason": "Linux page cache was not flushed in E16b or E16c.",
        },
        "warm_process_start": {
            "matched_native_evidence": matched_cpu,
            "readiness_ratio": single["ratios"]["readiness"] if matched_cpu else None,
            "normal_median_seconds": normal_ready if matched_cpu else None,
            "sidecar_median_seconds": sidecar_ready if matched_cpu else None,
            "same_job_observed_cache_state_only": True,
        },
        "multi_worker": {
            "matched_native_evidence": matched_cpu,
            "workers": 2,
            "summed_pss_ratio": evidence["ratios"]["summed_post_workload_pss"]
            if matched_cpu
            else None,
            "summed_pss_saved_kib": evidence["summed_post_workload_pss_saved_kib"]
            if matched_cpu
            else None,
            "per_process_rss_reduction_claim_permitted": False,
        },
        "amortization": {
            "prepack_seconds": prepack_seconds,
            "warm_start_saving_seconds_per_worker": saving if matched_cpu else None,
            "warm_start_break_even_worker_starts_estimate": starts,
            "estimate_boundary": (
                "Matched Neoverse N2 same-job warm-readiness evidence only; excludes "
                "cold storage, request work, energy, money, and maintenance cost."
            ),
        },
    }


def prepack_sidecar(
    *,
    contract_path: Path,
    evidence_path: Path,
    model_path: Path,
    server_path: Path,
    sidecar_path: Path,
    index_path: Path,
    receipt_path: Path,
    lifecycle_dir: Path,
    scratch_root: Path,
    host: str = "127.0.0.1",
    port: int = 18081,
    readiness_timeout: float = 120.0,
) -> dict[str, Any]:
    outputs = (sidecar_path, index_path, receipt_path, lifecycle_dir)
    resolved_outputs = {path.resolve() for path in outputs}
    if len(resolved_outputs) != len(outputs):
        raise ValueError("sidecar prepack outputs must be distinct")
    if any(path.exists() or path.is_symlink() for path in outputs):
        raise ValueError("sidecar prepack outputs must not already exist")
    inputs = validate_product_inputs(
        contract_path=contract_path,
        evidence_path=evidence_path,
        model_path=model_path,
        server_path=server_path,
    )
    evidence_index = inputs["evidence"]["construction"]["sidecar_index"]
    space = _space_check(
        scratch_root=scratch_root,
        output_parent=sidecar_path.parent,
        arena_bytes=evidence_index["header"]["arena_size_bytes"],
        sidecar_bytes=evidence_index["sidecar_size_bytes"],
    )
    lifecycle_dir.mkdir(parents=True, exist_ok=True)
    dump_dir = Path(tempfile.mkdtemp(prefix="pareto64-sidecar-", dir=scratch_root))
    identity_path = lifecycle_dir / "identity.json"
    write_object(identity_path, inputs["identity"])
    argv = service_argv(
        server_path,
        model_path,
        inputs["contract"],
        host=host,
        port=port,
    )
    recipe = {
        "schema_version": 1,
        "phase": "one_time_sidecar_prepack",
        "argv": argv,
        "runtime_environment": {
            "GGML_CPU_REPACK_DUMP_DIR": "fresh generated scratch directory",
            "GGML_CPU_REPACK_SIDECAR": None,
        },
    }
    write_object(lifecycle_dir / "construction-recipe.json", recipe)
    env = os.environ.copy()
    env["GGML_CPU_REPACK_DUMP_DIR"] = str(dump_dir)
    for name in SIDECAR_ENVIRONMENT:
        env.pop(name, None)
    total_started = time.perf_counter()
    process: subprocess.Popen[Any] | None = None
    ready_seconds = None
    returncode = None
    try:
        with (
            (lifecycle_dir / "server.stdout.log").open("wb") as stdout,
            (lifecycle_dir / "server.stderr.log").open("wb") as stderr,
        ):
            server_started = time.perf_counter()
            process = subprocess.Popen(argv, env=env, stdout=stdout, stderr=stderr)
            ready_seconds = _wait_for_health(
                f"http://{host}:{port}", process, readiness_timeout
            )
            returncode = _stop_child(process)
            server_seconds = time.perf_counter() - server_started
        if returncode not in {0, -signal.SIGINT, 130}:
            raise ValueError(f"sidecar construction server failed: {returncode}")
        shutil.copy2(dump_dir / "inventory.tsv", lifecycle_dir / "inventory.tsv")
        shutil.copy2(dump_dir / "runtime.tsv", lifecycle_dir / "runtime.tsv")
        build_started = time.perf_counter()
        index = build_sidecar(dump_dir, inputs["identity"], sidecar_path)
        write_object(index_path, index)
        build_seconds = time.perf_counter() - build_started
        verify_started = time.perf_counter()
        verification = verify_sidecar(sidecar_path, index_path)
        verification_seconds = time.perf_counter() - verify_started
        cleanup = _cleanup_generated_dump(dump_dir)
        sidecar_path.chmod(0o444)
        index_path.chmod(0o444)
        total_seconds = time.perf_counter() - total_started
        lifecycle_bytes = sum(
            path.stat().st_size for path in lifecycle_dir.iterdir() if path.is_file()
        )
        receipt = {
            "schema_version": 1,
            "status": "valid_persistent_arm_sidecar",
            "contract": {
                "path": str(contract_path.resolve()),
                "sha256": inputs["contract_sha256"],
            },
            "evidence": {
                "path": str(evidence_path.resolve()),
                "sha256": inputs["evidence_sha256"],
                "run_id": inputs["evidence"]["github"]["run_id"],
            },
            "model": {
                "path": inputs["model_path"],
                "sha256": inputs["model_sha256"],
                "size_bytes": inputs["model_size_bytes"],
            },
            "runtime": {
                "server_path": inputs["server_path"],
                "server_sha256": inputs["runtime"]["server_sha256"],
                "closure": inputs["runtime"],
            },
            "identity": inputs["identity"],
            "sidecar": {
                "path": str(sidecar_path.resolve()),
                "index_path": str(index_path.resolve()),
                "index_sha256": sha256_file(index_path),
                "index_size_bytes": index_path.stat().st_size,
                "sha256": verification["sidecar_sha256"],
                "size_bytes": sidecar_path.stat().st_size,
                "tensor_count": verification["tensor_count"],
                "mode": "0444",
                "mapping_protection": "PROT_READ",
                "mapping_sharing": "MAP_SHARED",
                "mapping_offset_bytes": index["header"]["data_offset"],
            },
            "construction": {
                "server_start_to_ready_seconds": ready_seconds,
                "server_process_seconds": server_seconds,
                "server_returncode": returncode,
                "sidecar_build_seconds": build_seconds,
                "full_verification_seconds": verification_seconds,
                "total_prepack_seconds": total_seconds,
                "cleanup": cleanup,
            },
            "storage": {
                "space_preflight": space,
                "raw_repack_bytes": cleanup["deleted_raw_tensor_bytes"],
                "sidecar_bytes": sidecar_path.stat().st_size,
                "index_bytes": index_path.stat().st_size,
                "retained_lifecycle_metadata_bytes_before_receipt": lifecycle_bytes,
                "raw_plus_sidecar_peak_bytes": (
                    cleanup["deleted_raw_tensor_bytes"] + sidecar_path.stat().st_size
                ),
            },
            "boundaries": _evidence_boundaries(
                inputs["contract"],
                inputs["evidence"],
                inputs["identity"],
                total_seconds,
            ),
            "cleanup_policy": {
                "raw_generated_tensors_deleted": True,
                "sidecar_cleanup_requires_hash_bound_receipt": True,
            },
        }
        write_object(receipt_path, receipt, read_only=True)
        return receipt
    except Exception as error:
        if process is not None and process.poll() is None:
            _stop_child(process)
        failure = {
            "schema_version": 1,
            "status": "failed_persistent_arm_sidecar_prepack",
            "error": f"{type(error).__name__}: {error}",
            "generated_dump_removed": False,
        }
        if dump_dir.exists():
            parent = dump_dir.parent.resolve()
            resolved = dump_dir.resolve()
            if resolved.is_relative_to(parent) and resolved != parent:
                shutil.rmtree(resolved)
                failure["generated_dump_removed"] = True
        removed_outputs = []
        for output in (sidecar_path, index_path, receipt_path):
            if output.is_file():
                output.chmod(0o600)
                output.unlink()
                removed_outputs.append(str(output.resolve()))
        failure["incomplete_outputs_removed"] = removed_outputs
        write_object(lifecycle_dir / "failure.json", failure)
        raise


def prepare_sidecar_launch(
    *,
    contract_path: Path,
    evidence_path: Path,
    model_path: Path,
    server_path: Path,
    sidecar_path: Path,
    index_path: Path,
    receipt_path: Path,
    workers: int = 2,
    threads: int = 4,
    host: str = "127.0.0.1",
    base_port: int = 18081,
) -> dict[str, Any]:
    if type(workers) is not int or not 1 <= workers <= 64:
        raise ValueError("sidecar workers must be between 1 and 64")
    if type(threads) is not int or not 1 <= threads <= 4:
        raise ValueError("sidecar worker threads must be between 1 and 4")
    if not 1 <= base_port <= 65535 or base_port + workers - 1 > 65535:
        raise ValueError("sidecar worker port range is invalid")
    verification = verify_product_sidecar(
        contract_path=contract_path,
        evidence_path=evidence_path,
        model_path=model_path,
        server_path=server_path,
        sidecar_path=sidecar_path,
        index_path=index_path,
        receipt_path=receipt_path,
    )
    contract = load_object(contract_path)
    environment = verification["environment"]
    stat_result = sidecar_path.stat()
    return {
        "schema_version": 1,
        "status": "ready_to_launch_shared_sidecar_workers",
        "worker_count": workers,
        "threads_per_worker": threads,
        "verification_passes": 1,
        "verification_seconds": [verification["verification_seconds"]],
        "verification_scope": (
            "one complete identity-bound sidecar verification before launch; "
            "each worker mapping is verified after readiness"
        ),
        "sidecar": {
            "path": str(sidecar_path.resolve()),
            "sha256": verification["sidecar_sha256"],
            "read_only": True,
            "device": stat_result.st_dev,
            "inode": stat_result.st_ino,
            "mapping_protection": "PROT_READ",
            "mapping_sharing": "MAP_SHARED",
        },
        "runtime_server_sha256": verification["runtime_server_sha256"],
        "product_identity": verification["binding"],
        "deployment_mode": "shared_sidecar",
        "workers": [
            {
                "worker": worker,
                "host": host,
                "port": base_port + worker - 1,
                "argv": service_argv(
                    server_path,
                    model_path,
                    contract,
                    host=host,
                    port=base_port + worker - 1,
                    threads=threads,
                ),
                "environment": environment,
            }
            for worker in range(1, workers + 1)
        ],
        "claim_boundary": contract["claim_boundary"],
    }


def prepare_normal_launch(
    *,
    contract_path: Path,
    evidence_path: Path,
    model_path: Path,
    server_path: Path,
    workers: int = 2,
    threads: int = 4,
    host: str = "127.0.0.1",
    base_port: int = 18081,
) -> dict[str, Any]:
    if type(workers) is not int or not 1 <= workers <= 64:
        raise ValueError("normal workers must be between 1 and 64")
    if type(threads) is not int or not 1 <= threads <= 4:
        raise ValueError("normal worker threads must be between 1 and 4")
    if not 1 <= base_port <= 65535 or base_port + workers - 1 > 65535:
        raise ValueError("normal worker port range is invalid")
    inputs = validate_product_inputs(
        contract_path=contract_path,
        evidence_path=evidence_path,
        model_path=model_path,
        server_path=server_path,
    )
    contract = inputs["contract"]
    return {
        "schema_version": 1,
        "status": "ready_to_launch_normal_workers",
        "deployment_mode": "normal_repack",
        "worker_count": workers,
        "threads_per_worker": threads,
        "sidecar": None,
        "runtime_server_sha256": inputs["runtime"]["server_sha256"],
        "product_identity": inputs["identity"],
        "workers": [
            {
                "worker": worker,
                "host": host,
                "port": base_port + worker - 1,
                "argv": service_argv(
                    server_path,
                    model_path,
                    contract,
                    host=host,
                    port=base_port + worker - 1,
                    threads=threads,
                ),
                "environment": {},
            }
            for worker in range(1, workers + 1)
        ],
        "claim_boundary": contract["claim_boundary"],
    }


def execute_sidecar_group(
    plan: dict[str, Any],
    *,
    log_dir: Path | None = None,
    readiness_timeout: float = 120.0,
    ready_output: Path | None = None,
    stop_file: Path | None = None,
) -> dict[str, Any]:
    if plan.get("status") != "ready_to_launch_shared_sidecar_workers":
        raise ValueError("sidecar launch plan is not verified")
    if readiness_timeout <= 0:
        raise ValueError("sidecar readiness timeout must be positive")
    if stop_file is not None and stop_file.exists():
        raise ValueError("sidecar stop file must not exist before launch")
    processes: list[subprocess.Popen[Any]] = []
    handles: list[Any] = []
    readiness: list[dict[str, Any]] = []
    failure: str | None = None
    stop_requested = False
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
    previous_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        for worker in plan["workers"]:
            env = os.environ.copy()
            env.update(worker["environment"])
            stdout = None
            stderr = None
            if log_dir is not None:
                stdout = (log_dir / f"worker-{worker['worker']}.stdout.log").open("wb")
                stderr = (log_dir / f"worker-{worker['worker']}.stderr.log").open("wb")
                handles.extend((stdout, stderr))
            processes.append(
                subprocess.Popen(worker["argv"], env=env, stdout=stdout, stderr=stderr)
            )
        for worker, process in zip(plan["workers"], processes, strict=True):
            elapsed = _wait_for_health(
                f"http://{worker['host']}:{worker['port']}",
                process,
                readiness_timeout,
            )
            readiness.append(
                {
                    "worker": worker["worker"],
                    "pid": process.pid,
                    "host": worker["host"],
                    "port": worker["port"],
                    "ready_seconds": elapsed,
                }
            )
        ready = {
            "schema_version": 1,
            "status": "shared_sidecar_workers_ready",
            "worker_count": len(readiness),
            "sidecar": plan["sidecar"],
            "workers": readiness,
        }
        if ready_output is not None:
            write_object(ready_output, ready)
        while all(process.poll() is None for process in processes):
            if stop_file is not None and stop_file.exists():
                stop_requested = True
                break
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    except Exception as error:  # noqa: BLE001
        failure = f"{type(error).__name__}: {error}"
    finally:
        statuses = [_stop_child(process) for process in processes]
        for handle in handles:
            handle.close()
        signal.signal(signal.SIGINT, previous_sigint)
    return {
        "status": (
            "sidecar_worker_group_stopped"
            if failure is None
            and len(readiness) == len(plan["workers"])
            and all(value in {0, -signal.SIGINT, 130} for value in statuses)
            else "sidecar_worker_group_failed"
        ),
        "error": failure,
        "readiness": readiness,
        "stop_requested": stop_requested,
        "worker_returncodes": statuses,
    }


def cleanup_sidecar(receipt_path: Path, *, execute: bool = False) -> dict[str, Any]:
    receipt = load_object(receipt_path)
    sidecar = Path(str(receipt.get("sidecar", {}).get("path", "")))
    index = Path(str(receipt.get("sidecar", {}).get("index_path", "")))
    if (
        receipt.get("status") != "valid_persistent_arm_sidecar"
        or not _regular_read_only(receipt_path)
        or not sidecar.is_absolute()
        or not index.is_absolute()
        or sidecar.resolve() == index.resolve()
        or not sidecar.is_file()
        or not index.is_file()
        or sha256_file(sidecar) != receipt["sidecar"]["sha256"]
        or sha256_file(index) != receipt["sidecar"].get("index_sha256")
        or index.stat().st_size != receipt["sidecar"].get("index_size_bytes")
        or load_object(index).get("sidecar_sha256") != receipt["sidecar"]["sha256"]
    ):
        raise ValueError("cleanup receipt does not match the retained sidecar")
    targets = [
        {"path": str(sidecar), "size_bytes": sidecar.stat().st_size},
        {"path": str(index), "size_bytes": index.stat().st_size},
    ]
    if execute:
        sidecar.unlink()
        index.unlink()
    return {
        "schema_version": 1,
        "status": "sidecar_cleanup_complete" if execute else "sidecar_cleanup_planned",
        "receipt_retained": True,
        "targets": targets,
        "deleted": execute,
        "targets_absent": execute and not sidecar.exists() and not index.exists(),
    }
