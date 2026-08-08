import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "e27_ingest", ROOT / "experiments" / "e27_ingest.py"
)
assert SPEC and SPEC.loader
E27 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E27)


class E27IngestTest(unittest.TestCase):
    def test_summarize_requires_six_positive_processes(self):
        result = E27.summarize([10, 11, 12, 13, 14, 15], "us")
        self.assertEqual(result["median_us"], 12.5)
        with self.assertRaises(ValueError):
            E27.summarize([10] * 5, "us")
        with self.assertRaises(ValueError):
            E27.summarize([10, 10, 10, 10, 10, 0], "us")

    def test_direct_speedup_uses_process_medians(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "direct").mkdir()
            for variant, value in (("baseline", 120.0), ("candidate", 80.0)):
                for run in range(6):
                    (root / "direct" / f"shape-{run}-{variant}.json").write_text(
                        json.dumps({"median_us": value + run}) + "\n"
                    )
            result = E27.direct_case(root, "shape")
            self.assertAlmostEqual(result["speedup"], 122.5 / 82.5)

    def test_correctness_enforces_declared_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "correctness").mkdir()
            rows = [
                {"nmse": 1e-5, "max_abs_error": 1e-3, "pass": True}
                for _ in range(9)
            ]
            (root / "correctness" / "cases.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows)
            )
            self.assertTrue(E27.correctness_summary(root, 5e-4)["accepted"])
            rows[-1]["nmse"] = 6e-4
            (root / "correctness" / "cases.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows)
            )
            self.assertFalse(E27.correctness_summary(root, 5e-4)["accepted"])


if __name__ == "__main__":
    unittest.main()
