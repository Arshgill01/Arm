import unittest

from experiments.e9c_ingest import build_policy, summarize_point
from experiments.e9c_probe import (
    longest_common_prefix,
    parse_prediction,
    system_text,
)


class E9cProbeTests(unittest.TestCase):
    def test_longest_common_prefix_stops_at_first_variant(self) -> None:
        self.assertEqual(
            longest_common_prefix([[1, 2, 3, 7], [1, 2, 3, 8], [1, 2, 3, 9]]),
            3,
        )

    def test_prediction_requires_a_standalone_letter(self) -> None:
        self.assertEqual(parse_prediction("  b\n"), "B")
        self.assertIsNone(parse_prediction("Answer: B"))
        self.assertIsNone(parse_prediction("AB"))
        self.assertIsNone(parse_prediction(None))

    def test_system_text_has_deterministic_single_space_boundaries(self) -> None:
        self.assertEqual(
            system_text(2, "alpha", "Choose."),
            "Cache cache cache alpha. Choose.",
        )


class E9cPolicyTests(unittest.TestCase):
    @staticmethod
    def cell(cache_prompt: bool, repetition: int, requests_per_second: float) -> dict:
        return {
            "cache_prompt": cache_prompt,
            "repetition": repetition,
            "requests_per_second": requests_per_second,
            "server_process_cpu": {"seconds_per_request": 0.9 if cache_prompt else 1.0},
            "ready_ms": 100.0,
            "process": {"maximum_rss_kib": 1000},
            "failures": 0,
            "reference_prediction_mismatches": 0,
        }

    @staticmethod
    def cases(cache_prompt: bool) -> list[dict]:
        return [
            {
                "prediction": "A",
                "http_ms": 90.0 if cache_prompt else 100.0,
                "encode_ms": 8.0 if cache_prompt else 10.0,
                "decode_ms": 20.0,
                "cached_tokens": 32 if cache_prompt else 0,
                "evaluated_prompt_tokens": 40 if cache_prompt else 72,
                "prompt_tokens": 72,
            }
            for _ in range(16)
        ]

    def test_point_requires_every_frozen_gate(self) -> None:
        cells = [
            self.cell(False, 1, 10.0),
            self.cell(True, 1, 11.0),
            self.cell(True, 2, 11.2),
            self.cell(False, 2, 10.2),
        ]
        samples = {
            (cache, repetition): self.cases(cache)
            for cache in (False, True)
            for repetition in (1, 2)
        }
        contract = {
            "validity": {
                "required_cache_off_tokens_per_request": 0,
                "maximum_throughput_coefficient_of_variation": 0.05,
            },
            "break_even": {
                "minimum_throughput_ratio": 1.05,
                "minimum_prompt_encode_speedup_ratio": 1.05,
                "maximum_p95_http_latency_ratio": 1.0,
                "maximum_cpu_seconds_per_request_ratio": 1.0,
            },
        }
        point = summarize_point(
            cardinality=2,
            shared_tokens=32,
            cells=cells,
            samples=samples,
            contract=contract,
        )
        self.assertTrue(point["eligible"])
        self.assertTrue(all(point["gates"].values()))

        samples[(True, 2)][0]["prediction"] = "B"
        drifted = summarize_point(
            cardinality=2,
            shared_tokens=32,
            cells=cells,
            samples=samples,
            contract=contract,
        )
        self.assertFalse(drifted["eligible"])
        self.assertFalse(drifted["gates"]["paired_cache_outputs_equal"])

    def test_no_eligible_point_disables_cache(self) -> None:
        self.assertEqual(
            build_policy([], [16, 32, 64]),
            {"mode": "disabled", "eligible_shared_prefix_tokens": []},
        )

    def test_monotone_suffix_emits_minimum_threshold(self) -> None:
        self.assertEqual(
            build_policy([64, 32], [16, 32, 64]),
            {
                "mode": "minimum_shared_prefix_tokens",
                "minimum_shared_prefix_tokens": 32,
                "eligible_shared_prefix_tokens": [32, 64],
            },
        )

    def test_non_monotone_result_emits_only_tested_allowlist(self) -> None:
        self.assertEqual(
            build_policy([16, 64], [16, 32, 64]),
            {
                "mode": "tested_lengths_only",
                "eligible_shared_prefix_tokens": [16, 64],
            },
        )


if __name__ == "__main__":
    unittest.main()
