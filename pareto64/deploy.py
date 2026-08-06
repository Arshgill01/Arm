"""One-command verified sidecar-worker and certificate-gateway deployment."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .certificate import CertificateStore, sha256_value
from .gateway import GatewayHTTPServer, GatewayState
from .sidecar import _stop_child, _wait_for_health, write_object


def prepare_deployment(
    sidecar_plan: dict[str, Any],
    *,
    gateway_host: str,
    gateway_port: int,
    registry_path: Path,
    minimum_cached_tokens: int,
    revalidate_every: int,
) -> dict[str, Any]:
    if sidecar_plan.get("status") not in {
        "ready_to_launch_shared_sidecar_workers",
        "ready_to_launch_normal_workers",
    }:
        raise ValueError("deployment requires a verified worker plan")
    if not 1 <= gateway_port <= 65535:
        raise ValueError("gateway port is invalid")
    if type(minimum_cached_tokens) is not int or minimum_cached_tokens <= 0:
        raise ValueError("minimum cached tokens must be positive")
    if type(revalidate_every) is not int or revalidate_every <= 0:
        raise ValueError("revalidation interval must be positive")
    identity_binding = sidecar_plan["product_identity"]
    service = {
        "workers": [
            {
                "argv": worker["argv"],
                "environment": worker["environment"],
            }
            for worker in sidecar_plan["workers"]
        ],
        "minimum_cached_tokens": minimum_cached_tokens,
        "revalidate_every": revalidate_every,
    }
    identity = {
        "model_sha256": identity_binding["source_model_sha256"],
        "server_sha256": sidecar_plan["runtime_server_sha256"],
        "source_diff_sha256": identity_binding["source_diff_sha256"],
        "service_sha256": sha256_value(service),
    }
    plan = {
        "schema_version": 1,
        "status": "ready_to_deploy_pareto64",
        "deployment_mode": sidecar_plan["deployment_mode"],
        "sidecar": sidecar_plan["sidecar"],
        "runtime_server_sha256": sidecar_plan["runtime_server_sha256"],
        "worker_count": sidecar_plan["worker_count"],
        "workers": sidecar_plan["workers"],
        "gateway": {
            "host": gateway_host,
            "port": gateway_port,
            "registry_path": str(registry_path.resolve()),
            "minimum_cached_tokens": minimum_cached_tokens,
            "revalidate_every": revalidate_every,
            "session_header": "X-Pareto64-Session-ID",
        },
        "certificate_identity": identity,
        "claim_boundary": sidecar_plan["claim_boundary"],
    }
    plan["deployment_sha256"] = sha256_value(plan)
    return plan


def execute_deployment(
    plan: dict[str, Any],
    *,
    receipt_path: Path,
    log_dir: Path | None = None,
    readiness_timeout: float = 120.0,
    upstream_timeout: float = 120.0,
    ready_output: Path | None = None,
    stop_file: Path | None = None,
) -> dict[str, Any]:
    if plan.get("status") != "ready_to_deploy_pareto64":
        raise ValueError("deployment plan is not verified")
    if receipt_path.exists() or receipt_path.is_symlink():
        raise ValueError("deployment receipt must not already exist")
    if stop_file is not None and stop_file.exists():
        raise ValueError("deployment stop file must not exist before launch")
    if readiness_timeout <= 0 or upstream_timeout <= 0:
        raise ValueError("deployment timeouts must be positive")
    processes: list[subprocess.Popen[Any]] = []
    handles: list[Any] = []
    readiness: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    worker_returncodes: list[int] = []
    gateway: GatewayHTTPServer | None = None
    gateway_thread: threading.Thread | None = None
    failure: str | None = None
    stop_requested = False
    started = time.perf_counter()
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
    previous_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        for worker in plan["workers"]:
            environment = os.environ.copy()
            environment.update(worker["environment"])
            stdout = None
            stderr = None
            if log_dir is not None:
                stdout = (log_dir / f"worker-{worker['worker']}.stdout.log").open("wb")
                stderr = (log_dir / f"worker-{worker['worker']}.stderr.log").open("wb")
                handles.extend((stdout, stderr))
            processes.append(
                subprocess.Popen(
                    worker["argv"], env=environment, stdout=stdout, stderr=stderr
                )
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
            if plan["deployment_mode"] == "shared_sidecar":
                mappings.append(verify_shared_mapping(process.pid, plan["sidecar"]))
        gateway_config = plan["gateway"]
        store = CertificateStore(
            Path(gateway_config["registry_path"]),
            plan["certificate_identity"],
            minimum_cached_tokens=gateway_config["minimum_cached_tokens"],
            revalidate_every=gateway_config["revalidate_every"],
        )
        worker_origins = tuple(
            f"http://{worker['host']}:{worker['port']}" for worker in plan["workers"]
        )
        state = GatewayState(worker_origins, store, upstream_timeout=upstream_timeout)
        gateway = GatewayHTTPServer(
            (gateway_config["host"], gateway_config["port"]), state
        )
        gateway_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        gateway_thread.start()
        gateway_host, gateway_port = gateway.server_address
        ready = {
            "schema_version": 1,
            "status": "pareto64_deployment_ready",
            "deployment_sha256": plan["deployment_sha256"],
            "sidecar": plan["sidecar"],
            "workers": readiness,
            "shared_mappings": mappings,
            "gateway": {
                "origin": f"http://{gateway_host}:{gateway_port}",
                "health": f"http://{gateway_host}:{gateway_port}/healthz",
                "metrics": f"http://{gateway_host}:{gateway_port}/metrics",
                "session_header": gateway_config["session_header"],
            },
        }
        if ready_output is not None:
            write_object(ready_output, ready)
        while all(process.poll() is None for process in processes):
            if stop_file is not None and stop_file.exists():
                stop_requested = True
                break
            time.sleep(0.1)
    except KeyboardInterrupt:
        stop_requested = True
    except Exception as error:  # noqa: BLE001
        failure = f"{type(error).__name__}: {error}"
    finally:
        if gateway is not None:
            gateway.shutdown()
            gateway.server_close()
        if gateway_thread is not None:
            gateway_thread.join(timeout=5)
        worker_returncodes = [_stop_child(process) for process in processes]
        for handle in handles:
            handle.close()
        signal.signal(signal.SIGINT, previous_sigint)
    valid = (
        failure is None
        and len(readiness) == len(plan["workers"])
        and (
            plan["deployment_mode"] == "normal_repack"
            or len(mappings) == len(plan["workers"])
        )
        and all(value in {0, -signal.SIGINT, 130} for value in worker_returncodes)
    )
    receipt = {
        "schema_version": 1,
        "status": (
            "valid_pareto64_deployment_lifecycle"
            if valid
            else "failed_pareto64_deployment_lifecycle"
        ),
        "deployment_sha256": plan["deployment_sha256"],
        "failure": failure,
        "duration_seconds": time.perf_counter() - started,
        "stop_requested": stop_requested,
        "deployment_mode": plan["deployment_mode"],
        "sidecar": plan["sidecar"],
        "runtime_server_sha256": plan["runtime_server_sha256"],
        "certificate_identity": plan["certificate_identity"],
        "workers": readiness,
        "shared_mappings": mappings,
        "worker_returncodes": worker_returncodes,
        "gateway": plan["gateway"],
        "claim_boundary": plan["claim_boundary"],
    }
    write_object(receipt_path, receipt, read_only=True)
    return receipt


def verify_shared_mapping(pid: int, sidecar: dict[str, Any]) -> dict[str, Any]:
    expected_path = str(Path(sidecar["path"]).resolve())
    expected_inode = sidecar["inode"]
    maps_path = Path(f"/proc/{pid}/maps")
    matches = []
    for line in maps_path.read_text(encoding="utf-8").splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and fields[5] == expected_path:
            matches.append(fields)
    if not matches:
        raise ValueError(f"worker {pid} does not map the verified sidecar")
    observed = []
    for fields in matches:
        permissions = fields[1]
        inode = int(fields[4])
        if "w" in permissions or len(permissions) != 4 or permissions[3] != "s":
            raise ValueError(f"worker {pid} sidecar mapping is not read-only shared")
        if inode != expected_inode:
            raise ValueError(f"worker {pid} sidecar inode differs")
        observed.append(
            {
                "address": fields[0],
                "permissions": permissions,
                "offset": fields[2],
                "device": fields[3],
                "inode": inode,
                "path": fields[5],
            }
        )
    return {
        "pid": pid,
        "path": expected_path,
        "inode": expected_inode,
        "read_only": True,
        "shared": True,
        "regions": observed,
    }
