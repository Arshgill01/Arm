from __future__ import annotations

import unittest
from pathlib import Path

from experiments.e16d_lifecycle_fixture import replay_once, run_synthetic_replay
from experiments.e16d_lifecycle_freeze import build_contract


class E16dLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path.cwd()
        cls.contract = build_contract(cls.root)

    def test_complete_lifecycle_replay_is_valid_and_byte_stable(self) -> None:
        summary, replay = run_synthetic_replay(self.contract, self.root)
        self.assertEqual("valid_product_sidecar_lifecycle", summary["status"])
        self.assertTrue(all(summary["gates"].values()))
        self.assertEqual(14, len(summary["gates"]))
        self.assertTrue(replay["byte_stable"])
        self.assertEqual(2, replay["independent_replays"])
        self.assertFalse(summary["decision"]["new_native_performance_claim_allowed"])

    def test_private_mapping_fails_closed(self) -> None:
        summary = replay_once(self.contract, self.root, private_second_mapping=True)
        self.assertEqual("invalid_product_sidecar_lifecycle", summary["status"])
        self.assertFalse(summary["gates"]["same_read_only_shared_inode_mapped"])
        self.assertFalse(summary["decision"]["product_sidecar_workflow_promoted"])


if __name__ == "__main__":
    unittest.main()
