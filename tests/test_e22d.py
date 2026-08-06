from __future__ import annotations

import json
import unittest
from pathlib import Path

from experiments.e22a_freeze import sha256_file
from experiments.e22d_freeze import build_contract
from experiments.e22d_ingest import distribution


class E22dIndependentHostReplicationTests(unittest.TestCase):
    @property
    def root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_frozen_contract_matches_generator(self) -> None:
        contract_path = self.root / "experiments/e22d_contract.json"
        frozen = json.loads(contract_path.read_text())
        self.assertEqual(frozen, build_contract(self.root))
        self.assertEqual(64, len(sha256_file(contract_path)))

    def test_replication_is_not_a_readiness_reroll(self) -> None:
        contract = build_contract(self.root)
        self.assertTrue(
            contract["advance"]["readiness_is_disclosure_only_not_a_replication_gate"]
        )
        self.assertFalse(contract["scientific_boundary"]["readiness_reroll_permitted"])
        self.assertNotIn(
            "maximum_median_all_worker_readiness_ratio", contract["advance"]
        )

    def test_independent_host_and_cost_stops_are_frozen(self) -> None:
        contract = build_contract(self.root)
        host = contract["host_requirements"]
        cost = contract["cost_control"]
        self.assertTrue(host["different_instance_id_from_source"])
        self.assertEqual(14_400, host["automatic_delete_after_seconds_at_most"])
        self.assertEqual("DELETE", host["instance_termination_action"])
        self.assertLess(
            cost["experiment_maximum_usd"], cost["user_authorized_ceiling_usd"]
        )
        self.assertLess(
            cost["estimated_maximum_compute_usd"], cost["experiment_maximum_usd"]
        )

    def test_distribution_is_population_summary(self) -> None:
        result = distribution([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(2.5, result["median"])
        self.assertAlmostEqual(
            1.118033988749895, result["population_standard_deviation"]
        )


if __name__ == "__main__":
    unittest.main()
