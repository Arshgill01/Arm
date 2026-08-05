import json
import unittest
from pathlib import Path

from experiments.e12b_artifact_retain import retain, validate_workflow_inventory


class E12bArtifactRetainTests(unittest.TestCase):
    def test_one_complete_workflow_inventory_when_downloaded(self) -> None:
        candidate = "e12b_q4_k_s_control"
        evidence = Path(
            ".scratch/e12b-30869536393/cells/"
            f"e12b-actual-{candidate}-30869536393-1"
        )
        if not evidence.exists():
            self.skipTest("downloaded E12b artifact is unavailable")
        result = validate_workflow_inventory(evidence, candidate)
        self.assertEqual(result["workflow_inventory_files"], 14497)
        self.assertEqual(result["raw_responses"], 14374)

    def test_complete_recovery_when_downloaded(self) -> None:
        cells = Path(".scratch/e12b-30869536393/cells")
        if len(list(cells.glob("*/summary.json"))) != 9:
            self.skipTest("all nine E12b artifacts are unavailable")
        result = retain(
            cells_root=cells,
            contract_path=Path("experiments/e12b_contract.json"),
            stock_path=Path(
                "results/manifests/e11a-actual-recovery-30868725586.json"
            ),
            root=Path("."),
            run_metadata=Path(".scratch/e12b-30869536393/run-metadata.json"),
            artifact_metadata=Path(
                ".scratch/e12b-30869536393/artifact-metadata.json"
            ),
        )
        self.assertEqual(result["artifact_recovery"]["root_cell_summaries_selected"], 9)
        self.assertFalse(result["campaign_decision"]["product_promotion_made"])

    def test_retained_manifest_preserves_source_failure(self) -> None:
        path = Path("results/manifests/e12b-30869536393-recovered.json")
        if not path.exists():
            self.skipTest("E12b recovered manifest has not been generated")
        result = json.loads(path.read_text())
        self.assertTrue(result["artifact_recovery"]["source_workflow_remains_failed"])
        self.assertFalse(result["artifact_recovery"]["native_rerun_required"])
        self.assertEqual(len(result["generated_models"]), 9)


if __name__ == "__main__":
    unittest.main()
