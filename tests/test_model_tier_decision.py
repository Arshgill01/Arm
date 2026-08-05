import tempfile
import unittest
from pathlib import Path

from experiments.model_tier_decision import build_decision


class ModelTierDecisionTests(unittest.TestCase):
    def build(self):
        return build_decision(
            e11b_path=Path(
                "results/manifests/e11b-30869286295-recovered.json"
            ),
            e12b_path=Path(
                "results/manifests/e12b-30869536393-recovered.json"
            ),
            memory_path=Path("results/manifests/e6i-30691254831.json"),
            sidecar_path=Path("results/manifests/e16b-30842925537.json"),
        )

    def test_q4_k_m_is_the_only_promoted_model_tier(self) -> None:
        result = self.build()
        self.assertEqual(result["selected_model"]["exact_30_task_correct"], 23)
        self.assertEqual(
            result["selected_model"]["maximum_anchor_answer_mismatches"], 0
        )
        self.assertEqual(
            result["terminal_decision"]["selected_model"],
            "ministral3_3b_q4_k_m",
        )
        self.assertEqual(
            result["terminal_decision"]["additional_model_tiers_promoted"], []
        )
        self.assertFalse(
            result["terminal_decision"]["new_native_model_experiment_authorized"]
        )

    def test_iq4_nl_tradeoff_is_preserved_not_promoted(self) -> None:
        result = self.build()
        iq4_nl = next(
            item
            for item in result["stock_candidate_assessments"]
            if item["candidate"] == "ministral3_3b_iq4_nl"
        )
        self.assertEqual(iq4_nl["exact_30_task_correct"], 23)
        self.assertEqual(iq4_nl["maximum_anchor_answer_mismatches"], 1)
        self.assertLess(iq4_nl["ratios_to_anchor"]["throughput"], 1.0)
        self.assertLess(iq4_nl["ratios_to_anchor"]["maximum_rss"], 1.0)
        self.assertIn("marginal_tradeoff", iq4_nl["decision"])

    def test_generated_frontier_remains_unpromoted(self) -> None:
        result = self.build()
        generated = result["generated_frontier_assessment"]
        self.assertEqual(generated["generated_recipes"], 9)
        self.assertEqual(generated["combined_quality_size_frontier_points"], 11)
        self.assertFalse(generated["matched_native_service_evidence_available"])
        self.assertEqual(len(generated["strongest_unconfirmed_signals"]), 2)

    def test_repeated_derivation_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = self.build()
            second = self.build()
            self.assertEqual(first, second)
            self.assertNotIn(directory, str(first))


if __name__ == "__main__":
    unittest.main()
