from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "e6b_ingest.py"
SPEC = importlib.util.spec_from_file_location("e6b_ingest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


class E6bIngestTests(unittest.TestCase):
    def test_perf_parser_requires_every_frozen_size(self) -> None:
        text = """q8_0
  quantize_row_q
    4096 values (0.02 MB)
      float32 throughput   :     12.50 GB/s
      quantized throughput :      1.00 GB/s
    65536 values (0.25 MB)
      float32 throughput   :      9.25 GB/s
      quantized throughput :      0.75 GB/s
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "perf.log"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(
                {4096: 12.5, 65536: 9.25},
                INGEST.parse_perf(path, [4096, 65536]),
            )
            with self.assertRaisesRegex(ValueError, "frozen benchmark sizes"):
                INGEST.parse_perf(path, [4096, 65536, 655360])

    def test_paired_effect_applies_metric_direction(self) -> None:
        baseline = {1: [10.0, 10.0], 2: [20.0, 20.0]}
        patched = {1: [12.0, 12.0], 2: [24.0, 24.0]}
        higher = INGEST.paired_effect(baseline, patched, "higher")
        lower = INGEST.paired_effect(patched, baseline, "lower")
        self.assertAlmostEqual(1.2, higher["median_improvement_ratio"])
        self.assertAlmostEqual(1.2, lower["median_improvement_ratio"])
        self.assertEqual(2, higher["improved_rounds"])

    def test_assembly_summary_distinguishes_scalar_and_vector_stores(self) -> None:
        text = """  10: stur b31, [x1, #-1]
  14: str b2, [x1]
  18: uzp1 v31.8h, v31.8h, v23.8h
  1c: xtn v30.8h, v29.4s
  20: stur q31, [x1, #-16]
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "assembly.txt"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(
                {
                    "static_instructions": 5,
                    "byte_stores": 2,
                    "vector_stores": 1,
                    "vector_narrows": 2,
                },
                INGEST.assembly_summary(path),
            )

    def test_win_requires_mechanism_direct_speed_and_guardrails(self) -> None:
        direct = {
            "4096": {"median_improvement_ratio": 1.4, "improved_rounds": 4},
            "65536": {"median_improvement_ratio": 1.2, "improved_rounds": 3},
        }
        inference = {
            "decode": {"median_improvement_ratio": 1.01},
            "total": {"median_improvement_ratio": 0.99},
        }
        assembly = {
            "baseline": {"byte_stores": 32},
            "patched": {
                "byte_stores": 0,
                "vector_narrows": 4,
                "vector_stores": 2,
            },
        }
        acceptance = {
            "direct_minimum_median_improvement_ratio_by_size": {
                "4096": 1.25,
                "65536": 1.15,
            },
            "direct_minimum_improved_rounds_by_size": {
                "4096": 3,
                "65536": 3,
            },
            "minimum_inference_improvement_ratio": 0.98,
            "maximum_patched_rss_increase_kib": 1024,
            "minimum_baseline_byte_stores": 16,
            "maximum_patched_byte_stores": 4,
            "minimum_patched_vector_narrows": 2,
            "minimum_patched_vector_stores": 2,
        }
        criteria, direct_criteria, inference_criteria = INGEST.evaluate_win(
            direct,
            inference,
            {"baseline": 1000, "patched": 1500},
            assembly,
            True,
            acceptance,
        )
        self.assertTrue(all(criteria.values()))
        self.assertTrue(all(direct_criteria.values()))
        self.assertTrue(all(inference_criteria.values()))
        direct["4096"]["median_improvement_ratio"] = 1.1
        criteria, _, _ = INGEST.evaluate_win(
            direct,
            inference,
            {"baseline": 1000, "patched": 1500},
            assembly,
            True,
            acceptance,
        )
        self.assertFalse(criteria["direct_benchmark_gates_met"])


if __name__ == "__main__":
    unittest.main()
