import tempfile
import unittest
from pathlib import Path

from experiments.e18a_ingestion_recovery import validate_inventory
from experiments.e18a_ingestion_recovery_freeze import build_contract
from experiments.e5b_ingest import sha256_file


class E18aIngestionRecoveryTests(unittest.TestCase):
    def test_contract_is_inspection_only_and_keeps_no_win(self) -> None:
        contract = build_contract(Path("."))
        self.assertEqual(contract["expected_result"]["status"], "valid_workload_pgo_no_win")
        self.assertFalse(contract["expected_result"]["hypothesis_passed"])
        self.assertEqual(
            contract["expected_result"]["selected_profile"], "release_control"
        )
        self.assertIn("rerun any service cell", contract["execution"]["forbidden_operations"])
        self.assertNotIn("launch llama-server", contract["execution"]["allowed_operations"])
        self.assertFalse(contract["decision"]["failed_workflow_rehabilitated"])

    def test_contract_is_deterministic(self) -> None:
        self.assertEqual(build_contract(Path(".")), build_contract(Path(".")))

    def test_source_inventory_rejects_an_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            retained_path = root / "retained.txt"
            retained_path.write_text("retained\n")
            retained = {
                "file_count": 1,
                "total_regular_file_bytes": retained_path.stat().st_size,
                "files": [
                    {
                        "path": "retained.txt",
                        "size_bytes": retained_path.stat().st_size,
                        "sha256": sha256_file(retained_path),
                    }
                ],
            }
            self.assertTrue(
                validate_inventory(root, retained)[
                    "all_extracted_regular_files_verified"
                ]
            )
            (root / "extra.txt").write_text("extra\n")
            with self.assertRaisesRegex(ValueError, "file set"):
                validate_inventory(root, retained)


if __name__ == "__main__":
    unittest.main()
