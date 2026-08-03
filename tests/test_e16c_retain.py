import unittest
from pathlib import Path

from experiments.e16c_retain import validate_inventory


class E16cRetainTests(unittest.TestCase):
    def test_shared_arena_inventory_contains_no_sidecar_or_model(self) -> None:
        evidence = Path(".scratch/e16c-30851609576")
        if not evidence.exists():
            self.skipTest("downloaded E16c artifact is not present")
        result = validate_inventory(evidence, "30851609576", 1)
        self.assertTrue(result["all_retained_file_hashes_verified"])
        self.assertFalse(result["generated_sidecar_or_model_retained"])
        self.assertEqual(result["file_count"], 325)


if __name__ == "__main__":
    unittest.main()
