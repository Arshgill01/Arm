from __future__ import annotations

import http.client
import json
from pathlib import Path
import threading
import unittest

from pareto64.server import PlannerHTTPServer, PlannerState


ROOT = Path(__file__).resolve().parents[1]


class Pareto64ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        state = PlannerState.from_paths(
            ROOT / "results/manifests/e3-30635472160.json",
            ROOT / "configs/cloud-balanced.json",
        )
        cls.server = PlannerHTTPServer(("127.0.0.1", 0), state)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def request(
        self, method: str, path: str, body: bytes | None = None, content_type: str | None = None
    ) -> tuple[int, dict]:
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def test_health_and_default_plan(self) -> None:
        status, health = self.request("GET", "/healthz")
        self.assertEqual(200, status)
        self.assertEqual("no_feasible_candidate", health["default_plan_status"])
        status, plan = self.request("GET", "/v1/plan")
        self.assertEqual(200, status)
        self.assertEqual("no_feasible_candidate", plan["status"])
        self.assertIsNone(plan["selected"])

    def test_posted_policy_and_invalid_policy(self) -> None:
        policy = (ROOT / "configs/cloud-balanced.json").read_bytes()
        status, plan = self.request("POST", "/v1/plan", policy, "application/json")
        self.assertEqual(200, status)
        self.assertEqual("no_feasible_candidate", plan["status"])
        status, error = self.request(
            "POST", "/v1/plan", b'{"schema_version": 99}', "application/json"
        )
        self.assertEqual(422, status)
        self.assertIn("constraint schema", error["detail"])

    def test_unknown_route_and_metrics(self) -> None:
        status, error = self.request("GET", "/missing")
        self.assertEqual(404, status)
        self.assertEqual("route not found", error["detail"])
        status, metrics = self.request("GET", "/metrics")
        self.assertEqual(200, status)
        self.assertGreater(metrics["requests"], 0)
        self.assertGreater(metrics["errors"], 0)

    def test_bounded_server_stops_after_configured_request_count(self) -> None:
        state = PlannerState.from_paths(
            ROOT / "results/manifests/e3-30635472160.json",
            ROOT / "configs/cloud-balanced.json",
        )
        server = PlannerHTTPServer(("127.0.0.1", 0), state, max_requests=1)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        connection.request("GET", "/healthz")
        response = connection.getresponse()
        self.assertEqual(200, response.status)
        response.read()
        connection.close()
        thread.join(timeout=5)
        server.server_close()
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
