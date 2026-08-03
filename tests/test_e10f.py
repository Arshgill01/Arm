import subprocess
import sys
import unittest
from pathlib import Path
import json

from experiments.e10f_freeze import build_plan
from experiments.e10f_probe import scoring_request


class E10fProbeTests(unittest.TestCase):
    def test_entrypoints_are_directly_runnable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for script in ("e10f_ingest.py", "e10f_retain.py"):
            completed = subprocess.run(
                [sys.executable, str(root / "experiments" / script), "--help"],
                cwd=root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_scoring_request_separates_sampled_and_scored_tokens(self) -> None:
        request = scoring_request(
            prefix=[1, 2],
            target_token=1194,
            token_index=0,
            seed=424242,
            safe_token_id=1046,
            safe_logit_bias=100.0,
        )
        self.assertEqual(request["probability_ids"], [1194])
        self.assertEqual(request["logit_bias"], [[1046, 100.0]])
        self.assertFalse(request["post_sampling_probs"])
        self.assertFalse(request["cache_prompt"])
        self.assertEqual(request["n_predict"], 1)

    def test_later_target_reuses_only_its_explicit_prefix(self) -> None:
        request = scoring_request(
            prefix=[1, 2, 1194],
            target_token=1190,
            token_index=1,
            seed=424242,
            safe_token_id=1046,
            safe_logit_bias=100.0,
        )
        self.assertEqual(request["prompt"], [1, 2, 1194])
        self.assertTrue(request["cache_prompt"])

    def test_freezer_preserves_failed_e10d_and_authorizes_only_successor(self) -> None:
        plan = build_plan()
        self.assertEqual(plan["experiment_id"], "E10f")
        self.assertFalse(plan["decision"]["original_e10d_rewrite_allowed"])
        self.assertEqual(plan["safe_sampling"]["token_id"], 1046)
        self.assertEqual(
            plan["workload"]["expected_summary"]["token_score_requests"],
            14374,
        )
        self.assertEqual(
            plan["prerequisites"]["e10e"]["required_status"],
            "valid_probability_api_compatibility_preflight",
        )

    def test_retained_pair_is_valid_but_still_waits_for_imatrix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads(
            (root / "results/manifests/e10f-30829237582.json").read_text()
        )
        self.assertEqual(manifest["status"], "valid_safe_sampled_external_holdout")
        self.assertTrue(manifest["decision"]["supplemental_external_holdout_valid"])
        self.assertTrue(
            manifest["decision"]["e10f_generated_quant_prerequisite_satisfied"]
        )
        self.assertFalse(
            manifest["decision"]["generated_quant_frontier_dispatch_allowed"]
        )
        self.assertEqual(
            [item["request_failures"] for item in manifest["models"]], [0, 0]
        )


if __name__ == "__main__":
    unittest.main()
