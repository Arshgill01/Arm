import json
import unittest
from pathlib import Path

from experiments.e17c_failure_retain import (
    retain,
    validate_artifact_inventory,
    validate_failed_cells,
)


class E17cFailureRetainTests(unittest.TestCase):
    def test_complete_failure_artifact_when_downloaded(self) -> None:
        evidence = Path(".scratch/e17c-30867998030")
        if not evidence.exists():
            self.skipTest("downloaded E17c artifact is unavailable")
        inventory = validate_artifact_inventory(evidence)
        self.assertEqual(inventory["file_count"], 144)
        contract = json.loads(Path("experiments/e17c_contract.json").read_text())
        cells = validate_failed_cells(evidence, contract)
        self.assertEqual(len(cells), 9)
        self.assertTrue(all(not cell["probe_written"] for cell in cells))

    def test_complete_failure_retention_when_downloaded(self) -> None:
        evidence = Path(".scratch/e17c-30867998030")
        failed_log = Path(".scratch/e17c-failed.log")
        if not evidence.exists() or not failed_log.exists():
            self.skipTest("downloaded E17c evidence is unavailable")
        result = retain(
            evidence=evidence,
            contract_path=Path("experiments/e17c_contract.json"),
            root=Path("."),
            run_metadata=evidence / "run-metadata.json",
            artifact_metadata=evidence / "artifact-metadata.json",
            failed_log=failed_log,
        )
        self.assertFalse(result["decision"]["kv_density_claim_allowed"])
        self.assertTrue(result["decision"]["eight_k_lane_parked"])

    def test_retained_manifest_contains_no_kv_claim(self) -> None:
        path = Path("results/manifests/e17c-30867998030-failure.json")
        if not path.exists():
            self.skipTest("E17c failure manifest has not been generated")
        result = json.loads(path.read_text())
        self.assertEqual(
            result["status"], "invalid_8k_context_timing_schema_no_kv_claim"
        )
        self.assertFalse(result["decision"]["quality_claim_allowed"])
        self.assertFalse(result["decision"]["successor_or_rerun_authorized"])


if __name__ == "__main__":
    unittest.main()
