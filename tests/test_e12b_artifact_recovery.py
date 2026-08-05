import json
import tempfile
import unittest
from pathlib import Path

from experiments.e12b_artifact_recovery import (
    build_recovered_aggregate,
    select_root_summaries,
)


class E12bArtifactRecoveryTests(unittest.TestCase):
    def test_root_selector_ignores_nested_prerequisite_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = ["control", "imatrix"]
            expected = []
            for candidate in candidates:
                artifact = root / f"e12b-actual-{candidate}-123-1"
                (artifact / "e12a").mkdir(parents=True)
                summary = artifact / "summary.json"
                summary.write_text(json.dumps({"candidate": candidate}))
                (artifact / "e12a/summary.json").write_text("{}")
                expected.append(summary)
            self.assertEqual(
                select_root_summaries(root, candidates, "123"), expected
            )
            self.assertEqual(len(list(root.rglob("summary.json"))), 4)

    def test_root_selector_rejects_extra_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = root / "e12b-actual-control-123-1"
            extra = root / "e12b-actual-extra-123-1"
            expected.mkdir()
            extra.mkdir()
            (expected / "summary.json").write_text("{}")
            (extra / "summary.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "set differs"):
                select_root_summaries(root, ["control"], "123")

    def test_complete_retained_aggregate_when_downloaded(self) -> None:
        root = Path(".scratch/e12b-30869536393/cells")
        if len(list(root.glob("*/summary.json"))) != 9:
            self.skipTest("all nine E12b artifacts are unavailable")
        result = build_recovered_aggregate(
            cells_root=root,
            contract_path=Path("experiments/e12b_contract.json"),
            stock_path=Path(
                "results/manifests/e11a-actual-recovery-30868725586.json"
            ),
            run_id="30869536393",
        )
        self.assertEqual(
            result["status"],
            "valid_safe_sampled_matched_mixed_quant_quality_frontier",
        )
        self.assertEqual(len(result["generated_models"]), 9)


if __name__ == "__main__":
    unittest.main()
