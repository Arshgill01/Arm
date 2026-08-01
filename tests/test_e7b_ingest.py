from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from experiments.e6f_ingest import expected_server_argv
from experiments.e7a_ingest import validate_recipe
from experiments.e7b_ingest import dependency_basenames, evaluate_hypothesis

ROOT = Path(__file__).resolve().parents[1]


class E7bIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e7b_contract.json").read_text())

    @staticmethod
    def profile(
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
    def builds(
        *,
        candidate_dependencies: list[str] | None = None,
        candidate_closure: int = 100_000_000,
        candidate_seconds: float = 100.0,
    ) -> dict:
        common = ["libc.so.6", "libggml.so.0", "libstdc++.so.6"]
        candidate_dependencies = candidate_dependencies or common
        return {
            "openssl_on": {
                "runtime_closure": {"total_size_bytes": 100_000_000},
                "build_process": {"elapsed_seconds": 100.0},
                "dependency_basenames": common + ["libcrypto.so.3", "libssl.so.3"],
                "system_dependency_basenames": [
                    "libc.so.6",
                    "libcrypto.so.3",
                    "libssl.so.3",
                    "libstdc++.so.6",
                ],
            },
            "openssl_off": {
                "runtime_closure": {"total_size_bytes": candidate_closure},
                "build_process": {"elapsed_seconds": candidate_seconds},
                "dependency_basenames": candidate_dependencies,
                "system_dependency_basenames": [
                    name for name in candidate_dependencies if name != "libggml.so.0"
                ],
            },
        }

    def evaluate(self, performance: dict, builds: dict) -> dict:
        return evaluate_hypothesis(
            performance,
            builds,
            self.contract["acceptance"],
            "openssl_on",
            "openssl_off",
        )

    def recipe(self, profile_name: str) -> dict:
        selected = self.contract["selected"]
        server = f"/tmp/{profile_name}/bin/llama-server"
        model = "/tmp/models/selected/model.gguf"
        return {
            "schema_version": 1,
            "experiment_id": "E7b",
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
            ["openssl_on", "openssl_off", "openssl_off", "openssl_on"],
            [item["profile"] for item in execution["order"]],
        )
        profiles = self.contract["build"]["profiles"]
        self.assertTrue(profiles["openssl_on"]["llama_openssl"])
        self.assertFalse(profiles["openssl_off"]["llama_openssl"])
        marker = "CPPHTTPLIB_OPENSSL_SUPPORT"
        self.assertIn(marker, profiles["openssl_on"]["required_command_patterns"])
        self.assertIn(marker, profiles["openssl_off"]["forbidden_command_patterns"])
        self.assertFalse(self.contract["selection_policy"]["weighted_score_used"])
        self.assertIn("https", self.contract["claim_boundary"].lower())

    def test_recipe_binds_openssl_profile_and_loopback_fast_service(self) -> None:
        for profile_name in self.contract["build"]["profiles"]:
            recipe = self.recipe(profile_name)
            self.assertNotIn("--no-repack", recipe["argv"])
            validate_recipe(recipe, profile_name, self.contract)

        invalid = copy.deepcopy(self.recipe("openssl_off"))
        invalid["build_profile"]["llama_openssl"] = True
        with self.assertRaisesRegex(ValueError, "recipe differs"):
            validate_recipe(invalid, "openssl_off", self.contract)

    def test_expected_dependency_pruning_can_select_candidate(self) -> None:
        performance = {
            "openssl_on": self.profile(1.0),
            "openssl_off": self.profile(0.99, median=1010, p95=1810, cpu=4.02),
        }
        result = self.evaluate(performance, self.builds(candidate_closure=99_900_000))
        self.assertTrue(result["passed"])
        self.assertTrue(result["dependency_pruning_passed"])
        self.assertEqual(
            ["libcrypto.so.3", "libssl.so.3"], result["removed_dependencies"]
        )
        self.assertEqual([], result["new_candidate_dependencies"])
        self.assertEqual("openssl_off", result["selected_profile"])

    def test_retained_or_new_dependency_rejects_candidate(self) -> None:
        performance = {
            "openssl_on": self.profile(1.0),
            "openssl_off": self.profile(1.0),
        }
        retained = self.builds(
            candidate_dependencies=[
                "libc.so.6",
                "libcrypto.so.3",
                "libggml.so.0",
                "libstdc++.so.6",
            ]
        )
        result = self.evaluate(performance, retained)
        self.assertFalse(result["dependency_pruning_passed"])
        self.assertFalse(result["passed"])

        added = self.builds(
            candidate_dependencies=[
                "libc.so.6",
                "libggml.so.0",
                "libreplacement.so.1",
                "libstdc++.so.6",
            ]
        )
        result = self.evaluate(performance, added)
        self.assertEqual(["libreplacement.so.1"], result["new_candidate_dependencies"])
        self.assertFalse(result["passed"])

    def test_quality_performance_or_closure_regression_keeps_baseline(self) -> None:
        performance = {
            "openssl_on": self.profile(1.0),
            "openssl_off": self.profile(0.97),
        }
        result = self.evaluate(performance, self.builds(candidate_closure=100_000_001))
        self.assertTrue(result["dependency_pruning_passed"])
        self.assertFalse(result["throughput_guardrail_passed"])
        self.assertFalse(result["runtime_closure_guardrail_passed"])
        self.assertFalse(result["passed"])
        self.assertEqual("openssl_on", result["selected_profile"])

    def test_dependency_inventory_uses_resolved_basenames(self) -> None:
        closure = {
            "runtime_dependencies": [
                {
                    "resolved_path": "/tmp/build/bin/libggml.so.0",
                    "build_local": True,
                },
                {
                    "resolved_path": "/usr/lib/aarch64-linux-gnu/libssl.so.3",
                    "build_local": False,
                },
            ]
        }
        self.assertEqual(
            {"libggml.so.0", "libssl.so.3"}, dependency_basenames(closure)
        )
        self.assertEqual(
            {"libssl.so.3"}, dependency_basenames(closure, system_only=True)
        )


if __name__ == "__main__":
    unittest.main()
