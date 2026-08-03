from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.e18a_freeze import build_contract
from experiments.e18a_ingest import evaluate
from experiments.e18a_profile_inventory import build_inventory


class E18aTests(unittest.TestCase):
    def test_frozen_contract_matches_generator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        frozen = root / "experiments/e18a_contract.json"
        if not frozen.exists():
            self.skipTest("E18a contract has not been frozen yet")
        self.assertEqual(json.loads(frozen.read_text()), build_contract(root))

    def test_contract_is_reverse_balanced_and_workload_specific(self) -> None:
        contract = build_contract(Path("."))
        self.assertEqual(contract["execution"]["repetitions_per_profile"], 6)
        self.assertEqual(
            [item["profile"] for item in contract["execution"]["order"]],
            [
                "release_control",
                "workload_pgo",
                "workload_pgo",
                "release_control",
            ]
            * 3,
        )
        self.assertEqual(
            {
                (item["profile"], item["repetition"])
                for item in contract["execution"]["order"]
            },
            {
                (profile, repetition)
                for profile in ("release_control", "workload_pgo")
                for repetition in range(1, 7)
            },
        )
        self.assertTrue(
            contract["training"]["same_build_directory_for_generate_and_use"]
        )
        self.assertIn(
            "-fprofile-generate=", contract["training"]["profile_generate_flags"]
        )
        self.assertIn("-fprofile-use=", contract["training"]["profile_use_flags"])
        self.assertTrue(
            contract["training"]["training_result_is_not_performance_evidence"]
        )
        self.assertTrue(contract["decision"]["no_generic_default_or_other_model_claim"])

    def test_inventory_hashes_every_nonempty_gcda_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(20):
                path = root / f"objects/{index:02d}.gcda"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"profile-{index}".encode())
            inventory = build_inventory(root)
        self.assertEqual(inventory["file_count"], 20)
        self.assertEqual(len(inventory["files"]), 20)
        self.assertEqual(
            inventory["total_size_bytes"],
            sum(item["size_bytes"] for item in inventory["files"]),
        )
        self.assertEqual(len({item["sha256"] for item in inventory["files"]}), 20)

    def test_evaluation_requires_every_frozen_gate(self) -> None:
        contract = build_contract(Path("."))
        def metric(
            median: float,
            p95: float | None = None,
            maximum: float | None = None,
            cv: float = 0.01,
        ) -> dict[str, float]:
            return {
                "median": median,
                "p95": median if p95 is None else p95,
                "max": median if maximum is None else maximum,
                "coefficient_of_variation": cv,
            }
        performance = {
            "release_control": {
                "requests_per_second": metric(10.0),
                "http_ms": metric(100.0, 120.0),
                "server_cpu_seconds_per_request": metric(1.0),
                "ready_ms": metric(1000.0),
                "maximum_rss_kib": metric(1000.0, maximum=1000.0),
                "quality": {"exact_selected_predictions": True},
            },
            "workload_pgo": {
                "requests_per_second": metric(10.3),
                "http_ms": metric(98.0, 121.0),
                "server_cpu_seconds_per_request": metric(0.98),
                "ready_ms": metric(1050.0),
                "maximum_rss_kib": metric(1000.0, maximum=1010.0),
                "quality": {"exact_selected_predictions": True},
            },
        }
        builds = {
            "release_control": {"runtime_closure": {"total_size_bytes": 1000}},
            "workload_pgo": {"runtime_closure": {"total_size_bytes": 1030}},
        }
        self.assertTrue(evaluate(performance, builds, contract)["passed"])
        performance["workload_pgo"]["quality"]["exact_selected_predictions"] = False
        result = evaluate(performance, builds, contract)
        self.assertFalse(result["passed"])
        self.assertEqual(result["selected_profile"], "release_control")


if __name__ == "__main__":
    unittest.main()
