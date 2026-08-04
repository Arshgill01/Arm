import tempfile
import unittest
from pathlib import Path

from experiments.e20a_ingestion_recovery import validate_inventory
from experiments.e20a_ingestion_recovery_freeze import build_contract
from experiments.e5b_ingest import sha256_file


class E20aIngestionRecoveryTests(unittest.TestCase):
    def test_contract_keeps_selection_and_forbids_measurement(self) -> None:
        contract = build_contract(Path("."))
        self.assertEqual(
            contract["expected_result"]["selection"]["selected_family"],
            "ffn_gate_up",
        )
        self.assertFalse(
            contract["decision"]["automatic_source_optimization_allowed"]
        )
        self.assertIn(
            "launch llama-bench or llama-server",
            contract["execution"]["forbidden_operations"],
        )

    def test_contract_is_deterministic(self) -> None:
        self.assertEqual(build_contract(Path(".")), build_contract(Path(".")))

    def test_inventory_rejects_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "source.txt"
            path.write_text("source\n")
            retained = {
                "file_count": 1,
                "total_regular_file_bytes": path.stat().st_size,
                "files": [
                    {
                        "path": "source.txt",
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                ],
            }
            self.assertEqual(validate_inventory(root, retained)["file_count"], 1)
            (root / "extra.txt").write_text("extra\n")
            with self.assertRaisesRegex(ValueError, "file set"):
                validate_inventory(root, retained)


if __name__ == "__main__":
    unittest.main()
