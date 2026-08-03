import unittest
from pathlib import Path

from experiments.e15b_retain import validate_inventory


class E15bRetainTests(unittest.TestCase):
    def test_runtime_alias_inventory_is_fully_verified(self) -> None:
        evidence = Path(".scratch/e15b-30851607665")
        if not evidence.exists():
            self.skipTest("downloaded E15b artifact is not present")
        result = validate_inventory(evidence, "30851607665", 1)
        self.assertTrue(result["all_retained_file_hashes_verified"])
        self.assertEqual(result["file_count"], 237)


if __name__ == "__main__":
    unittest.main()
