from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "e4_ingest.py"
SPEC = importlib.util.spec_from_file_location("e4_ingest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


def candidate(backlog: int, breaches: list[int], p95: float, rps: float, rss: int) -> dict:
    return {
        "backlog": backlog,
        "rounds": [{"tail_breaches": value} for value in breaches],
        "total_tail_breaches": sum(breaches),
        "total_failures": 0,
        "pooled_latency_ms": {"p95": p95},
        "median_round_requests_per_second": rps,
        "maximum_rss_kib": rss,
    }


class E4IngestTests(unittest.TestCase):
    def test_selection_prefers_smallest_zero_breach_backlog(self) -> None:
        candidates = {
            5: candidate(5, [2, 1, 2], 6.0, 300.0, 24000),
            16: candidate(16, [0, 0, 0], 5.0, 295.0, 24500),
            64: candidate(64, [0, 0, 0], 4.0, 305.0, 25000),
        }
        self.assertEqual(16, INGEST.select_candidate(candidates))

    def test_selection_prioritizes_failures_before_tail_breaches(self) -> None:
        candidates = {
            5: candidate(5, [2, 1, 2], 6.0, 300.0, 24000),
            16: candidate(16, [0, 0, 0], 5.0, 295.0, 24500),
            64: candidate(64, [1, 1, 1], 7.0, 305.0, 25000),
        }
        candidates[16]["total_failures"] = 1
        self.assertEqual(64, INGEST.select_candidate(candidates))

    def test_win_requires_reproduction_tail_elimination_and_guardrails(self) -> None:
        candidates = {
            5: candidate(5, [2, 1, 2], 6.0, 300.0, 24000),
            16: candidate(16, [0, 0, 0], 5.0, 295.0, 24500),
        }
        contract = {
            "acceptance": {
                "minimum_default_breaches_per_round": 1,
                "maximum_selected_failures": 0,
                "maximum_selected_total_breaches": 0,
                "maximum_selected_p95_latency_ms": 50.0,
                "minimum_throughput_ratio_to_default": 0.9,
                "maximum_rss_increase_kib": 10240,
            }
        }
        self.assertTrue(all(INGEST.evaluate_win(candidates, 16, contract).values()))
        candidates[16]["total_tail_breaches"] = 1
        self.assertFalse(
            INGEST.evaluate_win(candidates, 16, contract)[
                "selected_eliminates_tail_breaches"
            ]
        )


if __name__ == "__main__":
    unittest.main()
