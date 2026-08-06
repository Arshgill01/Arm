from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from pareto64.certificate import CertificateStore
from pareto64.gateway import GatewayHTTPServer, GatewayState

IDENTITY = {
    "model_sha256": "1" * 64,
    "server_sha256": "2" * 64,
    "source_diff_sha256": "3" * 64,
    "service_sha256": "4" * 64,
}


class WorkerHandler(BaseHTTPRequestHandler):
    calls: ClassVar[list[dict[str, object]]] = []
    drift = False

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        self.calls.append(payload)
        content = payload["messages"][-1]["content"]
        if self.drift and payload["cache_prompt"] and content == "B":
            content = "drift"
        body = json.dumps(
            {
                "choices": [
                    {
                        "message": {"content": content},
                        "finish_reason": "stop",
                    }
                ],
                "timings": {
                    "predicted_n": 1,
                    "cache_n": 16 if payload["cache_prompt"] else 0,
                },
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def post(origin: str, session: str, content: str):
    payload = json.dumps(
        {"messages": [{"role": "user", "content": content}], "stream": False}
    ).encode()
    request = urllib.request.Request(
        f"{origin}/v1/chat/completions",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Pareto64-Session-ID": session,
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read()), dict(response.headers)


class GatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        WorkerHandler.calls = []
        WorkerHandler.drift = False
        self.worker = ThreadingHTTPServer(("127.0.0.1", 0), WorkerHandler)
        self.worker_thread = threading.Thread(
            target=self.worker.serve_forever, daemon=True
        )
        self.worker_thread.start()
        self.temporary = tempfile.TemporaryDirectory()
        store = CertificateStore(
            Path(self.temporary.name) / "certificates.json",
            IDENTITY,
            minimum_cached_tokens=8,
            revalidate_every=1,
        )
        worker_origin = f"http://127.0.0.1:{self.worker.server_port}"
        self.state = GatewayState((worker_origin,), store, upstream_timeout=2.0)
        self.gateway = GatewayHTTPServer(("127.0.0.1", 0), self.state)
        self.gateway_thread = threading.Thread(
            target=self.gateway.serve_forever, daemon=True
        )
        self.gateway_thread.start()
        self.origin = f"http://127.0.0.1:{self.gateway.server_port}"

    def tearDown(self) -> None:
        self.gateway.shutdown()
        self.gateway.server_close()
        self.worker.shutdown()
        self.worker.server_close()
        self.temporary.cleanup()

    def establish_cycle(self) -> None:
        post(self.origin, "session-a", "A")
        post(self.origin, "session-a", "B")
        post(self.origin, "session-a", "A")

    def test_unknown_oracle_then_certified_route_is_visible(self) -> None:
        self.establish_cycle()
        response, headers = post(self.origin, "session-a", "B")
        self.assertEqual("B", response["choices"][0]["message"]["content"])
        self.assertEqual("certified_cache", headers["X-Pareto64-Route"])
        self.assertEqual("certified_cache", headers["X-Pareto64-Served-Source"])
        metrics = self.state.metrics()
        self.assertEqual(4, metrics["runtime"]["requests"])
        self.assertGreaterEqual(metrics["runtime"]["oracle_calls"], 3)
        self.assertGreaterEqual(metrics["registry"]["certified_transitions"], 2)

    def test_revalidation_revokes_drift_and_never_serves_it(self) -> None:
        self.establish_cycle()
        post(self.origin, "session-a", "B")
        post(self.origin, "session-a", "A")
        WorkerHandler.drift = True
        response, headers = post(self.origin, "session-a", "B")
        self.assertEqual("B", response["choices"][0]["message"]["content"])
        self.assertEqual("certified_revalidation", headers["X-Pareto64-Route"])
        self.assertEqual("revoked", headers["X-Pareto64-Admission"])
        self.assertEqual("revalidation_oracle", headers["X-Pareto64-Served-Source"])

    def test_session_state_is_isolated(self) -> None:
        self.establish_cycle()
        _, headers = post(self.origin, "session-b", "B")
        self.assertEqual("unknown_shadow_then_oracle", headers["X-Pareto64-Route"])
        self.assertEqual(2, self.state.metrics()["registry"]["sessions"])


if __name__ == "__main__":
    unittest.main()
