#!/usr/bin/env python3
"""Execute the frozen Pareto64 accept-backlog search."""

from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

try:
    from experiments.e5_http_probe import run_probe
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5_http_probe import run_probe


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def get_json(host: str, port: int, path: str, timeout: float) -> dict[str, Any]:
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        payload = json.loads(response.read())
        if response.status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"GET {path} returned {response.status}")
        return payload
    finally:
        connection.close()


def wait_ready(
    process: subprocess.Popen[bytes], host: str, port: int, timeout: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited before readiness with {process.returncode}")
        try:
            health = get_json(host, port, "/healthz", 0.5)
            if health.get("status") == "ok":
                return health
        except (ConnectionError, OSError, TimeoutError):
            pass
        time.sleep(0.05)
    raise TimeoutError("server did not become ready")


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)


def wait_for_bounded_server(process: subprocess.Popen[bytes]) -> int:
    try:
        return process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        children_path = Path(f"/proc/{process.pid}/task/{process.pid}/children")
        child_pids = [
            int(value)
            for value in children_path.read_text(encoding="utf-8").split()
        ]
        if len(child_pids) != 1:
            raise RuntimeError("could not identify the bounded server child process")
        os.kill(child_pids[0], signal.SIGINT)
        return process.wait(timeout=10)


def run_candidate(
    root: Path,
    output_dir: Path,
    contract: dict[str, Any],
    policy: dict[str, Any],
    backlog: int,
    round_number: int,
    position: int,
) -> dict[str, Any]:
    run_dir = output_dir / f"round-{round_number}-position-{position}-backlog-{backlog}"
    run_dir.mkdir(parents=True, exist_ok=False)
    server = contract["server"]
    probe_contract = contract["probe"]
    maximum_requests = (
        probe_contract["readiness_requests"]
        + probe_contract["warmups"]
        + probe_contract["measured_requests"]
        + 1
    )
    command = [
        "/usr/bin/time",
        "--verbose",
        "--output",
        str(run_dir / "server-time.log"),
        sys.executable,
        "-m",
        "pareto64",
        "serve",
        "--manifest",
        contract["inputs"]["manifest_path"],
        "--constraints",
        contract["inputs"]["policy_path"],
        "--host",
        server["host"],
        "--port",
        str(server["port"]),
        "--backlog",
        str(backlog),
        "--max-requests",
        str(maximum_requests),
    ]
    (run_dir / "command.json").write_text(
        json.dumps(command, indent=2) + "\n", encoding="utf-8"
    )
    started = time.perf_counter_ns()
    exit_status: int | None = None
    with (run_dir / "server.stdout.log").open("wb") as stdout, (
        run_dir / "server.stderr.log"
    ).open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=root,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        try:
            health = wait_ready(process, server["host"], server["port"], 5.0)
            (run_dir / "health.json").write_text(
                json.dumps(health, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            evidence = run_probe(
                f"http://{server['host']}:{server['port']}",
                policy,
                probe_contract["warmups"],
                probe_contract["measured_requests"],
                probe_contract["concurrency"],
                probe_contract["timeout_seconds"],
            )
            (run_dir / "probe.json").write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            metrics = get_json(
                server["host"], server["port"], "/metrics", 5.0
            )
            (run_dir / "service-metrics.json").write_text(
                json.dumps(metrics, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            exit_status = wait_for_bounded_server(process)
        finally:
            stop_process(process)
    elapsed_seconds = (time.perf_counter_ns() - started) / 1_000_000_000
    if exit_status != 0:
        raise RuntimeError(f"backlog {backlog} server exited {exit_status}")
    return {
        "round": round_number,
        "position": position,
        "backlog": backlog,
        "directory": run_dir.name,
        "elapsed_seconds": elapsed_seconds,
        "server_exit_status": exit_status,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    contract = read_json(arguments.contract)
    if contract.get("experiment_id") != "E4a":
        raise ValueError("contract does not identify E4a")
    root = Path.cwd().resolve()
    policy = read_json(root / contract["inputs"]["policy_path"])
    arguments.output_dir.mkdir(parents=True, exist_ok=False)
    search_started = time.perf_counter_ns()
    runs = []
    for round_number, order in enumerate(contract["execution_order"], start=1):
        if sorted(order) != sorted(contract["candidates"]):
            raise ValueError("execution order does not contain every candidate")
        for position, backlog in enumerate(order, start=1):
            runs.append(
                run_candidate(
                    root,
                    arguments.output_dir,
                    contract,
                    policy,
                    backlog,
                    round_number,
                    position,
                )
            )
    execution = {
        "schema_version": 1,
        "experiment_id": "E4a",
        "search_elapsed_seconds": (
            time.perf_counter_ns() - search_started
        )
        / 1_000_000_000,
        "runs": runs,
    }
    (arguments.output_dir / "execution.json").write_text(
        json.dumps(execution, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
