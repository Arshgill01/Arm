import json
import sys
import unittest
from pathlib import Path

from experiments.e11b_artifact_retain import (
    retain,
    validate_artifact_inventory,
)


class E11bArtifactRetainTests(unittest.TestCase):
    def test_complete_source_inventory_when_downloaded(self) -> None:
        evidence = Path(".scratch/e11b-30869286295")
        if not evidence.exists():
            self.skipTest("downloaded E11b artifact is unavailable")
        contract = json.loads(Path("experiments/e11b_contract.json").read_text())
        inventory = validate_artifact_inventory(evidence, contract)
        self.assertEqual(inventory["file_count"], 566)
        self.assertEqual(inventory["fresh_process_cells"], 40)
        self.assertEqual(inventory["cell_files"], 520)

    def test_complete_recovery_when_downloaded(self) -> None:
        if sys.version_info[:3] != (3, 10, 20):
            self.skipTest("complete E11b replay requires Python 3.10.20")
        evidence = Path(".scratch/e11b-30869286295")
        if not evidence.exists():
            self.skipTest("downloaded E11b artifact is unavailable")
        result = retain(
            evidence=evidence,
            contract_path=Path("experiments/e11b_contract.json"),
            root=Path("."),
            run_metadata=evidence / "run-metadata.json",
            artifact_metadata=evidence / "artifact-metadata.json",
        )
        self.assertFalse(result["campaign_decision"]["e11b_native_rerun_required"])
        self.assertTrue(result["artifact_recovery"]["complete_retained_matrix_replayed"])

    def test_retained_manifest_has_no_product_promotion(self) -> None:
        path = Path("results/manifests/e11b-30869286295-recovered.json")
        if not path.exists():
            self.skipTest("E11b recovered manifest has not been generated")
        result = json.loads(path.read_text())
        self.assertEqual(result["status"], "valid_stock_quant_service_frontier")
        self.assertFalse(result["campaign_decision"]["product_promotion_made"])
        self.assertTrue(result["artifact_recovery"]["source_workflow_remains_failed"])


if __name__ == "__main__":
    unittest.main()
