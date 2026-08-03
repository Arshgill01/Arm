from __future__ import annotations

import unittest
from pathlib import Path

from experiments.e5b_ingest import sha256_file


class E15bFailureRetentionTests(unittest.TestCase):
    def test_cell_runner_is_now_executable_without_contract_drift(self) -> None:
        root = Path(__file__).resolve().parents[1]
        runner = root / "experiments/e15b_affinity_cell.sh"
        self.assertTrue(runner.stat().st_mode & 0o100)
        self.assertEqual(
            sha256_file(root / "experiments/e15b_contract.json"),
            "29d01a19839edae7e568f447e9bca8f2eccbfea6df415ce45af6c8f080db6e5a",
        )


if __name__ == "__main__":
    unittest.main()
