from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "e3_score.py"
SPEC = importlib.util.spec_from_file_location("e3_score", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
SCORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCORE)


class E3ScoreTests(unittest.TestCase):
    def test_extract_answer_uses_first_standalone_option(self) -> None:
        self.assertEqual("B", SCORE.extract_answer("The answer is B."))
        self.assertEqual("C", SCORE.extract_answer("c\nBecause..."))
        self.assertIsNone(SCORE.extract_answer("unable to decide"))

    def test_quality_policy_combines_floor_stability_and_best_deficit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            models = {
                "variants": {
                    "best": {"framework": "llama.cpp"},
                    "eligible": {"framework": "MNN"},
                    "below_floor": {"framework": "llama.cpp"},
                }
            }
            tasks = {
                "schema_version": 1,
                "tasks": [
                    {"id": f"task-{index}", "category": "test", "answer": "A"}
                    for index in range(4)
                ],
            }
            models_path = root / "models.json"
            tasks_path = root / "tasks.json"
            models_path.write_text(json.dumps(models))
            tasks_path.write_text(json.dumps(tasks))

            predictions = {
                "best": ["A", "A", "A", "A"],
                "eligible": ["A", "A", "A", "B"],
                "below_floor": ["A", "A", "B", "B"],
            }
            for variant, answers in predictions.items():
                variant_dir = root / "evidence" / "variants" / variant
                variant_dir.mkdir(parents=True)
                framework = models["variants"][variant]["framework"]
                payload = {
                    "schema_version": 1,
                    "framework": framework,
                    "model_path": variant,
                    "cases": [
                        {"id": f"task-{index}", "response": answer}
                        for index, answer in enumerate(answers)
                    ],
                }
                for repetition in range(1, 3):
                    (variant_dir / f"quality-repeat-{repetition}.json").write_text(
                        json.dumps(payload)
                    )

            summary = SCORE.build_summary(
                models_path, tasks_path, root / "evidence"
            )

        self.assertTrue(summary["variants"]["best"]["quality_eligible"])
        self.assertTrue(summary["variants"]["eligible"]["quality_eligible"])
        self.assertFalse(summary["variants"]["below_floor"]["quality_eligible"])


if __name__ == "__main__":
    unittest.main()
