from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from experiments.e6f_ingest import expected_server_argv
from experiments.e7a_ingest import evaluate_hypothesis, validate_recipe

ROOT = Path(__file__).resolve().parents[1]


class E7aIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e7a_contract.json").read_text())

    def profile(
        self,
        throughput: float,
        *,
        median: float = 1000.0,
        p95: float = 1800.0,
        cpu: float = 4.0,
        ready: float = 4000.0,
        rss: float = 2_400_000.0,
        exact: bool = True,
    ) -> dict:
        return {
            "quality": {"exact_selected_predictions": exact},
            "requests_per_second": {"median": throughput},
            "http_ms": {"median": median, "p95": p95},
            "server_cpu_seconds_per_request": {"median": cpu},
            "ready_ms": {"median": ready},
            "maximum_rss_kib": {"max": rss},
        }

    @staticmethod
    def builds(candidate_closure: int, candidate_seconds: float = 150.0) -> dict:
        return {
            "lto_off": {
                "runtime_closure": {"total_size_bytes": 100_000_000},
                "build_process": {"elapsed_seconds": 100.0},
            },
            "lto_on": {
                "runtime_closure": {"total_size_bytes": candidate_closure},
                "build_process": {"elapsed_seconds": candidate_seconds},
            },
        }

    def evaluate(self, performance: dict, builds: dict) -> dict:
        return evaluate_hypothesis(
            performance,
            builds,
            self.contract["acceptance"],
            "lto_off",
            "lto_on",
        )

    def recipe(self, profile_name: str) -> dict:
        selected = self.contract["selected"]
        server = f"/tmp/{profile_name}/bin/llama-server"
        model = "/tmp/models/selected/model.gguf"
        return {
            "schema_version": 1,
            "experiment_id": "E7a",
            "profile_name": profile_name,
            "build_profile": self.contract["build"]["profiles"][profile_name],
            "runtime": self.contract["runtime"],
            "server_path": server,
            "server_version": f"version ({self.contract['runtime']['commit'][:9]})",
            "model": {
                "path": model,
                "sha256": selected["model_sha256"],
                "size_bytes": selected["model_size_bytes"],
            },
            "service": self.contract["service"],
            "argv": expected_server_argv(
                server,
                model,
                candidate=selected["candidate"],
                service=self.contract["service"],
            ),
        }

    def test_contract_is_balanced_single_difference_ablation(self) -> None:
        execution = self.contract["execution"]
        self.assertEqual(
            ["lto_off", "lto_on", "lto_on", "lto_off"],
            [item["profile"] for item in execution["order"]],
        )
        profiles = self.contract["build"]["profiles"]
        self.assertFalse(profiles["lto_off"]["ggml_lto"])
        self.assertTrue(profiles["lto_on"]["ggml_lto"])
        self.assertIn("-flto", profiles["lto_on"]["required_command_patterns"])
        self.assertIn("-flto", profiles["lto_off"]["forbidden_command_patterns"])
        self.assertFalse(self.contract["selection_policy"]["weighted_score_used"])
        self.assertIn("energy", self.contract["claim_boundary"].lower())

    def test_recipe_binds_lto_profile_and_fast_service(self) -> None:
        for profile_name in self.contract["build"]["profiles"]:
            recipe = self.recipe(profile_name)
            self.assertNotIn("--no-repack", recipe["argv"])
            validate_recipe(recipe, profile_name, self.contract)

        invalid = copy.deepcopy(self.recipe("lto_on"))
        invalid["build_profile"]["ggml_lto"] = False
        with self.assertRaisesRegex(ValueError, "recipe differs"):
            validate_recipe(invalid, "lto_on", self.contract)

    def test_performance_branch_can_select_lto(self) -> None:
        performance = {
            "lto_off": self.profile(1.0),
            "lto_on": self.profile(
                1.04,
                median=1010,
                p95=1810,
                cpu=4.02,
                ready=4040,
                rss=2_410_000,
            ),
        }
        result = self.evaluate(performance, self.builds(101_000_000))
        self.assertTrue(result["passed"])
        self.assertTrue(result["performance_branch_passed"])
        self.assertFalse(result["footprint_branch_passed"])
        self.assertEqual("lto_on", result["selected_profile"])

    def test_footprint_branch_can_select_lto(self) -> None:
        performance = {
            "lto_off": self.profile(1.0),
            "lto_on": self.profile(0.99),
        }
        result = self.evaluate(performance, self.builds(94_000_000))
        self.assertTrue(result["passed"])
        self.assertFalse(result["performance_branch_passed"])
        self.assertTrue(result["footprint_branch_passed"])

    def test_no_benefit_or_common_guardrail_failure_keeps_baseline(self) -> None:
        no_benefit = {
            "lto_off": self.profile(1.0),
            "lto_on": self.profile(1.01),
        }
        result = self.evaluate(no_benefit, self.builds(98_000_000))
        self.assertFalse(result["passed"])
        self.assertEqual("lto_off", result["selected_profile"])

        cpu_regression = copy.deepcopy(no_benefit)
        cpu_regression["lto_on"] = self.profile(1.04, cpu=4.3)
        result = self.evaluate(cpu_regression, self.builds(101_000_000))
        self.assertTrue(result["performance_branch_passed"])
        self.assertFalse(result["cpu_time_guardrail_passed"])
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
