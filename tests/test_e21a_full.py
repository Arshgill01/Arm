import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from experiments.e21a_full_fixture import run_synthetic_replay
from experiments.e21a_full_freeze import build_contract


class E21aFullTests(unittest.TestCase):
    def test_contract_is_bounded_and_matrix_authorized(self) -> None:
        contract = build_contract(Path(".").resolve())
        self.assertEqual(
            contract["readiness"]["evaluation"]["decision"], "matrix_allowed"
        )
        self.assertTrue(contract["readiness"]["evaluation"]["matrix_allowed"])
        self.assertEqual(contract["execution"]["order_design"], "ABBA/BAAB")
        self.assertEqual(contract["execution"]["total_cells"], 8)
        self.assertEqual(contract["execution"]["total_served_requests"], 960)
        self.assertEqual(contract["workload"]["unique_prompts"], 30)
        self.assertEqual(contract["workload"]["correct_per_cycle"], 23)

    def test_transition_and_call_counts_are_frozen(self) -> None:
        contract = build_contract(Path(".").resolve())
        self.assertEqual(
            contract["acceptance"]["online_route_counts"],
            {"certified_cache": 89, "unknown_shadow_then_oracle": 31},
        )
        self.assertEqual(
            contract["acceptance"]["online_admission_counts"],
            {"certified": 30, "denied": 1, "retained": 89},
        )
        self.assertEqual(contract["acceptance"]["online_http_calls"], 151)
        self.assertEqual(
            contract["promotion_thresholds"]["minimum_throughput_ratio"], 1.10
        )
        self.assertFalse(
            contract["promotion_thresholds"]["first_use_p95_nonregression_required"]
        )

    def test_complete_synthetic_matrix_replay_is_byte_stable(self) -> None:
        root = Path(".").resolve()
        result, replay = run_synthetic_replay(build_contract(root), root)
        self.assertEqual(
            result["status"], "valid_online_transition_certificate_promoted"
        )
        self.assertTrue(all(result["validity_gates"].values()))
        self.assertTrue(all(result["promotion_gates"].values()))
        self.assertEqual(replay["complete_cells"], 8)
        self.assertEqual(replay["served_requests"], 960)
        self.assertTrue(replay["byte_stable"])
        self.assertGreater(
            result["tail_boundaries"]["synchronous_first_use"]["p95_latency_ratio"],
            1.0,
        )

    def test_frozen_contract_matches_generator_when_present(self) -> None:
        path = Path("experiments/e21a_full_contract.json")
        if not path.exists():
            self.skipTest("E21a full contract has not been frozen")
        self.assertEqual(
            json.loads(path.read_text()), build_contract(Path(".").resolve())
        )

    def test_freeze_is_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outputs = [Path(directory) / name for name in ("one.json", "two.json")]
            for output in outputs:
                subprocess.run(
                    [
                        sys.executable,
                        "experiments/e21a_full_freeze.py",
                        "--output",
                        str(output),
                    ],
                    check=True,
                )
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())


if __name__ == "__main__":
    unittest.main()
