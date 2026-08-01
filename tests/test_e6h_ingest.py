from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e6f_ingest import (
    evaluate_upgrade,
    expected_server_argv,
    validate_runtime_recipe,
    validate_timed_invocation,
)

ROOT = Path(__file__).resolve().parents[1]


class E6hIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e6h_contract.json").read_text())

    def recipe(self, runtime_name: str) -> dict:
        runtime = self.contract["runtimes"][runtime_name]
        server_path = f"/tmp/{runtime_name}/bin/llama-server"
        model_path = "/tmp/models/selected/model.gguf"
        return {
            "schema_version": 1,
            "experiment_id": "E6h",
            "runtime_name": runtime_name,
            "source": runtime,
            "server_path": server_path,
            "server_version": f"version ({runtime['commit'][:9]})",
            "model": {
                "path": model_path,
                "sha256": self.contract["selected"]["model_sha256"],
                "size_bytes": self.contract["selected"]["model_size_bytes"],
            },
            "service": self.contract["service"],
            "argv": expected_server_argv(
                server_path,
                model_path,
                candidate=self.contract["selected"]["candidate"],
                service=self.contract["service"],
            ),
        }

    def test_contract_is_balanced_no_repack_upgrade(self) -> None:
        execution = self.contract["execution"]
        self.assertEqual(
            ["baseline", "current_patched", "current_patched", "baseline"],
            [item["runtime"] for item in execution["order"]],
        )
        self.assertFalse(self.contract["service"]["weight_repack"])
        self.assertEqual(
            3_145_728, self.contract["acceptance"]["maximum_process_rss_kib"]
        )
        self.assertIn(
            "CPU_REPACK model buffer size",
            self.contract["selected"]["forbidden_runtime_buffer_patterns"],
        )
        self.assertIn("energy", self.contract["claim_boundary"].lower())

    def test_recipe_requires_no_repack_for_both_runtimes(self) -> None:
        for runtime_name in self.contract["runtimes"]:
            recipe = self.recipe(runtime_name)
            self.assertEqual("--no-repack", recipe["argv"][-1])
            validate_runtime_recipe(
                recipe,
                runtime_name=runtime_name,
                contract=self.contract,
            )
            with tempfile.TemporaryDirectory() as temporary:
                cell = Path(temporary)
                (cell / "server-time.log").write_text(
                    f'Command being timed: "{" ".join(recipe["argv"])}"\n'
                )
                validate_timed_invocation(cell, recipe)

        invalid = copy.deepcopy(self.recipe("current_patched"))
        invalid["argv"].remove("--no-repack")
        with self.assertRaisesRegex(ValueError, "arguments differ"):
            validate_runtime_recipe(
                invalid,
                runtime_name="current_patched",
                contract=self.contract,
            )

    def test_upgrade_requires_every_retention_gate(self) -> None:
        def profile(throughput: float, rss: float) -> dict:
            return {
                "quality": {"exact_selected_predictions": True},
                "requests_per_second": {"median": throughput},
                "http_ms": {"median": 2200.0, "p95": 3900.0},
                "server_cpu_seconds_per_request": {"median": 8.5},
                "ready_ms": {"median": 2100.0},
                "maximum_rss_kib": {"max": rss},
            }

        performance = {
            "baseline": profile(0.45, 2_381_000),
            "current_patched": profile(0.44, 2_382_000),
        }
        result = evaluate_upgrade(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_runtime="baseline",
            candidate_runtime="current_patched",
        )
        self.assertTrue(result["passed"])
        self.assertEqual("current_patched", result["selected_runtime"])

        performance["current_patched"]["maximum_rss_kib"]["max"] = 2_500_000
        result = evaluate_upgrade(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_runtime="baseline",
            candidate_runtime="current_patched",
        )
        self.assertFalse(result["passed"])
        self.assertFalse(result["rss_overhead_passed"])


if __name__ == "__main__":
    unittest.main()
