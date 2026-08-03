import gzip
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e10e_retain import raw_inventory


class E10eRetainTests(unittest.TestCase):
    def test_recursive_raw_inventory_includes_variant_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for variant in ("original", "forced"):
                target = root / "variants" / variant / "raw" / "response.json.gz"
                target.parent.mkdir(parents=True)
                target.write_bytes(gzip.compress(json.dumps({"tokens": [1]}).encode()))
            result = raw_inventory(root)
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(len(result["inventory_sha256"]), 64)

    def test_recursive_raw_inventory_rejects_empty_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                raw_inventory(Path(directory))


if __name__ == "__main__":
    unittest.main()
