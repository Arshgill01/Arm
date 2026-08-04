import unittest
from pathlib import Path

from experiments.e20b_failure_retain import artifact_inventory


class E20bFailureRetainTests(unittest.TestCase):
    def test_real_artifact_inventory_is_complete_when_present(self) -> None:
        path = Path(".scratch/e20b-30867317408")
        if not path.exists():
            self.skipTest("downloaded E20b artifact is unavailable")
        inventory = artifact_inventory(path)
        self.assertGreaterEqual(inventory["file_count"], 70)
        self.assertIn("preflight/reuse_on/stderr.log", inventory["entries"])
        self.assertIn(
            "cells/02-reuse_on-r1/server.stderr.log", inventory["entries"]
        )
        self.assertNotIn("run-metadata.json", inventory["entries"])


if __name__ == "__main__":
    unittest.main()
