import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "e27_second", ROOT / "experiments" / "e27_second_arm_ingest.py"
)
assert SPEC and SPEC.loader
E27 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E27)


class E27SecondArmIngestTest(unittest.TestCase):
    def test_pair_uses_six_process_medians(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "direct").mkdir()
            for variant, value in (("baseline", 90.0), ("candidate", 30.0)):
                for run in range(6):
                    path = root / "direct" / f"case-{run}-{variant}.json"
                    path.write_text(json.dumps({"median_us": value + run}) + "\n")
            result = E27.pair(root, "direct", "case", "median_us", True)
            self.assertAlmostEqual(result["speedup"], 92.5 / 32.5)

    def test_six_values_rejects_missing_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for run in range(5):
                (root / f"case-{run}.json").write_text('{"value": 1}\n')
            with self.assertRaises(ValueError):
                E27.six_values(root, "case-*.json", "value")


if __name__ == "__main__":
    unittest.main()
