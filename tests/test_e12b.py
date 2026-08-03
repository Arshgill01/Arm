import json
import unittest
from pathlib import Path


class E12bPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(Path("experiments/e12b_plan.json").read_text())
        cls.candidates = {item["candidate"]: item for item in cls.plan["candidates"]}

    def test_candidate_names_and_recipes_are_unique(self) -> None:
        self.assertEqual(len(self.candidates), 9)
        recipes = [
            tuple(item["argv_after_binary"]) for item in self.candidates.values()
        ]
        self.assertEqual(len(set(recipes)), len(recipes))

    def test_matched_pairs_bind_controls_to_imatrix_equivalents(self) -> None:
        for control_name, imatrix_name in self.plan["matched_pairs"]:
            control = self.candidates[control_name]
            imatrix = self.candidates[imatrix_name]
            self.assertEqual(control["base_quantization"], imatrix["base_quantization"])
            self.assertFalse(control["uses_imatrix"])
            self.assertTrue(imatrix["uses_imatrix"])
            self.assertNotIn("--imatrix", control["argv_after_binary"])
            self.assertIn("--imatrix", imatrix["argv_after_binary"])

    def test_mixed_recipes_retain_explicit_overrides(self) -> None:
        mixed = [
            item
            for item in self.candidates.values()
            if item["role"] == "predefined mixed-tensor candidate"
        ]
        self.assertEqual(len(mixed), 3)
        self.assertTrue(
            all(
                "--tensor-type" in item["argv_after_binary"]
                or "--output-tensor-type" in item["argv_after_binary"]
                for item in mixed
            )
        )


if __name__ == "__main__":
    unittest.main()
