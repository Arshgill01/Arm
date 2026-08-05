import json
import tempfile
import unittest
from pathlib import Path

from experiments.e21a_full_fixture import materialize_fixture
from experiments.e21a_full_freeze import build_contract
from experiments.e21a_full_recovery import (
    _observed_counts,
    build_recovered_summary,
)


class E21aFullRecoveryTests(unittest.TestCase):
    def test_observed_counts_are_recomputed_from_records(self) -> None:
        probe = {
            "served_records": [
                {
                    "route": "unknown_shadow_then_oracle",
                    "admission": "denied",
                    "correct": False,
                    "reference_match": False,
                },
                {
                    "route": "denied_fallback",
                    "admission": "retained_denial",
                    "correct": True,
                    "reference_match": True,
                },
            ],
            "raw_calls": [{"error": None}, {"error": None}, {"error": None}],
            "result": {
                "served_requests": 2,
                "actual_http_calls": 3,
                "route_counts": {
                    "denied_fallback": 1,
                    "unknown_shadow_then_oracle": 1,
                },
                "admission_counts": {"denied": 1, "retained_denial": 1},
                "correct": 1,
                "reference_prediction_mismatches": 1,
                "request_failures": 0,
            },
        }
        self.assertEqual(_observed_counts(probe), probe["result"])

    def test_recovery_rejects_untruthful_result_summary(self) -> None:
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
            _observed_counts(probe)

    def test_exact_divergent_matrix_is_retained_as_invalid(self) -> None:
        root = Path(".").resolve()
        with tempfile.TemporaryDirectory() as directory:
            evidence, contract_path = materialize_fixture(
                Path(directory), build_contract(root), root
            )
            for cell in (evidence / "cells").iterdir():
                probe_path = cell / "probe.json"
                probe = json.loads(probe_path.read_text())
                records = probe["served_records"]
                for record in records:
                    if record["task_id"] == "arithmetic-04":
                        record["prediction"] = "C"
                        record["served_response"] = "C"
                        record["correct"] = False
                        record["reference_match"] = False
                        record["served_call"]["prediction"] = "C"
                        record["served_call"]["response"] = "C"
                probe["result"]["correct"] = sum(r["correct"] for r in records)
                probe["result"]["reference_prediction_mismatches"] = sum(
                    not r["reference_match"] for r in records
                )
                probe_path.write_text(
                    json.dumps(probe, indent=2, sort_keys=True) + "\n"
                )
            result = build_recovered_summary(evidence, contract_path, root)
        self.assertEqual(result["status"], "invalid_online_transition_certificate")
        self.assertFalse(result["validity_gates"]["reference_answers_preserved"])
        self.assertFalse(result["decision"]["promoted"])
        self.assertFalse(result["recovery"]["source_contract_or_gates_changed"])

    def test_complete_retained_native_matrix_replays_when_downloaded(self) -> None:
        evidence = Path(".scratch/e21a-30980957266")
        if not evidence.exists():
            self.skipTest("downloaded E21a artifact is unavailable")
        result = build_recovered_summary(
            evidence, Path("experiments/e21a_full_contract.json"), Path(".")
        )
        self.assertEqual(result["status"], "invalid_online_transition_certificate")
        self.assertEqual(result["baseline"]["served_requests"], 480)
        self.assertEqual(result["online"]["served_requests"], 480)
        self.assertEqual(result["quality"]["task_score"], "21/30")
        self.assertEqual(result["quality"]["frozen_reference_task_score"], "23/30")
        self.assertFalse(result["decision"]["promoted"])


if __name__ == "__main__":
    unittest.main()
