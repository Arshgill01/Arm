import json
import unittest
from pathlib import Path

from experiments.e20c_retain import retain, validate_workflow_inventory


class E20cRetainTests(unittest.TestCase):
    def test_real_workflow_inventory_when_downloaded(self) -> None:
        evidence = Path(".scratch/e20c-30870229218")
        if not evidence.exists():
            self.skipTest("downloaded E20c artifact is unavailable")
        inventory = validate_workflow_inventory(evidence)
        self.assertEqual(inventory["hashed_files"], 195)
        self.assertIn("summary.json", inventory["entries"])
        self.assertIn(
            "cells/safety-reuse_on-r7/probe.json", inventory["entries"]
        )

    def test_real_replay_when_downloaded(self) -> None:
        evidence = Path(".scratch/e20c-30870229218")
        if not evidence.exists():
            self.skipTest("downloaded E20c artifact is unavailable")
        retained = retain(
            evidence,
            Path("experiments/e20c_contract.json"),
            Path("."),
            evidence / "run-metadata.json",
            evidence / "artifact-metadata.json",
        )
        self.assertTrue(retained["campaign_decision"]["guarded_safety_success"])
        self.assertFalse(retained["campaign_decision"]["performance_win"])
        self.assertTrue(
            retained["campaign_decision"]["ffn_pair_fusion_lane_closed"]
        )

    def test_retained_manifest_closes_lane(self) -> None:
        path = Path("results/manifests/e20c-30870229218.json")
        if not path.exists():
            self.skipTest("E20c retained manifest has not been generated")
        retained = json.loads(path.read_text())
        self.assertEqual(
            retained["status"], "valid_guarded_repack_pair_reuse_no_win"
        )
        self.assertFalse(retained["hypothesis"]["passed"])
        self.assertTrue(retained["campaign_decision"]["ffn_pair_fusion_lane_closed"])


if __name__ == "__main__":
    unittest.main()
