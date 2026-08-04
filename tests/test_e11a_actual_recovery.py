import json
import unittest
from pathlib import Path

from experiments.e11a_actual_recovery_freeze import (
    INPUT_PATHS,
    build_contract,
    job_for_candidate,
)


class E11aActualRecoveryTests(unittest.TestCase):
    def test_job_lookup_is_exact(self) -> None:
        source = {
            "jobs": [
                {"name": "candidate_a native holdout", "conclusion": "success"},
                {"name": "candidate_b native holdout", "conclusion": "failure"},
            ]
        }
        self.assertEqual(
            job_for_candidate(source, "candidate_b")["conclusion"], "failure"
        )
        with self.assertRaises(ValueError):
            job_for_candidate(source, "candidate")

    def test_terminal_contract_accounts_for_every_candidate(self) -> None:
        root = Path(__file__).resolve().parents[1]
        if not (root / INPUT_PATHS["source_run"]).exists():
            self.skipTest("E11a source run is not terminal yet")
        contract = build_contract(root)
        accounted = set(contract["valid_candidate_order"]) | set(
            contract["resource_infeasible_candidate_order"]
        )
        self.assertEqual(accounted, set(contract["attempted_candidates"]))
        self.assertFalse(
            set(contract["deployable_candidate_order"])
            & set(contract["resource_infeasible_candidate_order"])
        )

    def test_frozen_contract_matches_generator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        frozen = root / "experiments/e11a_actual_recovery_contract.json"
        if not frozen.exists():
            self.skipTest("E11a actual recovery has not been frozen yet")
        self.assertEqual(json.loads(frozen.read_text()), build_contract(root))


if __name__ == "__main__":
    unittest.main()
