import json
import tempfile
import unittest
from pathlib import Path

from experiments.e21b_openai_probe import openai_request_payload
from experiments.e21b_preflight_fixture import run_synthetic_replay
from experiments.e21b_preflight_freeze import build_contract
from experiments.e21b_preflight_ingest import recompute_counts


class E21bPreflightTests(unittest.TestCase):
    def test_openai_request_matches_frozen_quality_shape(self) -> None:
        task = {"id": "example", "prompt": "Choose one."}
        self.assertEqual(
            openai_request_payload(
                candidate="model",
                instruction="Return A, B, C, or D.",
                task=task,
                cache_prompt=True,
                maximum_output_tokens=8,
                seed=424242,
            ),
            {
                "model": "model",
                "messages": [
                    {"role": "system", "content": "Return A, B, C, or D."},
                    {"role": "user", "content": "Choose one."},
                ],
                "temperature": 0.0,
                "seed": 424242,
                "max_tokens": 8,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
                "cache_prompt": True,
            },
        )

    def test_contract_uses_full_quality_and_adaptive_safety_bounds(self) -> None:
        contract = build_contract(Path(".").resolve())
        self.assertEqual(contract["client"]["api_path"], "/v1/chat/completions")
        self.assertEqual(contract["workload"]["unique_prompts"], 30)
        self.assertEqual(contract["workload"]["served_requests"], 60)
        self.assertEqual(contract["workload"]["correct_per_cycle"], 23)
        self.assertEqual(contract["acceptance"]["minimum_certified_transitions"], 24)
        self.assertEqual(contract["acceptance"]["maximum_denied_transitions"], 7)
        self.assertNotIn("online_route_counts", contract["acceptance"])
        self.assertEqual(
            contract["readiness"]["evaluation"]["decision"],
            "await_native_preflight",
        )

    def test_complete_synthetic_preflight_replay_is_byte_stable(self) -> None:
        root = Path(".").resolve()
        contract = build_contract(root)
        summary, replay = run_synthetic_replay(contract, root)
        self.assertEqual(summary["status"], "valid_openai_online_certificate_preflight")
        self.assertTrue(all(summary["gates"].values()))
        self.assertEqual(summary["quality"]["task_score_per_cycle"], "23/30")
        self.assertEqual(summary["online_decisions"]["certified_transitions"], 30)
        self.assertEqual(summary["online_decisions"]["denied_transitions"], 1)
        self.assertTrue(replay["byte_stable"])
        self.assertEqual(replay["served_requests"], 120)

    def test_recomputed_summary_rejects_untruthful_counts(self) -> None:
        probe = {
            "served_records": [],
            "raw_calls": [],
            "result": {
                "served_requests": 1,
                "actual_http_calls": 0,
                "route_counts": {},
                "admission_counts": {},
                "correct": 0,
                "reference_prediction_mismatches": 0,
                "request_failures": 0,
            },
        }
        with self.assertRaisesRegex(ValueError, "served_requests summary differs"):
            recompute_counts(probe)

    def test_frozen_contract_matches_generator_when_present(self) -> None:
        frozen = Path("experiments/e21b_preflight_contract.json")
        if not frozen.exists():
            self.skipTest("E21b preflight contract has not been frozen")
        self.assertEqual(
            json.loads(frozen.read_text()), build_contract(Path(".").resolve())
        )

    def test_freeze_is_byte_stable(self) -> None:
        root = Path(".").resolve()
        with tempfile.TemporaryDirectory() as directory:
            payloads = []
            for name in ("one", "two"):
                value = build_contract(root)
                destination = Path(directory) / f"{name}.json"
                destination.write_text(
                    json.dumps(value, indent=2, sort_keys=True) + "\n"
                )
                payloads.append(destination.read_bytes())
        self.assertEqual(payloads[0], payloads[1])


if __name__ == "__main__":
    unittest.main()
