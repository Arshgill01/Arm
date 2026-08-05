import json
import tempfile
import unittest
from pathlib import Path

from experiments.e21b_full_fixture import materialize_fixture, run_synthetic_replay
from experiments.e21b_full_freeze import build_contract, maximum_denied_known_routes
from experiments.e21b_full_ingest import build_summary, expected_cell_path


class E21bFullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(".").resolve()
        cls.contract = build_contract(cls.root)

    def test_contract_is_byte_stable_and_preflight_authorized(self) -> None:
        again = build_contract(self.root)
        self.assertEqual(self.contract, again)
        self.assertEqual(self.contract["experiment_id"], "E21b")
        self.assertEqual(self.contract["preflight"]["run_id"], "30983800871")
        self.assertEqual(self.contract["execution"]["order_design"], "ABBA/BAAB")
        self.assertEqual(self.contract["execution"]["total_cells"], 8)
        self.assertEqual(self.contract["execution"]["total_served_requests"], 960)
        self.assertEqual(self.contract["execution"]["total_raw_http_calls"], 1084)
        self.assertEqual(
            self.contract["readiness"]["evaluation"]["decision"], "matrix_allowed"
        )

    def test_adaptive_route_floor_is_worst_case_not_observed_exact_count(self) -> None:
        sequence = self.contract["workload"]["task_sequence"]
        maximum = maximum_denied_known_routes(sequence, 7)
        self.assertEqual(maximum, 21)
        self.assertEqual(self.contract["acceptance"]["minimum_certified_routes"], 68)
        self.assertEqual(
            self.contract["acceptance"]["maximum_denied_fallback_routes"], 21
        )

    def test_complete_synthetic_matrix_is_byte_stable_and_promoted(self) -> None:
        summary, replay = run_synthetic_replay(self.contract, self.root)
        self.assertTrue(replay["byte_stable"])
        self.assertEqual(replay["complete_cells"], 8)
        self.assertEqual(replay["served_requests"], 960)
        self.assertEqual(summary["status"], "valid_openai_online_certificate_promoted")
        self.assertTrue(all(summary["validity_gates"].values()))
        self.assertTrue(all(summary["promotion_gates"].values()))
        self.assertEqual(summary["quality"]["paired_exact_response_mismatches"], 0)
        self.assertEqual(summary["revocation_boundary"]["observed_revocations"], 0)
        self.assertFalse(
            summary["revocation_boundary"]["post_certification_revocation_supported"]
        )

    def test_exact_output_drift_fails_validity_without_changing_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence, contract_path = materialize_fixture(
                Path(directory), self.contract, self.root
            )
            spec = next(
                item
                for item in self.contract["execution"]["cell_order"]
                if item["policy"] == "online" and item["repetition"] == 1
            )
            probe_path = evidence / "cells" / expected_cell_path(spec) / "probe.json"
            probe = json.loads(probe_path.read_text())
            record = probe["served_records"][31]
            record["served_response"] = f" {record['served_response']}"
            record["served_call"]["response"] = record["served_response"]
            raw_index = record["served_call"]["http_call_index"]
            probe["raw_calls"][raw_index]["response"] = record["served_response"]
            probe_path.write_text(json.dumps(probe, indent=2, sort_keys=True) + "\n")
            summary = build_summary(evidence, contract_path, self.root)
            self.assertFalse(
                summary["validity_gates"]["exact_online_outputs_match_paired_uncached"]
            )
            self.assertFalse(summary["decision"]["valid"])

    def test_corrupt_registry_fails_integrity_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence, contract_path = materialize_fixture(
                Path(directory), self.contract, self.root
            )
            spec = next(
                item
                for item in self.contract["execution"]["cell_order"]
                if item["policy"] == "online" and item["repetition"] == 2
            )
            probe_path = evidence / "cells" / expected_cell_path(spec) / "probe.json"
            probe = json.loads(probe_path.read_text())
            probe["registry"]["payload_sha256"] = "0" * 64
            probe_path.write_text(json.dumps(probe, indent=2, sort_keys=True) + "\n")
            summary = build_summary(evidence, contract_path, self.root)
            self.assertFalse(summary["validity_gates"]["registry_integrity_and_bounds"])
            self.assertFalse(summary["decision"]["valid"])


if __name__ == "__main__":
    unittest.main()
