import gzip
import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from experiments.e10c_ingest import scorer_server_argv, validate_raw
from experiments.e10c_probe import forked_scores, prediction, retain_raw

ROOT = Path(__file__).resolve().parents[1]


class ScoreHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.request_body = body
        response = json.dumps(
            {
                "object": "candidate_scores",
                "score_semantics": "raw_pre_sampling_logprob",
                "shared_prompt": True,
                "prompt_tokens_cached": 0,
                "selected_index": 1,
                "request_ms": 1.5,
                "candidates": [
                    {
                        "index": 0,
                        "content": "A",
                        "tokens": [10],
                        "token_logprobs": [{"id": 10, "logprob": -2.0}],
                        "sum_logprob": -2.0,
                        "timings": {
                            "prompt_ms": 4.0,
                            "predicted_ms": 1.0,
                            "cache_n": 0,
                        },
                    },
                    {
                        "index": 1,
                        "content": "B",
                        "tokens": [20],
                        "token_logprobs": [{"id": 20, "logprob": -1.0}],
                        "sum_logprob": -1.0,
                        "timings": {
                            "prompt_ms": 4.0,
                            "predicted_ms": 1.0,
                            "cache_n": 0,
                        },
                    },
                ],
            },
            separators=(",", ":"),
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: object) -> None:
        pass


class E10cProbeTests(unittest.TestCase):
    def test_prediction_uses_request_order_for_exact_ties(self) -> None:
        self.assertEqual(prediction([-1.0, -1.0], ["A", "B"]), (0, "A"))

    def test_forked_scores_preserves_exact_candidate_order_and_raw_response(
        self,
    ) -> None:
        server = HTTPServer(("127.0.0.1", 0), ScoreHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                cell_dir = Path(directory)
                raw_dir = cell_dir / "raw"
                result = forked_scores(
                    f"http://127.0.0.1:{server.server_port}",
                    prompt_tokens=[1, 2, 3],
                    candidates=[[10], [20]],
                    timeout=1.0,
                    raw_dir=raw_dir,
                    raw_prefix="case",
                )
                self.assertEqual(result["candidate_contents"], ["A", "B"])
                self.assertEqual(result["candidate_sum_logprobs"], [-2.0, -1.0])
                self.assertEqual(result["selected_index"], 1)
                self.assertEqual(result["prompt_evaluations"], 1)
                validate_raw(cell_dir, result["raw_responses"][0])
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(server.request_body["candidates"], [[10], [20]])
        self.assertFalse(server.request_body["cache_prompt"])

    def test_raw_retention_is_deterministic(self) -> None:
        raw = b'{"candidate":1}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw" / "response.json.gz"
            record = retain_raw(path, raw)
            compressed = path.read_bytes()
        self.assertEqual(gzip.decompress(compressed), raw)
        self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(record["gzip_sha256"], hashlib.sha256(compressed).hexdigest())


class E10cIngestTests(unittest.TestCase):
    def test_contract_freezes_native_candidate_scorer_gates(self) -> None:
        contract = json.loads((ROOT / "experiments/e10c_contract.json").read_text())
        self.assertEqual(contract["experiment_id"], "E10c")
        self.assertEqual(
            contract["workload"]["candidate_token_ids"], [1065, 1066, 1067, 1068]
        )
        self.assertEqual(
            contract["execution"]["cell_order"],
            [
                {"mode": "serial", "repetition": 1},
                {"mode": "forked", "repetition": 1},
                {"mode": "forked", "repetition": 2},
                {"mode": "serial", "repetition": 2},
            ],
        )
        self.assertIsNone(contract["acceptance"]["minimum_accuracy"])
        self.assertEqual(
            contract["acceptance"]["maximum_forked_to_serial_median_cpu_ratio"],
            0.7,
        )

    def test_scorer_recipe_changes_only_context_and_slot_count(self) -> None:
        argv = scorer_server_argv("/tmp/server", "/tmp/model", "ministral3_3b_q4_k_m")
        self.assertEqual(argv[argv.index("--ctx-size") + 1], "1024")
        self.assertEqual(argv[argv.index("--parallel") + 1], "4")
        self.assertIn("--metrics", argv)
        self.assertIn("--slots", argv)


if __name__ == "__main__":
    unittest.main()
