import unittest
from pathlib import Path

from experiments.e5b_ingest import load_object
from experiments.e17b_freeze import build_contract
from experiments.e17b_probe import distractor_line, task_user_text


class E17bTests(unittest.TestCase):
    def test_contract_includes_both_supported_quantized_pairs(self) -> None:
        contract = build_contract(Path("."))
        self.assertEqual(
            contract["execution"]["quantized_candidates"],
            ["q8_0_q8_0", "q4_0_q4_0"],
        )
        self.assertEqual(len(contract["execution"]["cells"]), 9)
        self.assertEqual(
            contract["execution"]["cells"][:6],
            [
                {"configuration": "f16_f16", "slots": 4, "repetition": 1},
                {"configuration": "q8_0_q8_0", "slots": 4, "repetition": 1},
                {"configuration": "q4_0_q4_0", "slots": 4, "repetition": 1},
                {"configuration": "q4_0_q4_0", "slots": 4, "repetition": 2},
                {"configuration": "q8_0_q8_0", "slots": 4, "repetition": 2},
                {"configuration": "f16_f16", "slots": 4, "repetition": 2},
            ],
        )
        self.assertTrue(
            contract["decision"][
                "no_global_service_promotion_without_separate_general_quality_confirmation"
            ]
        )

    def test_ledger_is_deterministic_and_contains_one_needle(self) -> None:
        task = load_object(Path("experiments/e17b_tasks.json"))["tasks"][2]
        first = task_user_text(task, 25)
        second = task_user_text(task, 25)
        self.assertEqual(first, second)
        self.assertEqual(first.count(task["retrieval_key"]), 2)
        self.assertEqual(first.count(task["options"][2]), 2)
        self.assertIn("Record 00008: retrieval key", first)

    def test_distractors_are_seeded_and_do_not_contain_retrieval_key(self) -> None:
        self.assertEqual(distractor_line(42, 7), distractor_line(42, 7))
        self.assertNotEqual(distractor_line(42, 7), distractor_line(42, 8))
        self.assertNotIn("PARETO-", distractor_line(42, 7))


if __name__ == "__main__":
    unittest.main()
