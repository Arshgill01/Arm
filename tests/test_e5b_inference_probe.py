from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from experiments.e5b_inference_probe import (
    parse_process_stat,
    read_process_cpu,
    request_case,
    summarize_process_cpu,
)


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
    def test_process_cpu_interval_excludes_load_and_warmup_counters(self) -> None:
        before = parse_process_stat(
            "812 (llama server (arm)) S 1 2 3 4 5 6 7 8 9 10 1250 250 0 0"
        )
        after = parse_process_stat(
            "812 (llama server (arm)) S 1 2 3 4 5 6 7 8 9 10 1370 280 0 0"
        )
        result = summarize_process_cpu(
            before,
            after,
            clock_ticks_per_second=100,
            measured_requests=30,
            elapsed_seconds=1.0,
        )
        self.assertEqual(150, result["total_ticks"])
        self.assertEqual(1.5, result["total_seconds"])
        self.assertEqual(0.05, result["seconds_per_request"])
        self.assertEqual(1.5, result["average_cores_used"])

    def test_process_stat_reader_binds_requested_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc = Path(temporary)
            stat = proc / "812" / "stat"
            stat.parent.mkdir()
            stat.write_text(
                "812 (server) S 1 2 3 4 5 6 7 8 9 10 1250 250 0 0"
            )
            self.assertEqual(1500, read_process_cpu(812, proc)["total_ticks"])
            stat.write_text("999 (server) S 1 2 3 4 5 6 7 8 9 10 1 2")
            with self.assertRaisesRegex(ValueError, "PID differs"):
                read_process_cpu(812, proc)

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
                1,
            )
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertIs(ProbeHandler.payload["cache_prompt"], True)
        self.assertEqual(1, ProbeHandler.payload["id_slot"])
        self.assertEqual(24, case["cached_tokens"])
        self.assertEqual(80, case["evaluated_prompt_tokens"])
        self.assertEqual("A", case["predicted"])
        self.assertTrue(case["reference_match"])


if __name__ == "__main__":
    unittest.main()
