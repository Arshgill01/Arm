from __future__ import annotations

import unittest
from pathlib import Path

from experiments.e5b_ingest import sha256_file


class E16cFailureRetentionTests(unittest.TestCase):
    def test_group_runner_is_now_executable_without_content_drift(self) -> None:
        root = Path(__file__).resolve().parents[1]
        runner = root / "experiments/e16c_shared_arena_group.sh"
        self.assertTrue(runner.stat().st_mode & 0o100)
        self.assertEqual(
            sha256_file(root / "experiments/e16c_contract.json"),
            "118bed9c2887bfaef877dbac5ffdd74890f2b3abab6c651c8c579c3891d26df0",
        )


if __name__ == "__main__":
    unittest.main()
