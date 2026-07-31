from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from experiments.e5b_inference_probe import request_case


class ProbeHandler(BaseHTTPRequestHandler):
    payload: dict = {}

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        type(self).payload = json.loads(self.rfile.read(length))
        body = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "A"},
                    }
                ],
                "timings": {
                    "cache_n": 24,
                    "prompt_n": 80,
                    "prompt_ms": 12.5,
                    "predicted_n": 1,
                    "predicted_ms": 2.5,
                },
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class E5bInferenceProbeTests(unittest.TestCase):
    def test_request_binds_cache_mode_and_captures_token_reuse(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            host, port = server.server_address
            case = request_case(
                f"http://{host}:{port}",
                0,
                {
                    "id": "arithmetic-01",
                    "category": "arithmetic",
                    "prompt": "Question",
                    "answer": "A",
                },
                "Return A-D",
                "selected",
                "A",
                8,
                424242,
                5.0,
                True,
            )
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertIs(ProbeHandler.payload["cache_prompt"], True)
        self.assertEqual(24, case["cached_tokens"])
        self.assertEqual(80, case["evaluated_prompt_tokens"])
        self.assertEqual("A", case["predicted"])
        self.assertTrue(case["reference_match"])


if __name__ == "__main__":
    unittest.main()
