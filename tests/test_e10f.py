import unittest

from experiments.e10f_freeze import build_plan
from experiments.e10f_probe import scoring_request


class E10fProbeTests(unittest.TestCase):
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
        self.assertFalse(
            plan["decision"]["original_e10d_rewrite_allowed"]
        )
        self.assertEqual(plan["safe_sampling"]["token_id"], 1046)
        self.assertEqual(
            plan["workload"]["expected_summary"]["token_score_requests"],
            14374,
        )
        self.assertEqual(
            plan["prerequisites"]["e10e"]["required_status"],
            "valid_probability_api_compatibility_preflight",
        )


if __name__ == "__main__":
    unittest.main()
