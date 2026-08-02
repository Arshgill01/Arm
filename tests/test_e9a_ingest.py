from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from experiments.e9a_ingest import (
    evaluate_hypothesis,
    expected_server_argv,
    validate_recipe,
)

ROOT = Path(__file__).resolve().parents[1]


class E9aIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e9a_contract.json").read_text())

    @staticmethod
    def profile(
        throughput: float,
        *,
        median_ms: float,
        p95_ms: float,
        cpu_seconds: float,
        cached_min: float,
        cached_max: float,
        exact: bool = True,
        cv: float = 0.01,
    ) -> dict:
        return {
            "quality": {"exact_selected_predictions": exact},
            "requests_per_second": {
                "median": throughput,
                "coefficient_of_variation": cv,
            },
            "http_ms": {"median": median_ms, "p95": p95_ms},
            "server_cpu_seconds_per_request": {"median": cpu_seconds},
            "cached_tokens": {"min": cached_min, "max": cached_max},
            "ready_ms": {"median": 4000.0},
            "maximum_rss_kib": {"max": 4_500_000.0},
        }

    def recipe(self, profile_name: str) -> dict:
        selected = self.contract["selected"]
        profile = self.contract["profiles"][profile_name]
        server = f"/tmp/{profile_name}/bin/llama-server"
        model = "/tmp/models/selected.gguf"
        return {
            "schema_version": 1,
            "experiment_id": "E9a",
            "profile_name": profile_name,
            "source": profile["source"],
            "build": profile["build"],
            "service": profile["service"],
            "server_path": server,
            "server_version": f"version ({profile['source']['commit'][:9]})",
            "model": {
                "path": model,
                "sha256": selected["model_sha256"],
                "size_bytes": selected["model_size_bytes"],
            },
            "argv": expected_server_argv(
                server,
                model,
                candidate=selected["candidate"],
                profile_name=profile_name,
            ),
        }

    def test_contract_freezes_reverse_balanced_four_repetition_matrix(self) -> None:
        execution = self.contract["execution"]
        self.assertEqual(4, execution["repetitions_per_profile"])
        self.assertEqual(
            [
                "e5b_earliest",
                "e7c_final",
                "e7c_final",
                "e5b_earliest",
                "e7c_final",
                "e5b_earliest",
                "e5b_earliest",
                "e7c_final",
            ],
            [item["profile"] for item in execution["order"]],
        )
        self.assertIn("compounded", self.contract["claim_boundary"].lower())
        self.assertFalse(self.contract["selection_policy"]["weighted_score_used"])

    def test_historical_service_argv_are_distinct_and_exact(self) -> None:
        baseline = self.recipe("e5b_earliest")
        final = self.recipe("e7c_final")
        validate_recipe(baseline, "e5b_earliest", self.contract)
        validate_recipe(final, "e7c_final", self.contract)
        self.assertIn("--no-cache-prompt", baseline["argv"])
        self.assertNotIn("--batch-size", baseline["argv"])
        self.assertNotIn("--cache-type-k", baseline["argv"])
        self.assertIn("--cache-prompt", final["argv"])
        self.assertEqual("64", final["argv"][final["argv"].index("--batch-size") + 1])
        self.assertEqual("256", final["argv"][final["argv"].index("--ctx-size") + 1])

        invalid = copy.deepcopy(baseline)
        invalid["argv"].extend(["--batch-size", "2048"])
        with self.assertRaisesRegex(ValueError, "historical recipe"):
            validate_recipe(invalid, "e5b_earliest", self.contract)

    def test_passing_compounded_result_requires_every_frozen_gate(self) -> None:
        performance = {
            "e5b_earliest": self.profile(
                0.5,
                median_ms=1800.0,
                p95_ms=2600.0,
                cpu_seconds=7.0,
                cached_min=0.0,
                cached_max=0.0,
            ),
            "e7c_final": self.profile(
                0.9,
                median_ms=1050.0,
                p95_ms=1800.0,
                cpu_seconds=4.2,
                cached_min=24.0,
                cached_max=92.0,
            ),
        }
        result = evaluate_hypothesis(performance, self.contract)
        self.assertTrue(result["passed"])
        self.assertGreater(result["throughput_ratio"], 1.25)

        noisy = copy.deepcopy(performance)
        noisy["e7c_final"]["requests_per_second"]["coefficient_of_variation"] = 0.06
        result = evaluate_hypothesis(noisy, self.contract)
        self.assertFalse(result["passed"])
        self.assertFalse(result["scheduler_dispersion_gate_passed"])

        drift = copy.deepcopy(performance)
        drift["e7c_final"]["quality"]["exact_selected_predictions"] = False
        self.assertFalse(evaluate_hypothesis(drift, self.contract)["passed"])


if __name__ == "__main__":
    unittest.main()
