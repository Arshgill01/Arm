import json
import tempfile
import unittest
from pathlib import Path

from experiments.e5b_ingest import sha256_file
from experiments.e12b_successor_cell import render, sha256_bytes
from experiments.e12b_successor_freeze import (
    INPUT_PATHS,
    build_contract,
    require_validation,
)
from experiments.e12b_successor_ingest import SUCCESSOR_ARTIFACT_INPUTS


class E12bSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = Path("experiments/e12b_cell.sh").read_text()
        cls.rendered = render(cls.source)
        cls.plan = json.loads(Path("experiments/e12b_plan.json").read_text())
        cls.safe = json.loads(Path("experiments/e10f_contract.json").read_text())

    def test_render_changes_only_three_fail_closed_boundaries(self) -> None:
        self.assertIn("experiments/e10f_probe.py", self.rendered)
        self.assertNotIn("experiments/e10d_probe.py", self.rendered)
        self.assertIn("experiments/e12b_successor_ingest.py cell", self.rendered)
        self.assertIn("tests.test_e12b_successor", self.rendered)
        with self.assertRaises(ValueError):
            render(self.source.replace("experiments/e10d_probe.py", "drift.py"))

    def test_render_digest_is_deterministic(self) -> None:
        expected = sha256_bytes(self.rendered.encode())
        self.assertEqual(sha256_bytes(render(self.source).encode()), expected)
        self.assertEqual(len(expected), 64)

    def test_original_nine_recipes_and_pairs_remain_frozen(self) -> None:
        self.assertEqual(len(self.plan["candidates"]), 9)
        self.assertEqual(len(self.plan["matched_pairs"]), 3)
        self.assertEqual(
            sum(item["uses_imatrix"] for item in self.plan["candidates"]), 6
        )

    def test_safe_transport_retains_exact_workload(self) -> None:
        self.assertEqual(self.safe["experiment_id"], "E10f")
        self.assertEqual(self.safe["safe_sampling"]["token_id"], 1046)
        self.assertEqual(self.safe["safe_sampling"]["token_text"], ".")
        self.assertEqual(
            self.safe["workload"]["expected_summary"]["token_score_requests"],
            14374,
        )
        self.assertFalse(
            self.safe["scoring"]["probe_parameters"]["sampled_output_used_for_score"]
        )

    def test_successor_artifact_inventory_covers_bound_execution_inputs(self) -> None:
        expected = set(SUCCESSOR_ARTIFACT_INPUTS)
        self.assertTrue(expected.issubset(INPUT_PATHS))
        self.assertIn("successor_wrapper", expected)
        self.assertIn("safe_probe", expected)
        self.assertIn("safe_manifest", expected)

    def test_required_validation_fails_closed(self) -> None:
        require_validation({"validation": {"a": True}}, ("a",), "fixture")
        with self.assertRaises(ValueError):
            require_validation({"validation": {"a": False}}, ("a",), "fixture")

    def test_contract_freezer_binds_completed_prerequisites_before_outcomes(
        self,
    ) -> None:
        root = Path(".")
        safe_manifest = json.loads(
            Path("results/manifests/e10f-30829237582.json").read_text()
        )
        stock_contract_sha = sha256_file(
            Path("experiments/e11a_successor_contract.json")
        )
        resume_contract_sha = sha256_file(Path("experiments/e12a_resume_contract.json"))
        with tempfile.TemporaryDirectory() as directory:
            scratch = Path(directory)
            imatrix = scratch / "imatrix.gguf"
            imatrix.write_bytes(b"fixture-imatrix")
            e12a = {
                "status": "valid_resumed_application_conditioned_imatrix",
                "contract_sha256": resume_contract_sha,
                "decision": {
                    "resume_success_authorizes_generated_quant_successor": True
                },
                "imatrix": {
                    "sha256": sha256_file(imatrix),
                    "size_bytes": imatrix.stat().st_size,
                    "metadata": {"entries": 182, "chunk_count": 32},
                },
                "validation": {
                    key: True
                    for key in (
                        "native_arm64",
                        "exact_source_build_model",
                        "exact_checkpoint_identity",
                        "deterministic_frozen_corpus",
                        "holdouts_excluded",
                        "ordered_chunk_24_resume",
                        "complete_chunk_count",
                        "entry_names_match_checkpoint",
                        "gguf_metadata_valid",
                        "statistics_retained",
                    )
                },
            }
            e11a = {
                "status": "valid_safe_sampled_stock_quant_quality_ladder",
                "contract_sha256": stock_contract_sha,
                "prepared_sha256": safe_manifest["prepared_sha256"],
                "models": [{} for _ in range(9)],
                "validation": {
                    key: True
                    for key in (
                        "native_arm64",
                        "same_frozen_workload",
                        "all_candidates_complete",
                        "exact_e10f_anchor_reused_without_rerun",
                        "zero_request_failures",
                        "per_sample_logs_retained",
                        "all_raw_responses_retained_once",
                    )
                },
            }
            e12a_path = scratch / "e12a-summary.json"
            e11a_path = scratch / "e11a-summary.json"
            e12a_path.write_text(json.dumps(e12a))
            e11a_path.write_text(json.dumps(e11a))
            contract = build_contract(
                root,
                e12a_summary_path=e12a_path,
                e12a_imatrix_path=imatrix,
                e12a_run_id="1",
                e12a_artifact="e12a-fixture",
                e11a_summary_path=e11a_path,
                e11a_run_id="2",
                e11a_artifact="e11a-fixture",
            )
        self.assertEqual(contract["experiment_id"], "E12b")
        self.assertEqual(len(contract["candidates"]), 9)
        self.assertEqual(
            contract["execution"]["resolved_cell_runner_sha256"],
            sha256_bytes(self.rendered.encode()),
        )
        self.assertEqual(
            contract["prerequisites"]["e10f"]["prepared_sha256"],
            contract["workload"]["prepared_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
