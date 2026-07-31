from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from typing import Any

from .planner import build_plan, load_object


MAX_REQUEST_BYTES = 64 * 1024


@dataclass
class PlannerState:
    manifest: dict[str, Any]
    default_constraints: dict[str, Any]
    default_plan: dict[str, Any]
    manifest_path: Path
    constraints_path: Path
    started_ns: int = field(default_factory=time.monotonic_ns)
    request_count: int = 0
    error_count: int = 0
    status_counts: Counter[int] = field(default_factory=Counter)
    total_duration_ns: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def from_paths(cls, manifest_path: Path, constraints_path: Path) -> "PlannerState":
        manifest = load_object(manifest_path)
        constraints = load_object(constraints_path)
        plan = build_plan(
            manifest,
            constraints,
            manifest_path=manifest_path,
            constraints_path=constraints_path,
        )
        return cls(manifest, constraints, plan, manifest_path, constraints_path)

    def evaluate(self, constraints: dict[str, Any]) -> dict[str, Any]:
        return build_plan(
            self.manifest,
            constraints,
            manifest_path=self.manifest_path,
        )

    def record(self, status: int, duration_ns: int) -> int:
        with self.lock:
            self.request_count += 1
            self.status_counts[status] += 1
            self.total_duration_ns += duration_ns
            if status >= 400:
                self.error_count += 1
            return self.request_count

    def metrics(self) -> dict[str, Any]:
        with self.lock:
            requests = self.request_count
            return {
                "schema_version": 1,
                "service": "Pareto64",
                "uptime_ms": (time.monotonic_ns() - self.started_ns) / 1_000_000,
                "requests": requests,
                "errors": self.error_count,
                "status_counts": {
                    str(status): count
                    for status, count in sorted(self.status_counts.items())
                },
                "mean_handler_ms": (
                    self.total_duration_ns / requests / 1_000_000
                    if requests
                    else 0.0
                ),
            }


class PlannerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self, address: tuple[str, int], state: PlannerState, max_requests: int = 0
    ):
        self.state = state
        self.max_requests = max_requests
        super().__init__(address, PlannerHandler)


class PlannerHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: PlannerHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_policy(self) -> dict[str, Any]:
        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            raise RequestError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "expected JSON")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise RequestError(HTTPStatus.LENGTH_REQUIRED, "Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid Content-Length") from error
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise RequestError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request is too large")
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid JSON") from error
        if not isinstance(value, dict):
            raise RequestError(HTTPStatus.BAD_REQUEST, "policy must be a JSON object")
        return value

    def _dispatch(self) -> HTTPStatus:
        if self.command == "GET" and self.path == "/healthz":
            self._json_response(
                HTTPStatus.OK,
                {
                    "schema_version": 1,
                    "service": "Pareto64",
                    "status": "ok",
                    "default_plan_status": self.server.state.default_plan["status"],
                },
            )
            return HTTPStatus.OK
        if self.command == "GET" and self.path == "/v1/plan":
            self._json_response(HTTPStatus.OK, self.server.state.default_plan)
            return HTTPStatus.OK
        if self.command == "POST" and self.path == "/v1/plan":
            try:
                result = self.server.state.evaluate(self._read_policy())
            except RequestError:
                raise
            except ValueError as error:
                raise RequestError(HTTPStatus.UNPROCESSABLE_ENTITY, str(error)) from error
            self._json_response(HTTPStatus.OK, result)
            return HTTPStatus.OK
        if self.command == "GET" and self.path == "/metrics":
            self._json_response(HTTPStatus.OK, self.server.state.metrics())
            return HTTPStatus.OK
        raise RequestError(HTTPStatus.NOT_FOUND, "route not found")

    def _handle(self) -> None:
        started = time.monotonic_ns()
        status = HTTPStatus.INTERNAL_SERVER_ERROR
        try:
            status = self._dispatch()
        except RequestError as error:
            status = error.status
            self._json_response(
                error.status,
                {
                    "schema_version": 1,
                    "error": error.status.phrase,
                    "detail": error.detail,
                },
            )
        except (BrokenPipeError, ConnectionResetError):
            status = HTTPStatus.BAD_REQUEST
        finally:
            request_count = self.server.state.record(
                int(status), time.monotonic_ns() - started
            )
            if self.server.max_requests and request_count >= self.server.max_requests:
                threading.Thread(target=self.server.shutdown, daemon=True).start()

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()


class RequestError(Exception):
    def __init__(self, status: HTTPStatus, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail
