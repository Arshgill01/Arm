import json
import tempfile
import unittest
from pathlib import Path

from experiments.e26_compare import read_f32


ROOT = Path(__file__).resolve().parents[1]


class E26NegativeResultTest(unittest.TestCase):
    def test_rejected_result_cannot_claim_promotion(self) -> None:
        result = json.loads((ROOT / "results/raw/e26a-axion-negative-summary.json").read_text())
        self.assertEqual(result["decision"], "reject")
        self.assertFalse(result["gates"]["cheap_layer_pass"])
        self.assertFalse(result["gates"]["whole_model_run_allowed"])
        self.assertLess(
            result["gates"]["best_observed_layer_speedup"],
            result["gates"]["minimum_layer_speedup"],
        )
        self.assertFalse(result["production"]["enabled"])
        self.assertTrue((ROOT / result["production"]["rejected_patch"]).is_file())

    def test_float_reader_rejects_partial_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.bin"
            path.write_bytes(b"123")
            with self.assertRaisesRegex(ValueError, "not a float32 file"):
                read_f32(path)


if __name__ == "__main__":
    unittest.main()
