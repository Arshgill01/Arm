from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.e11a_q8_resource_failure_retain import compact_inventory


class E11aQ8ResourceFailureTests(unittest.TestCase):
    def test_compact_inventory_is_ordered_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "z.txt").write_text("z\n")
            (root / "a.txt").write_text("aa\n")
            result = compact_inventory(root)
            self.assertTrue(result["all_extracted_regular_files_hashed"])
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(result["total_regular_file_bytes"], 5)
            self.assertEqual(len(result["inventory_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
