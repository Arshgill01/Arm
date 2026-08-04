import unittest
from pathlib import Path

from experiments.e11a_actual_recovery_retain import validate_inventory


class E11aActualRecoveryRetainTests(unittest.TestCase):
    def test_real_compact_inventory_when_present(self) -> None:
        path = Path(".scratch/e11a-actual-recovery-30868725586")
        if not path.exists():
            self.skipTest("downloaded E11a recovery artifact is unavailable")
        inventory = validate_inventory(path)
        self.assertEqual(inventory["file_count"], 11)
        self.assertTrue(inventory["all_workflow_inventoried_files_verified"])


if __name__ == "__main__":
    unittest.main()
