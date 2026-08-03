import argparse
import unittest

from experiments.e10e_probability_preflight import (
    parse_case,
    select_request,
    selected_probability,
)
from experiments.e10e_probability_ingest import (
    compare_variants,
    validate_attempt_probability,
)
from experiments.e10e_freeze import select_prepared_case


class E10ePreflightTests(unittest.TestCase):
    def test_case_parser_is_fail_closed(self) -> None:
        self.assertEqual(parse_case("task:44:1"), ("task", 44, 1))
        for value in ("task:44", "task:no:1", "task:-1:0"):
            with self.assertRaises(argparse.ArgumentTypeError):
                parse_case(value)

    def test_selected_probability_requires_the_exact_requested_id(self) -> None:
        response = {
            "completion_probabilities": [
                {"selected_logprobs": [{"id": 17, "logprob": -1.25}]}
            ]
        }
        self.assertEqual(selected_probability(response, 17)["status"], "ok")
        self.assertEqual(
            selected_probability({"completion_probabilities": []}, 17)["status"],
            "missing_probability_entry",
        )
        self.assertEqual(
            selected_probability(response, 18)["status"],
            "invalid_selected_probability",
        )

    def test_ingest_rebinds_selected_probability_to_raw_response(self) -> None:
        raw = {
            "completion_probabilities": [
                {"selected_logprobs": [{"id": 17, "logprob": -1.25}]}
            ]
        }
        attempt = {
            "status": "ok",
            "target_token_id": 17,
            "selected_logprob": -1.25,
        }
        validate_attempt_probability(raw, attempt)
        with self.assertRaises(ValueError):
            validate_attempt_probability(raw, {**attempt, "selected_logprob": -2.0})
        validate_attempt_probability(
            {"completion_probabilities": []},
            {
                "status": "missing_probability_entry",
                "target_token_id": 17,
                "selected_logprob": None,
            },
        )

    def test_request_selection_binds_task_sample_and_choice(self) -> None:
        selected = {
            "task": "held",
            "sample_ordinal": 44,
            "source_index": 3681,
            "choice_index": 1,
            "candidate_tokens": [4],
        }
        prepared = {"cases": [selected]}
        self.assertEqual(
            select_request(prepared, ("held", 44, 1)), (selected, selected)
        )
        with self.assertRaises(ValueError):
            select_request(prepared, ("held", 45, 1))

    def test_freezer_binds_failure_to_exact_prepared_token(self) -> None:
        request = {
            "choice_index": 1,
            "prompt_sha256": "a" * 64,
            "candidate_sha256": "b" * 64,
            "prompt_tokens": [1, 2],
            "candidate_tokens": [7, 8, 9],
        }
        prepared = {
            "tasks": [
                {
                    "task": "held",
                    "samples": [
                        {
                            "sample_ordinal": 44,
                            "source_index": 3681,
                            "source_document_sha256": "c" * 64,
                            "requests": [request],
                        }
                    ],
                }
            ]
        }
        failure = {
            "task": "held",
            "sample_ordinal": 44,
            "source_index": 3681,
            "failed_choice_index": 1,
            "failed_token_index": 2,
            "failed_target_token_id": 9,
            "candidate_token_count": 3,
            "retained_partial_token_responses": 2,
            "failure_response_received_but_not_retained": True,
        }
        selected = select_prepared_case(prepared, failure)
        self.assertEqual(selected["candidate_tokens"], [7, 8, 9])
        self.assertEqual(selected["original_missing_target_token_id"], 9)
        with self.assertRaises(ValueError):
            select_prepared_case(
                prepared, {**failure, "failed_target_token_id": 10}
            )

    def test_variant_comparison_uses_only_observed_original_prefix(self) -> None:
        key = "held|44|1"
        variants = {
            "original": {
                "cases": {
                    key: {
                        "attempts": [
                            {"selected_logprob": -1.0},
                            {"selected_logprob": None},
                        ]
                    }
                }
            },
            "forced_safe_1": {
                "cases": {
                    key: {
                        "attempts": [
                            {"selected_logprob": -1.0},
                            {"selected_logprob": -2.0},
                        ]
                    }
                }
            },
            "forced_safe_2": {
                "cases": {
                    key: {
                        "attempts": [
                            {"selected_logprob": -1.0},
                            {"selected_logprob": -2.0},
                        ]
                    }
                }
            },
        }
        plan = {
            "cases": [
                {"task": "held", "sample_ordinal": 44, "choice_index": 1}
            ],
            "acceptance": {
                "maximum_prefailure_logprob_delta": 0.0,
                "maximum_repeat_logprob_delta": 0.0,
            },
        }
        self.assertEqual(
            compare_variants(variants, plan),
            {
                "maximum_original_vs_forced_safe_prefailure_logprob_delta": 0.0,
                "maximum_forced_safe_repeat_logprob_delta": 0.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
