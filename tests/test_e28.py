import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "e28_ingest", ROOT / "experiments" / "e28_ingest.py"
)
assert SPEC and SPEC.loader
E28 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E28)


class E28ContractTests(unittest.TestCase):
    def test_contract_freezes_matrix_order_and_gates(self) -> None:
        contract = json.loads((ROOT / "experiments/e28_contract.json").read_text())
        self.assertEqual(contract["experiment_id"], "E28")
        self.assertEqual(
            contract["matrix"]["D"],
            ["pinned_baseline_series", "e25", "e27"],
        )
        self.assertEqual(
            contract["performance"]["process_order_per_round"],
            ["A", "B", "C", "D", "D", "C", "B", "A"],
        )
        self.assertEqual(contract["performance"]["processes_per_variant_per_case"], 6)
        self.assertEqual(contract["quality"]["repetitions_per_variant"], 2)
        self.assertEqual(contract["resource_policy"]["maximum_total_usd"], 12.0)

    def test_campaign_is_staged_and_e26_is_absent(self) -> None:
        campaign = (ROOT / "experiments/e28_pinned_campaign.sh").read_text()
        self.assertIn("prepare|benchmark|demo-profile|all", campaign)
        self.assertIn("run_correctness", campaign)
        self.assertIn("run_quality_and_perplexity", campaign)
        self.assertIn("run_benchmarks", campaign)
        self.assertNotIn("e26", campaign.lower())


class E28IngestTests(unittest.TestCase):
    def test_six_sample_summary_and_bootstrap_are_deterministic(self) -> None:
        summary = E28.median_summary([10, 11, 12, 13, 14, 15], "units")
        self.assertEqual(summary["median_units"], 12.5)
        with self.assertRaises(ValueError):
            E28.median_summary([10] * 5, "units")
        first = E28.bootstrap_ratio(
            [20, 21, 22, 23, 24, 25],
            [10, 11, 12, 13, 14, 15],
            seed=28,
            resamples=100,
        )
        second = E28.bootstrap_ratio(
            [20, 21, 22, 23, 24, 25],
            [10, 11, 12, 13, 14, 15],
            seed=28,
            resamples=100,
        )
        self.assertEqual(first, second)

    def test_inference_uses_six_process_medians(self) -> None:
        contract = {
            "performance": {
                "confidence_interval": {"seed": 28, "resamples": 100},
                "whole_model_cases": [{"id": "tg128"}],
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "inference" / "tg128"
            case.mkdir(parents=True)
            for variant_index, variant in enumerate(E28.VARIANTS, start=1):
                for run in range(6):
                    stem = case / f"r{run}-{variant}"
                    value = 10.0 * variant_index + run
                    stem.with_suffix(".jsonl").write_text(
                        json.dumps(
                            {"avg_ts": value, "samples_ts": [value, value, value]}
                        )
                        + "\n"
                    )
                    stem.with_suffix(".time").write_text(
                        "Maximum resident set size (kbytes): 1000\n"
                    )
            result = E28.inference_summary(root, contract)
            self.assertEqual(result["tg128"]["A"]["count"], 6)
            self.assertEqual(result["tg128"]["D"]["median_tokens_per_second"], 42.5)
            self.assertAlmostEqual(result["tg128"]["D_over_A"]["ratio"], 42.5 / 12.5)


if __name__ == "__main__":
    unittest.main()
