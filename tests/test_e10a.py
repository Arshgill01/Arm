from __future__ import annotations

import json
import math
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from experiments.e10a_ingest import (
    jensen_shannon,
    pair_metrics,
    separation_summary,
)
from experiments.e10a_probe import (
    extract_candidate_distribution,
    request_candidate_scores,
)


class ProbabilityHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path != "/completion":
            self.send_error(404)
            return
        if (
            payload.get("grammar") != "root ::= [ABCD]"
            or payload.get("post_sampling_probs") is not True
            or payload.get("return_tokens") is not True
        ):
            self.send_error(400)
            return
        body = json.dumps(
            {
                "content": "B",
                "tokens": [100],
                "stop_type": "limit",
                "tokens_cached": 8,
                "tokens_evaluated": 3,
                "timings": {
                    "cache_n": 7,
                    "prompt_n": 3,
                    "prompt_ms": 12.0,
                    "predicted_n": 1,
                    "predicted_ms": 3.0,
                },
                "completion_probabilities": [
                    {
                        "id": 100,
                        "token": "B",
                        "prob": 0.2,
                        "top_probs": [
                            {"id": 99, "token": "A", "bytes": [65], "prob": 0.6},
                            {"id": 100, "token": "B", "bytes": [66], "prob": 0.2},
                            {"id": 101, "token": "C", "bytes": [67], "prob": 0.15},
                            {"id": 102, "token": "D", "bytes": [68], "prob": 0.05},
                        ],
                    }
                ],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def make_pair(
    *,
    prompt: str,
    off_prediction: str,
    on_prediction: str,
    on_margin: float,
    js_shift: float,
) -> dict:
    off = {"A": 0.7, "B": 0.1, "C": 0.1, "D": 0.1}
    on = {
        "A": 0.25 + js_shift,
        "B": 0.25 + on_margin,
        "C": 0.25 - on_margin,
        "D": 0.25 - js_shift,
    }
    off_ranking = [
        {"candidate": candidate, "probability": probability}
        for candidate, probability in sorted(
            off.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    on_ranking = [
        {"candidate": candidate, "probability": probability}
        for candidate, probability in sorted(
            on.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    return {
        "index": 0,
        "task_id": "task",
        "prefix_marker": "alpha",
        "prompt_sha256": prompt,
        "cache_off_prediction": off_prediction,
        "cache_on_prediction": on_prediction,
        "semantic_drift": off_prediction != on_prediction,
        "cache_off_reference_match": True,
        "cache_on_reference_match": off_prediction == on_prediction,
        "cache_off_top1_margin": 0.6,
        "cache_on_top1_margin": on_margin,
        "jensen_shannon_nats": jensen_shannon(off, on),
        "maximum_absolute_probability_delta": max(
            abs(off[key] - on[key]) for key in off
        ),
        "top2_set_overlap": len(
            {item["candidate"] for item in off_ranking[:2]}
            & {item["candidate"] for item in on_ranking[:2]}
        )
        / len(
            {item["candidate"] for item in off_ranking[:2]}
            | {item["candidate"] for item in on_ranking[:2]}
        ),
        "cache_off_candidate_probabilities": off,
        "cache_on_candidate_probabilities": on,
        "prefix_cardinality": 1,
        "shared_prefix_tokens": 64,
        "repetition": 1,
    }


class E10aProbeTests(unittest.TestCase):
    def test_extract_candidate_distribution_aggregates_duplicate_tokens(self) -> None:
        response = {
            "completion_probabilities": [
                {
                    "top_probs": [
                        {"bytes": [65], "prob": 0.4},
                        {"bytes": [65], "prob": 0.1},
                        {"bytes": [66], "prob": 0.2},
                        {"bytes": [67], "prob": 0.2},
                        {"bytes": [68], "prob": 0.1},
                    ]
                }
            ]
        }
        self.assertEqual(
            {"A": 0.5, "B": 0.2, "C": 0.2, "D": 0.1},
            extract_candidate_distribution(response),
        )

    def test_extract_candidate_distribution_rejects_grammar_leak(self) -> None:
        response = {
            "completion_probabilities": [
                {
                    "top_probs": [
                        {"bytes": [65], "prob": 0.4},
                        {"bytes": [66], "prob": 0.2},
                        {"bytes": [67], "prob": 0.2},
                        {"bytes": [68], "prob": 0.1},
                        {"bytes": [69], "prob": 0.1},
                    ]
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "grammar leaked"):
            extract_candidate_distribution(response)

    def test_request_uses_top_probability_not_emitted_sample(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), ProbabilityHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            case = request_candidate_scores(
                f"http://127.0.0.1:{server.server_port}",
                index=0,
                task={"id": "task"},
                marker="alpha",
                marker_index=0,
                prompt_tokens=[1, 2, 3],
                reference="A",
                cache_prompt=True,
                scoring={
                    "maximum_output_tokens": 1,
                    "temperature": 1.0,
                    "samplers": ["temperature"],
                    "grammar": "root ::= [ABCD]",
                    "n_probs": 32,
                },
                seed=424242,
                timeout=1.0,
            )
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual("B", case["sampled_prediction"])
        self.assertEqual("A", case["prediction"])
        self.assertAlmostEqual(0.4, case["top1_margin"])
        self.assertTrue(case["reference_match"])

    def test_probe_supports_direct_workflow_entrypoint(self) -> None:
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, str(root / "experiments/e10a_probe.py"), "--help"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


class E10aIngestTests(unittest.TestCase):
    def test_jensen_shannon_is_symmetric_and_zero_for_identity(self) -> None:
        left = {"A": 0.7, "B": 0.1, "C": 0.1, "D": 0.1}
        right = {"A": 0.1, "B": 0.7, "C": 0.1, "D": 0.1}
        self.assertEqual(0.0, jensen_shannon(left, left))
        self.assertTrue(
            math.isclose(
                jensen_shannon(left, right),
                jensen_shannon(right, left),
                rel_tol=1e-12,
            )
        )

    def test_pair_metrics_rejects_token_mismatch(self) -> None:
        base = {
            "index": 0,
            "task_id": "task",
            "prefix_marker": "alpha",
            "prediction": "A",
            "reference_match": True,
            "top1_margin": 0.2,
            "candidate_probabilities": {
                "A": 0.5,
                "B": 0.3,
                "C": 0.1,
                "D": 0.1,
            },
            "candidate_ranking": [
                {"candidate": "A", "probability": 0.5},
                {"candidate": "B", "probability": 0.3},
                {"candidate": "C", "probability": 0.1},
                {"candidate": "D", "probability": 0.1},
            ],
        }
        with self.assertRaisesRegex(ValueError, "different prompt tokens"):
            pair_metrics(
                {**base, "prompt_sha256": "a" * 64},
                {**base, "prompt_sha256": "b" * 64},
            )

    def test_margin_separation_requires_strict_gap_and_stable_repeats(self) -> None:
        pairs = [
            make_pair(
                prompt="a" * 64,
                off_prediction="A",
                on_prediction="B",
                on_margin=0.01,
                js_shift=0.02,
            ),
            make_pair(
                prompt="a" * 64,
                off_prediction="A",
                on_prediction="B",
                on_margin=0.02,
                js_shift=0.02,
            ),
            make_pair(
                prompt="b" * 64,
                off_prediction="A",
                on_prediction="A",
                on_margin=0.20,
                js_shift=0.02,
            ),
        ]
        summary = separation_summary(pairs)
        self.assertTrue(summary["cached_top1_margin_separable"])
        self.assertTrue(summary["repeated_drift_labels_stable"])
        self.assertEqual(2, summary["semantic_drift_pairs"])

        pairs[2]["cache_on_top1_margin"] = 0.02
        self.assertFalse(separation_summary(pairs)["cached_top1_margin_separable"])

        pairs[2]["prompt_sha256"] = "a" * 64
        self.assertFalse(separation_summary(pairs)["repeated_drift_labels_stable"])


if __name__ == "__main__":
    unittest.main()
