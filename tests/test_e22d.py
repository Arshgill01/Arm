from __future__ import annotations

import json
import unittest
from pathlib import Path

from experiments.e22a_freeze import sha256_file
from experiments.e22d_freeze import build_contract
from experiments.e22d_ingest import distribution
from experiments.e22d_retain import (
    ARCHIVE_SHA256,
    INSTANCE_ID,
    SETUP_FAILURE_ARCHIVE_SHA256,
)


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

    def test_retained_result_promotes_only_the_two_instance_density_claim(
        self,
    ) -> None:
        result = json.loads(
            (self.root / "results/manifests/e22d-axion-20260806.json").read_text()
        )
        combined = result["combined_two_instance_result"]
        retention = result["retention_validation"]
        claims = result["claim_decision"]

        self.assertEqual(
            "valid_independent_host_replication_promoted", result["status"]
        )
        self.assertFalse(result["failed_advance_gates"])
        self.assertTrue(all(result["validity_gates"].values()))
        self.assertTrue(all(result["advance_gates"].values()))
        self.assertEqual(INSTANCE_ID, result["host"]["instance_id"])
        self.assertEqual(2, combined["independent_instances"])
        self.assertEqual(8, combined["balanced_pairs"])
        self.assertEqual(3_360, combined["exact_measured_requests"])
        self.assertAlmostEqual(
            1.3568374837384678,
            combined["ratio_distributions"]["aggregate_throughput_ratio"]["median"],
        )
        self.assertAlmostEqual(
            0.5932237202265771,
            combined["ratio_distributions"]["summed_pss_saved_fraction"]["median"],
        )
        self.assertEqual(ARCHIVE_SHA256, retention["archive_sha256"])
        self.assertEqual(
            SETUP_FAILURE_ARCHIVE_SHA256,
            retention["setup_failure_archive_sha256"],
        )
        self.assertTrue(
            retention["workflow_inventory"]["all_retained_file_hashes_verified"]
        )
        self.assertTrue(claims["two_independent_axion_instance_density_promotion"])
        self.assertFalse(claims["full_all_lifecycle_promotion"])
        self.assertFalse(claims["cross_provider_or_fleet_claim_permitted"])
        self.assertTrue(claims["readiness_regression_must_be_disclosed"])

    def test_paid_replication_was_deleted_below_its_cost_guardrail(self) -> None:
        result = json.loads(
            (self.root / "results/manifests/e22d-axion-20260806.json").read_text()
        )
        cleanup = result["resource_cleanup"]
        self.assertEqual("DONE", cleanup["delete_operation"]["status"])
        self.assertEqual(INSTANCE_ID, cleanup["delete_operation"]["target_id"])
        self.assertTrue(all(cleanup["post_delete_checks"].values()))
        self.assertLess(
            cleanup["cost_closeout"]["estimated_compute_usd"],
            result["cost_control"]["experiment_maximum_usd"],
        )


if __name__ == "__main__":
    unittest.main()
