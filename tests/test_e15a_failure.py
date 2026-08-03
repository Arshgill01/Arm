from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.e15a_failure_retain import inventory


class E15aFailureRetentionTests(unittest.TestCase):
    def test_inventory_hashes_every_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("a\n", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested/b.txt").write_text("bb\n", encoding="utf-8")
            result = inventory(root)
            self.assertTrue(result["all_extracted_regular_files_hashed"])
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(result["total_regular_file_bytes"], 5)
            self.assertEqual(
                [item["path"] for item in result["files"]],
                ["a.txt", "nested/b.txt"],
            )


if __name__ == "__main__":
    unittest.main()
