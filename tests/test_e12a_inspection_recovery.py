import unittest
from pathlib import Path

from experiments.e12a_inspection_recovery_freeze import build_contract
from experiments.e12a_inspection_recovery_ingest import validate_inspection_command


class E12aInspectionRecoveryTests(unittest.TestCase):
    def test_freeze_binds_completed_bytes_without_recompute(self) -> None:
        contract = build_contract(Path("."))
        self.assertEqual(contract["experiment_id"], "E12a-inspection-recovery")
        self.assertFalse(contract["inspection"]["matrix_recomputation_allowed"])
        self.assertFalse(contract["inspection"]["matrix_mutation_allowed"])
        self.assertEqual(contract["acceptance"]["required_final_chunks"], 32)
        self.assertEqual(contract["acceptance"]["required_imatrix_entries"], 182)
        self.assertEqual(
            contract["acceptance"]["required_final_sha256"],
            "2338867f1b51341e02d0f63ca4d7281731a94b0738d80413476581ae991a1548",
        )

    def test_statistics_command_adds_only_required_model(self) -> None:
        contract = {
            "inspection": {
                "statistics_argv_after_binary": [
                    "--model",
                    "MODEL_PATH",
                    "--in-file",
                    "MATRIX_PATH",
                    "--show-statistics",
                    "--ctx-size",
                    "512",
                    "--threads",
                    "4",
                ]
            }
        }
        command = {
            "argv": [
                "/build/bin/llama-imatrix",
                "--model",
                "/model.gguf",
                "--in-file",
                "/matrix.gguf",
                "--show-statistics",
                "--ctx-size",
                "512",
                "--threads",
                "4",
            ]
        }
        validate_inspection_command(
            command,
            contract,
            model_path="/model.gguf",
            matrix_path="/matrix.gguf",
        )
        command["argv"].extend(["--chunks", "8"])
        with self.assertRaisesRegex(ValueError, "differs from the frozen contract"):
            validate_inspection_command(
                command,
                contract,
                model_path="/model.gguf",
                matrix_path="/matrix.gguf",
            )


if __name__ == "__main__":
    unittest.main()
