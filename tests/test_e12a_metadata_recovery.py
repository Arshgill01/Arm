import unittest
from pathlib import Path

from experiments.e12a_metadata_recovery_freeze import build_contract
from experiments.e12a_metadata_recovery_ingest import validate_command


class E12aMetadataRecoveryTests(unittest.TestCase):
    def test_freeze_allows_only_metadata_dump(self) -> None:
        contract = build_contract(Path("."))
        self.assertFalse(contract["metadata"]["matrix_recomputation_allowed"])
        self.assertFalse(contract["metadata"]["statistics_repetition_allowed"])
        self.assertFalse(contract["metadata"]["native_tool_rebuild_allowed"])
        self.assertFalse(contract["metadata"]["model_download_allowed"])
        self.assertEqual(contract["acceptance"]["required_final_chunks"], 32)
        self.assertEqual(contract["acceptance"]["required_imatrix_entries"], 182)

    def test_command_is_exact_metadata_read(self) -> None:
        contract = {
            "metadata": {
                "command_after_python": [
                    "-m",
                    "gguf.scripts.gguf_dump",
                    "MATRIX_PATH",
                    "--json",
                    "--json-array",
                ]
            }
        }
        command = {
            "argv": [
                "/venv/bin/python",
                "-m",
                "gguf.scripts.gguf_dump",
                "/matrix.gguf",
                "--json",
                "--json-array",
            ]
        }
        validate_command(command, contract, matrix_path="/matrix.gguf")
        command["argv"].append("--show-statistics")
        with self.assertRaisesRegex(ValueError, "differs from the frozen contract"):
            validate_command(command, contract, matrix_path="/matrix.gguf")


if __name__ == "__main__":
    unittest.main()
