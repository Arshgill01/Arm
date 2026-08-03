from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from experiments.e19a_freeze import build_contract, worker_inventory
from experiments.e19a_ingest import expected_trace_with_workers


class E19aTests(unittest.TestCase):
    def test_contract_composes_only_admitted_mechanisms(self) -> None:
        contract = build_contract(Path("."))
        self.assertTrue(contract["prerequisites"]["cache_certificate"]["promoted"])
        self.assertTrue(contract["prerequisites"]["shared_arena"]["promoted"])
        self.assertTrue(contract["mechanism"]["all_groups_use_one_shared_sidecar"])
        self.assertTrue(
            contract["decision"]["both_policies_use_identical_shared_sidecar_workers"]
        )
        self.assertEqual(
            [item["policy"] for item in contract["execution"]["order"]],
            ["all_uncached", "certificate", "certificate", "all_uncached"],
        )

    def test_prefix_affinity_is_complete_and_stable(self) -> None:
        contract = build_contract(Path("."))
        trace = expected_trace_with_workers(contract)
        counts = Counter(item["worker"] for item in trace)
        self.assertEqual(counts, {1: 91, 2: 74})
        assignments = {}
        for item in trace:
            key = (item["point_index"], item["prefix_marker_index"])
            assignments.setdefault(key, item["worker"])
            self.assertEqual(assignments[key], item["worker"])
        self.assertEqual(
            worker_inventory(contract["workload"]),
            contract["execution"]["worker_request_inventory"],
        )

    def test_frozen_contract_matches_generator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        frozen = root / "experiments/e19a_contract.json"
        if not frozen.exists():
            self.skipTest("E19a contract has not been frozen yet")
        self.assertEqual(json.loads(frozen.read_text()), build_contract(root))


if __name__ == "__main__":
    unittest.main()
