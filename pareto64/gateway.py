"""Certificate-aware OpenAI gateway for a bounded Pareto64 worker group."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, deque
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .certificate import (
    CertificateStore,
    canonical_bytes,
    sha256_value,
    valid_call,
)

MAX_REQUEST_BYTES = 1024 * 1024
SESSION_HEADER = "X-Pareto64-Session-ID"
LATENCY_WINDOW = 4096


@dataclass
class GatewayState:
    worker_origins: tuple[str, ...]
    certificate_store: CertificateStore
    upstream_timeout: float = 120.0
    started_ns: int = field(default_factory=time.monotonic_ns)
    route_counts: Counter[str] = field(default_factory=Counter)
    source_counts: Counter[str] = field(default_factory=Counter)
    admission_counts: Counter[str] = field(default_factory=Counter)
    request_count: int = 0
    error_count: int = 0
    oracle_calls: int = 0
    cached_tokens: int = 0
    latencies_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=LATENCY_WINDOW)
    )
    metrics_lock: threading.Lock = field(default_factory=threading.Lock)
    session_locks: dict[str, threading.Lock] = field(default_factory=dict)
    session_locks_lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if not self.worker_origins:
            raise ValueError("gateway requires at least one worker")
        if any(not origin.startswith("http://") for origin in self.worker_origins):
            raise ValueError("gateway workers must use explicit HTTP origins")
        if self.upstream_timeout <= 0:
            raise ValueError("gateway upstream timeout must be positive")

    def _session_lock(self, session_digest: str) -> threading.Lock:
        with self.session_locks_lock:
            return self.session_locks.setdefault(session_digest, threading.Lock())

    def route(
        self, session_id: str, request_payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        if request_payload.get("stream") is True:
            raise GatewayError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "streaming is outside this certificate boundary",
            )
        if not isinstance(request_payload.get("messages"), list):
            raise GatewayError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "messages must be a JSON array",
            )
        payload = dict(request_payload)
        payload.pop("cache_prompt", None)
        prompt_digest = sha256_value(payload)
        session_digest, controller = self.certificate_store.controller(session_id)
        worker_index = int(session_digest, 16) % len(self.worker_origins)
        origin = self.worker_origins[worker_index]
        started = time.perf_counter_ns()
        with self._session_lock(session_digest):
            # Reload after waiting so concurrent requests for one session cannot
            # use a stale transition state.
            session_digest, controller = self.certificate_store.controller(session_id)
            plan = controller.plan(prompt_digest)
            first = call_worker(
                origin,
                payload,
                cache_prompt=plan["first_call_cache_prompt"],
                timeout=self.upstream_timeout,
            )
            oracle = None
            if plan["oracle_required"] or (
                plan["route"] == "certified_cache" and not valid_call(first)
            ):
                oracle = call_worker(
                    origin,
                    payload,
                    cache_prompt=False,
                    timeout=self.upstream_timeout,
                )
            try:
                completed = controller.complete(plan, first, oracle)
            finally:
                self.certificate_store.save(session_digest, controller)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        served = completed["served_call"]
        response = served.get("raw_response")
        if not isinstance(response, dict):
            self._record_error(elapsed_ms)
            raise GatewayError(
                HTTPStatus.BAD_GATEWAY, "worker returned no valid JSON response"
            )
        self._record(completed, first, oracle, elapsed_ms)
        headers = {
            "X-Pareto64-Route": completed["route"],
            "X-Pareto64-Admission": completed["admission"],
            "X-Pareto64-Served-Source": completed["served_source"],
            "X-Pareto64-Worker": str(worker_index + 1),
            "X-Pareto64-Transition": completed["transition_sha256"],
        }
        return response, headers

    def _record(
        self,
        completed: dict[str, Any],
        first: dict[str, Any],
        oracle: dict[str, Any] | None,
        elapsed_ms: float,
    ) -> None:
        cached_tokens = first.get("cached_tokens")
        with self.metrics_lock:
            self.request_count += 1
            self.route_counts[completed["route"]] += 1
            self.source_counts[completed["served_source"]] += 1
            self.admission_counts[completed["admission"]] += 1
            self.oracle_calls += int(oracle is not None)
            if type(cached_tokens) is int:
                self.cached_tokens += cached_tokens
            self.latencies_ms.append(elapsed_ms)

    def _record_error(self, elapsed_ms: float) -> None:
        with self.metrics_lock:
            self.request_count += 1
            self.error_count += 1
            self.latencies_ms.append(elapsed_ms)

    def metrics(self) -> dict[str, Any]:
        with self.metrics_lock:
            latencies = sorted(self.latencies_ms)
            runtime = {
                "uptime_ms": (time.monotonic_ns() - self.started_ns) / 1_000_000,
                "requests": self.request_count,
                "errors": self.error_count,
                "route_counts": dict(sorted(self.route_counts.items())),
                "served_source_counts": dict(sorted(self.source_counts.items())),
                "admission_counts": dict(sorted(self.admission_counts.items())),
                "oracle_calls": self.oracle_calls,
                "cached_tokens": self.cached_tokens,
                "latency_ms": {
                    "p50": percentile(latencies, 0.50),
                    "p95": percentile(latencies, 0.95),
                    "maximum": max(latencies) if latencies else 0.0,
                    "window": len(latencies),
                },
            }
        return {
            "schema_version": 1,
            "service": "Pareto64 certificate gateway",
            "workers": len(self.worker_origins),
            "runtime": runtime,
            "registry": self.certificate_store.counts(),
            "policy": {
                "unknown": "cached shadow plus uncached oracle; oracle served",
                "certified": "cached route with periodic oracle revalidation",
                "denied": "uncached route",
                "revalidate_every": self.certificate_store.revalidate_every,
                "minimum_cached_tokens": self.certificate_store.minimum_cached_tokens,
            },
        }


def call_worker(
    origin: str,
    payload: dict[str, Any],
    *,
    cache_prompt: bool,
    timeout: float,
) -> dict[str, Any]:
    request_payload = {**payload, "cache_prompt": cache_prompt}
    request = urllib.request.Request(
        f"{origin}/v1/chat/completions",
        data=canonical_bytes(request_payload),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter_ns()
    status: int | None = None
    response: dict[str, Any] | None = None
    error: str | None = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as opened:
            status = opened.status
            decoded = json.loads(opened.read())
            if isinstance(decoded, dict):
                response = decoded
            else:
                error = "worker response is not a JSON object"
    except urllib.error.HTTPError as http_error:
        status = http_error.code
        error = f"HTTPError: {http_error.code}"
    except Exception as call_error:  # noqa: BLE001
        error = f"{type(call_error).__name__}: {call_error}"
    choice: dict[str, Any] = {}
    message: dict[str, Any] = {}
    timings: dict[str, Any] = {}
    usage: dict[str, Any] = {}
    if response is not None:
        choices = response.get("choices")
        if (
            isinstance(choices, list)
            and len(choices) == 1
            and isinstance(choices[0], dict)
        ):
            choice = choices[0]
        if isinstance(choice.get("message"), dict):
            message = choice["message"]
        if isinstance(response.get("timings"), dict):
            timings = response["timings"]
        if isinstance(response.get("usage"), dict):
            usage = response["usage"]
    prompt_details = usage.get("prompt_tokens_details")
    if not isinstance(prompt_details, dict):
        prompt_details = {}
    generated_tokens = timings.get("predicted_n", usage.get("completion_tokens"))
    cached_tokens = timings.get("cache_n", prompt_details.get("cached_tokens"))
    return {
        "http_status": status,
        "error": error,
        "response": message.get("content"),
        "stop_type": choice.get("finish_reason"),
        "generated_tokens": generated_tokens,
        "cached_tokens": cached_tokens,
        "cache_prompt": cache_prompt,
        "http_ms": (time.perf_counter_ns() - started) / 1_000_000,
        "raw_response": response,
    }


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int((len(values) - 1) * fraction)))
    return values[index]


class GatewayHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: GatewayState):
        self.state = state
        super().__init__(address, GatewayHandler)


class GatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: GatewayHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json_response(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        body = canonical_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _read_payload(self) -> dict[str, Any]:
        if self.headers.get_content_type() != "application/json":
            raise GatewayError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "expected application/json"
            )
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise GatewayError(HTTPStatus.LENGTH_REQUIRED, "Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise GatewayError(
                HTTPStatus.BAD_REQUEST, "invalid Content-Length"
            ) from error
        if not 0 <= length <= MAX_REQUEST_BYTES:
            raise GatewayError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request is too large"
            )
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GatewayError(HTTPStatus.BAD_REQUEST, "invalid JSON") from error
        if not isinstance(value, dict):
            raise GatewayError(HTTPStatus.BAD_REQUEST, "request must be a JSON object")
        return value

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json_response(
                HTTPStatus.OK,
                {
                    "schema_version": 1,
                    "status": "ok",
                    "service": "Pareto64 certificate gateway",
                    "workers": len(self.server.state.worker_origins),
                },
            )
            return
        if self.path == "/metrics":
            self._json_response(HTTPStatus.OK, self.server.state.metrics())
            return
        self._json_response(
            HTTPStatus.NOT_FOUND,
            {"error": "Not Found", "detail": "route not found"},
        )

    def do_POST(self) -> None:
        try:
            if self.path != "/v1/chat/completions":
                raise GatewayError(HTTPStatus.NOT_FOUND, "route not found")
            session_id = self.headers.get(SESSION_HEADER)
            if session_id is None:
                raise GatewayError(
                    HTTPStatus.BAD_REQUEST,
                    f"{SESSION_HEADER} is required for cache isolation",
                )
            response, headers = self.server.state.route(
                session_id, self._read_payload()
            )
            self._json_response(HTTPStatus.OK, response, headers)
        except GatewayError as error:
            self.server.state._record_error(0.0)
            self._json_response(
                error.status,
                {"error": error.status.phrase, "detail": error.detail},
            )
        except ValueError as error:
            self.server.state._record_error(0.0)
            self._json_response(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                {"error": "Unprocessable Entity", "detail": str(error)},
            )
        except Exception as error:  # noqa: BLE001
            self.server.state._record_error(0.0)
            self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {"error": "Bad Gateway", "detail": f"{type(error).__name__}: {error}"},
            )


class GatewayError(Exception):
    def __init__(self, status: HTTPStatus, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def serve_gateway(
    *,
    host: str,
    port: int,
    worker_origins: tuple[str, ...],
    registry_path: Path,
    identity: dict[str, Any],
    minimum_cached_tokens: int,
    revalidate_every: int,
    upstream_timeout: float = 120.0,
) -> None:
    store = CertificateStore(
        registry_path,
        identity,
        minimum_cached_tokens=minimum_cached_tokens,
        revalidate_every=revalidate_every,
    )
    state = GatewayState(worker_origins, store, upstream_timeout=upstream_timeout)
    server = GatewayHTTPServer((host, port), state)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
