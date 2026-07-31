from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "e3_ingest.py"
SPEC = importlib.util.spec_from_file_location("e3_ingest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


class E3IngestTests(unittest.TestCase):
    def test_pareto_front_excludes_only_dominated_candidates(self) -> None:
        directions = {
            "quality": "higher",
            "latency": "lower",
            "size": "lower",
        }
        candidates = {
            "fast": {"quality": 0.9, "latency": 8.0, "size": 12.0},
            "small": {"quality": 0.9, "latency": 10.0, "size": 8.0},
            "dominated": {"quality": 0.8, "latency": 12.0, "size": 14.0},
        }
        self.assertEqual(
            ["fast", "small"], INGEST.pareto_front(candidates, directions)
        )

    def test_pareto_front_rejects_unknown_direction(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown Pareto direction"):
            INGEST.pareto_front(
                {"left": {"metric": 1.0}, "right": {"metric": 2.0}},
                {"metric": "sideways"},
            )


if __name__ == "__main__":
    unittest.main()
