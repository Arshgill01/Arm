from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from experiments.e6f_ingest import (
    capture_server_version,
    evaluate_upgrade,
    expected_server_argv,
    validate_runtime_recipe,
    validate_timed_invocation,
)

ROOT = Path(__file__).resolve().parents[1]


class E6fIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e6f_contract.json").read_text())

    def recipe(self, runtime_name: str) -> dict:
        runtime = self.contract["runtimes"][runtime_name]
        server_path = f"/tmp/{runtime_name}/bin/llama-server"
        model_path = "/tmp/models/selected/model.gguf"
        return {
            "schema_version": 1,
            "experiment_id": "E6f",
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

    def test_contract_is_balanced_historical_current_pair(self) -> None:
        execution = self.contract["execution"]
        self.assertEqual("baseline", execution["baseline_runtime"])
        self.assertEqual("current_patched", execution["candidate_runtime"])
        self.assertEqual(
            ["baseline", "current_patched", "current_patched", "baseline"],
            [item["runtime"] for item in execution["order"]],
        )
        self.assertEqual(
            3, len(self.contract["runtimes"]["current_patched"]["patches"])
        )
        self.assertIn("energy", self.contract["claim_boundary"].lower())

    def test_server_version_captures_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            server = Path(temporary) / "llama-server"
            server.write_text(
                "#!/bin/sh\nprintf 'version: 10216 (876a43211)\\n' >&2\n"
            )
            server.chmod(server.stat().st_mode | 0o100)
            self.assertEqual(
                "version: 10216 (876a43211)\n",
                capture_server_version(os.fspath(server)),
            )

    def test_runtime_recipe_binds_source_model_and_service(self) -> None:
        for runtime_name in self.contract["runtimes"]:
            recipe = self.recipe(runtime_name)
            validate_runtime_recipe(
                recipe,
                runtime_name=runtime_name,
                contract=self.contract,
            )
            with tempfile.TemporaryDirectory() as temporary:
                cell = Path(temporary)
                command = " ".join(recipe["argv"])
                (cell / "server-time.log").write_text(
                    f'Command being timed: "{command}"\n'
                )
                validate_timed_invocation(cell, recipe)

        invalid = copy.deepcopy(self.recipe("current_patched"))
        invalid["source"]["commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "frozen E6f profile"):
            validate_runtime_recipe(
                invalid,
                runtime_name="current_patched",
                contract=self.contract,
            )

    def test_upgrade_requires_every_quality_and_resource_gate(self) -> None:
        def profile(
            throughput: float,
            median: float,
            p95: float,
            cpu: float,
            ready: float,
            rss: float,
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

        performance = {
            "baseline": profile(1.0, 1000, 1800, 4.0, 4000, 4_450_000),
            "current_patched": profile(
                0.98, 1010, 1820, 4.05, 4100, 4_480_000
            ),
        }
        result = evaluate_upgrade(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_runtime="baseline",
            candidate_runtime="current_patched",
        )
        self.assertTrue(result["passed"])
        self.assertEqual("current_patched", result["selected_runtime"])

        performance["current_patched"]["requests_per_second"]["median"] = 0.94
        result = evaluate_upgrade(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_runtime="baseline",
            candidate_runtime="current_patched",
        )
        self.assertFalse(result["passed"])
        self.assertEqual("baseline", result["selected_runtime"])
        self.assertFalse(result["throughput_retention_passed"])


if __name__ == "__main__":
    unittest.main()
