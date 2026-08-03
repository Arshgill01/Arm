import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from experiments.e10d_ingest import compare_models
from experiments.e10d_prepare import move_context_spaces, prepare_request
from experiments.e10d_probe import argmax, score_candidate, score_sample


class FakeTokenizer:
    @staticmethod
    def encode(text: str, add_special_tokens: bool = False) -> list[int]:
        assert not add_special_tokens
        return [ord(character) for character in text]


class SelectedProbabilityHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(request)
        target = request["probability_ids"][0]
        cache_n = 0 if not request["cache_prompt"] else len(request["prompt"]) - 1
        response = json.dumps(
            {
                "content": str(target),
                "tokens": [target],
                "completion_probabilities": [
                    {
                        "id": target,
                        "selected_logprobs": [
                            {"id": target, "logprob": -float(target) / 10.0}
                        ],
                    }
                ],
                "timings": {
                    "cache_n": cache_n,
                    "prompt_ms": 2.0,
                    "predicted_ms": 1.0,
                },
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


class E10dPreparationTests(unittest.TestCase):
    def test_context_spaces_move_to_continuation(self) -> None:
        self.assertEqual(
            move_context_spaces("question  ", "answer"), ("question", "  answer")
        )

    def test_prepare_request_matches_harness_left_truncation(self) -> None:
        tokenizer = FakeTokenizer()
        result = prepare_request(
            context="abcd ",
            continuation="ef",
            choice_index=0,
            tokenizer=tokenizer,
            tokenize=lambda text: tokenizer.encode(text),
            max_length=5,
        )
        self.assertEqual(result["left_truncated_tokens"], 2)
        self.assertEqual(result["prompt_tokens"], [ord("c"), ord("d")])
        self.assertEqual(result["candidate_tokens"], [ord(" "), ord("e"), ord("f")])
        self.assertEqual(result["input_tokens"], 5)


class E10dProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HTTPServer(("127.0.0.1", 0), SelectedProbabilityHandler)
        self.server.requests = []
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def test_argmax_uses_first_index_for_ties(self) -> None:
        self.assertEqual(argmax([-1.0, -1.0, -2.0]), 0)

    def test_candidate_starts_clean_then_reuses_only_its_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = score_candidate(
                base_url=self.base_url,
                prompt_tokens=[1, 2],
                candidate_tokens=[10, 20, 30],
                seed=7,
                timeout=1.0,
                raw_dir=Path(directory),
                raw_prefix="case",
            )
        self.assertEqual(result["token_logprobs"], [-1.0, -2.0, -3.0])
        self.assertEqual(result["sum_logprob"], -6.0)
        self.assertEqual(result["cached_tokens"], [0, 2, 3])
        self.assertEqual(len(result["raw_responses"]), 3)
        self.assertEqual(
            [request["cache_prompt"] for request in self.server.requests],
            [False, True, True],
        )
        self.assertEqual(
            [request["prompt"] for request in self.server.requests],
            [[1, 2], [1, 2, 10], [1, 2, 10, 20]],
        )

    def test_sample_scores_every_choice_independently(self) -> None:
        sample = {
            "sample_ordinal": 0,
            "source_index": 7,
            "source_document_sha256": "a" * 64,
            "gold_index": 0,
            "choice_text_lengths": [3, 4],
            "requests": [
                {
                    "choice_index": 0,
                    "prompt_tokens": [1, 2],
                    "prompt_sha256": "b" * 64,
                    "candidate_tokens": [10],
                    "candidate_sha256": "c" * 64,
                },
                {
                    "choice_index": 1,
                    "prompt_tokens": [1, 2],
                    "prompt_sha256": "b" * 64,
                    "candidate_tokens": [20],
                    "candidate_sha256": "d" * 64,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            result = score_sample(
                base_url=self.base_url,
                task_name="task",
                sample=sample,
                seed=7,
                timeout=1.0,
                raw_dir=Path(directory),
            )
        self.assertIsNone(result["error"])
        self.assertEqual(result["choice_sum_logprobs"], [-1.0, -2.0])
        self.assertEqual(result["prediction"], 0)
        self.assertEqual(
            [request["cache_prompt"] for request in self.server.requests],
            [False, False],
        )


class E10dIngestTests(unittest.TestCase):
    def test_model_comparison_reports_metric_delta_and_agreement(self) -> None:
        primary = {
            "metrics": {"task": {"acc": 0.75}},
            "tasks": [
                {
                    "task": "task",
                    "samples": [
                        {"source_index": 1, "prediction": 0, "prediction_norm": 0},
                        {"source_index": 2, "prediction": 1, "prediction_norm": 1},
                    ],
                }
            ],
        }
        control = {
            "metrics": {"task": {"acc": 0.5}},
            "tasks": [
                {
                    "task": "task",
                    "samples": [
                        {"source_index": 1, "prediction": 0, "prediction_norm": 0},
                        {"source_index": 2, "prediction": 0, "prediction_norm": 1},
                    ],
                }
            ],
        }
        result = compare_models([primary, control])
        self.assertEqual(
            result["primary_minus_control_metric_deltas"]["task"]["acc"], 0.25
        )
        self.assertEqual(result["paired_prediction_agreement"], 0.5)
        self.assertEqual(result["paired_normalized_prediction_agreement"], 1.0)


if __name__ == "__main__":
    unittest.main()
