import json
import tempfile
import unittest
from pathlib import Path

from experiments.e5b_ingest import sha256_file
from experiments.e12b_actual_cell import render, sha256_bytes
from experiments.e12b_actual_freeze import INPUT_PATHS
from experiments.e12b_actual_ingest import ARTIFACT_INPUTS, validate_actual_e12a


class E12bActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = Path("experiments/e12b_cell.sh").read_text()
        cls.rendered = render(cls.source)

    def test_render_uses_safe_probe_and_actual_ingester(self) -> None:
        self.assertIn("experiments/e10f_probe.py", self.rendered)
        self.assertIn("experiments/e12b_actual_ingest.py cell", self.rendered)
        self.assertIn("tests.test_e12b_actual", self.rendered)
        self.assertNotIn("experiments/e10d_probe.py", self.rendered)
        self.assertEqual(
            sha256_bytes(render(self.source).encode()),
            sha256_bytes(self.rendered.encode()),
        )

    def test_every_actual_input_has_an_artifact_copy(self) -> None:
        self.assertTrue(set(INPUT_PATHS).issubset(ARTIFACT_INPUTS))
        self.assertEqual(
            set(ARTIFACT_INPUTS) - set(INPUT_PATHS),
            {"e11a_recovery_contract", "e11a_recovery_summary"},
        )

    def test_retained_workflow_summary_is_exact_artifact_bytes(self) -> None:
        path = Path(
            "results/manifests/e12a-metadata-recovery-workflow-30855550027.json"
        )
        self.assertEqual(
            sha256_file(path),
            "acd97619bacbb37667079feec2f622ba67eda4240e11426ed2540eb0738b109d",
        )

    def test_workflow_dispatches_exact_frozen_candidate_set(self) -> None:
        workflow = Path(
            ".github/workflows/application-imatrix-quant-frontier-actual.yml"
        ).read_text()
        plan = json.loads(Path("experiments/e12b_plan.json").read_text())
        for candidate in plan["candidates"]:
            self.assertEqual(
                workflow.count(f"          - {candidate['candidate']}\n"), 1
            )
        self.assertIn(
            "python3 experiments/e12b_actual_cell.py --root", workflow
        )
        self.assertIn("experiments/e12b_actual_ingest.py aggregate", workflow)
        self.assertIn("test \"${#summaries[@]}\" -eq 9", workflow)
        self.assertNotIn("continue-on-error", workflow)

    def test_actual_e12a_validation_accepts_false_recovery_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            (evidence / "e12a").mkdir()
            imatrix = evidence / "e12a/imatrix.gguf"
            imatrix.write_bytes(b"fixture")
            summary = {
                "status": "valid_application_conditioned_imatrix_metadata_recovery",
                "contract_sha256": "contract",
                "imatrix": {
                    "sha256": sha256_file(imatrix),
                    "size_bytes": imatrix.stat().st_size,
                },
                "validation": {
                    name: True
                    for name in (
                        "native_arm64",
                        "exact_retained_statistics",
                        "exact_source_artifact_inventory",
                        "matrix_bytes_unchanged",
                        "ordered_dataset_metadata",
                        "complete_chunk_count",
                        "entry_names_match_checkpoint",
                        "gguf_metadata_valid",
                        "generated_quant_dispatch_allowed",
                    )
                },
            }
            summary["validation"].update(
                {
                    "matrix_recomputed": False,
                    "native_tool_rebuilt": False,
                    "model_downloaded": False,
                }
            )
            summary_path = evidence / "e12a/summary.json"
            summary_path.write_text(json.dumps(summary))
            contract = {
                "prerequisites": {
                    "e12a": {
                        "summary_sha256": sha256_file(summary_path),
                        "required_status": summary["status"],
                        "contract_sha256": "contract",
                        "imatrix_sha256": sha256_file(imatrix),
                        "imatrix_size_bytes": imatrix.stat().st_size,
                    }
                }
            }
            observed = validate_actual_e12a(evidence, contract)
            self.assertEqual(observed["imatrix"]["size_bytes"], len(b"fixture"))


if __name__ == "__main__":
    unittest.main()
