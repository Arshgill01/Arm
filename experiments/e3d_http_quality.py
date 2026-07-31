#!/usr/bin/env python3
"""Wait for llama-server and capture the frozen E3 quality workload over HTTP."""

from __future__ import annotations

import argparse
import http.client
import json
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlsplit


def request_json(
    base_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    timeout: float,
) -> tuple[int, dict[str, Any], float]:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.path not in {"", "/"}:
        raise ValueError("--url must be an HTTP origin without a path")
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if encoded is not None:
        headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    started = time.perf_counter_ns()
    try:
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"{path} did not return a JSON object")
        return response.status, payload, elapsed_ms
    finally:
        connection.close()


def wait_for_health(base_url: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter_ns()
    deadline = time.monotonic() + timeout
    attempts = 0
    last_error = "server did not respond"
    while time.monotonic() < deadline:
        attempts += 1
        try:
            status, payload, _ = request_json(base_url, "GET", "/health", None, 2.0)
            if status == 200 and payload.get("status") == "ok":
                return {
                    "schema_version": 1,
                    "status": "ok",
                    "attempts": attempts,
                    "ready_ms": (time.perf_counter_ns() - started) / 1_000_000,
                    "response": payload,
                }
            last_error = f"HTTP {status}: {payload}"
        except (OSError, ValueError, json.JSONDecodeError) as error:
            last_error = f"{type(error).__name__}: {error}"
        time.sleep(0.1)
    raise TimeoutError(f"llama-server readiness timed out: {last_error}")


def run_quality(
    base_url: str,
    tasks: dict[str, Any],
    model: str,
    model_path: str,
    load_ms: float,
    threads: int,
    context: int,
    max_output_tokens: int,
    seed: int,
    timeout: float,
) -> dict[str, Any]:
    if tasks.get("schema_version") != 1 or not isinstance(tasks.get("tasks"), list):
        raise ValueError("invalid E3 task manifest")
    instruction = tasks.get("instruction")
    if not isinstance(instruction, str) or not instruction:
        raise ValueError("task manifest lacks an instruction")

    cases: list[dict[str, Any]] = []
    for task in tasks["tasks"]:
        prompt = f"{instruction}\n\n{task['prompt']}"
        status, response, http_ms = request_json(
            base_url,
            "POST",
            "/v1/chat/completions",
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "seed": seed,
                "max_tokens": max_output_tokens,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout,
        )
        if status != 200:
            raise RuntimeError(f"quality request {task['id']} failed: HTTP {status}: {response}")
        choices = response.get("choices")
        timings = response.get("timings")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(timings, dict):
            raise ValueError(f"quality response {task['id']} lacks choices or timings")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError(f"quality response {task['id']} lacks text content")
        prompt_ms = float(timings.get("prompt_ms"))
        predicted_ms = float(timings.get("predicted_ms"))
        predicted_n = int(timings.get("predicted_n"))
        if prompt_ms < 0 or predicted_ms < 0 or predicted_n < 0:
            raise ValueError(f"quality response {task['id']} has invalid timings")
        cases.append(
            {
                "id": task["id"],
                "response": message["content"],
                "generated_tokens": predicted_n,
                "encode_ms": prompt_ms,
                "decode_ms": predicted_ms,
                "http_ms": http_ms,
                "termination_reason": choice.get("finish_reason"),
            }
        )

    return {
        "schema_version": 1,
        "framework": "llama.cpp",
        "transport": "OpenAI-compatible HTTP",
        "model_path": model_path,
        "threads": threads,
        "context_size": context,
        "max_output_tokens": max_output_tokens,
        "chat_template_mode": "model_jinja_enable_thinking_false",
        "temperature": 0.0,
        "seed": seed,
        "model_load_ms": load_ms,
        "cases": cases,
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    wait = commands.add_parser("wait")
    wait.add_argument("--url", required=True)
    wait.add_argument("--timeout", type=float, default=30.0)
    wait.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--url", required=True)
    run.add_argument("--tasks", type=Path, required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--model-path", required=True)
    run.add_argument("--load-ms", type=float, required=True)
    run.add_argument("--threads", type=int, default=4)
    run.add_argument("--context", type=int, default=2048)
    run.add_argument("--max-output-tokens", type=int, default=8)
    run.add_argument("--seed", type=int, default=424242)
    run.add_argument("--timeout", type=float, default=30.0)
    run.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    if arguments.command == "wait":
        if arguments.timeout <= 0:
            raise ValueError("--timeout must be positive")
        write_json(arguments.output, wait_for_health(arguments.url, arguments.timeout))
        return 0
    if arguments.command == "run":
        if (
            arguments.load_ms < 0
            or arguments.threads <= 0
            or arguments.context <= 0
            or arguments.max_output_tokens <= 0
            or arguments.timeout <= 0
        ):
            raise ValueError("quality runtime values must be positive")
        tasks = json.loads(arguments.tasks.read_text(encoding="utf-8"))
        if not isinstance(tasks, dict):
            raise ValueError("task manifest must be a JSON object")
        write_json(
            arguments.output,
            run_quality(
                arguments.url,
                tasks,
                arguments.model,
                arguments.model_path,
                arguments.load_ms,
                arguments.threads,
                arguments.context,
                arguments.max_output_tokens,
                arguments.seed,
                arguments.timeout,
            ),
        )
        return 0
    raise AssertionError(f"unsupported command {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())
