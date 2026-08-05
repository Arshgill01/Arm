import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from experiments.e21a_preflight_freeze import build_contract


class E21aPreflightTests(unittest.TestCase):
    def test_contract_waits_at_exact_native_pair(self) -> None:
        contract = build_contract(Path(".").resolve())
        self.assertEqual(
            contract["readiness"]["evaluation"]["decision"],
            "await_native_preflight",
        )
        self.assertFalse(contract["readiness"]["evaluation"]["matrix_allowed"])
        self.assertEqual(contract["execution"]["cell_order"], ["all_uncached", "online"])
        self.assertTrue(contract["execution"]["performance_timings_diagnostic_only"])

    def test_unseen_route_and_call_counts_are_frozen(self) -> None:
        contract = build_contract(Path(".").resolve())
        self.assertEqual(len(contract["prior_certificate"]["prompt_fingerprints"]), 48)
        self.assertEqual(
            contract["acceptance"]["online_route_counts"],
            {"certified_cache": 3, "unknown_shadow_then_oracle": 3},
        )
        self.assertEqual(contract["acceptance"]["baseline_http_calls"], 6)
        self.assertEqual(contract["acceptance"]["online_http_calls"], 9)

    def test_frozen_contract_matches_generator_when_present(self) -> None:
        path = Path("experiments/e21a_preflight_contract.json")
        if not path.exists():
            self.skipTest("E21a preflight contract has not been frozen")
        self.assertEqual(json.loads(path.read_text()), build_contract(Path(".").resolve()))

    def test_freeze_is_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            outputs = [Path(directory) / name for name in ("one.json", "two.json")]
            for output in outputs:
                subprocess.run(
                    [
                        sys.executable,
                        "experiments/e21a_preflight_freeze.py",
                        "--output",
                        str(output),
                    ],
                    check=True,
                )
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())


if __name__ == "__main__":
    unittest.main()
