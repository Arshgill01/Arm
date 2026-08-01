from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e5b_ingest import validate_recipe
from experiments.e5j_ingest import (
    evaluate_profiles,
    validate_process_cpu,
    validate_thread_invocation,
)

ROOT = Path(__file__).resolve().parents[1]


class E5jIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e5j_contract.json").read_text())

    def recipe(self, configuration: str) -> dict:
        selected = self.contract["selected"]
        inputs = self.contract["inputs"]
        config = self.contract["execution"]["configurations"][configuration]
        threads = config["threads"]
        argv = [
            "llama-server",
            "--threads",
            str(threads),
            "--threads-batch",
            str(threads),
            "--ctx-size",
            "256",
            "--cache-type-k",
            "f16",
            "--cache-type-v",
            "f16",
            "--flash-attn",
            "auto",
            "--batch-size",
            "64",
            "--ubatch-size",
            "64",
            "--cont-batching",
            "--cache-prompt",
            "--metrics",
            "--slots",
            "--jinja",
        ]
        return {
            "schema_version": 1,
            "service": "Pareto64",
            "status": "ready_to_launch",
            "selected_candidate": selected["candidate"],
            "selection": {"plan_status": "selected"},
            "weighted_score_used": False,
            "inputs": {
                "manifest_sha256": inputs["manifest_sha256"],
                "constraints_sha256": inputs["policy_sha256"],
                "models_sha256": inputs["models_sha256"],
                "contract_sha256": inputs["runtime_contract_sha256"],
            },
            "model": {
                "files": [
                    {
                        "sha256": selected["model_sha256"],
                        "size_bytes": selected["model_size_bytes"],
                    }
                ]
            },
            "runtime": {
                "llama_cpp_commit": selected["llama_cpp_commit"],
                "server_version": (
                    f"version b10208 ({selected['llama_cpp_commit'][:9]})"
                ),
                "threads": threads,
                "parallel_slots": 1,
                "prompt_cache": True,
                "context_per_slot": 256,
                "context_total": 256,
                "kv_cache_type_k": "f16",
                "kv_cache_type_v": "f16",
                "flash_attention": "auto",
                "batch_size_requested": 64,
                "micro_batch_size_requested": 64,
                "batch_size": 64,
                "micro_batch_size": 64,
                "weight_repack": True,
                "argv": argv,
            },
        }

    def test_contract_is_reverse_balanced_three_profile_study(self) -> None:
        execution = self.contract["execution"]
        self.assertEqual("threads4", execution["baseline_configuration"])
        self.assertEqual(
            {"threads4": 4, "threads3": 3, "threads2": 2},
            {
                name: config["threads"]
                for name, config in execution["configurations"].items()
            },
        )
        first = execution["order"][:3]
        second = execution["order"][3:]
        self.assertEqual(
            [item["configuration"] for item in first][::-1],
            [item["configuration"] for item in second],
        )
        self.assertEqual(
            0.95,
            self.contract["acceptance"]["maximum_cpu_seconds_per_request_ratio"],
        )
        self.assertIn("not an energy", self.contract["measurement_boundary"])

    def test_recipe_and_outer_command_bind_both_thread_pools(self) -> None:
        for name, config in self.contract["execution"]["configurations"].items():
            recipe = self.recipe(name)
            validate_recipe(recipe, config=config, contract=self.contract)
            with tempfile.TemporaryDirectory() as temporary:
                cell = Path(temporary)
                (cell / "recipe.json").write_text(json.dumps(recipe))
                (cell / "server-time.log").write_text(
                    "Command being timed: \"python3 -m pareto64 launch "
                    f"--threads {config['threads']}\"\n"
                )
                validate_thread_invocation(cell, config)

        invalid = copy.deepcopy(self.recipe("threads3"))
        invalid["runtime"]["threads"] = 4
        with self.assertRaisesRegex(ValueError, "frozen configuration"):
            validate_recipe(
                invalid,
                config=self.contract["execution"]["configurations"]["threads3"],
                contract=self.contract,
            )

    def test_process_cpu_record_recomputes_from_integer_counters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cell = Path(temporary)
            (cell / "server-pid.txt").write_text("812\n")
            probe = {
                "parameters": {"server_pid": 812},
                "result": {
                    "elapsed_seconds": 1.0,
                    "server_process_cpu": {
                        "pid": 812,
                        "clock_ticks_per_second": 100,
                        "user_ticks": 120,
                        "system_ticks": 30,
                        "total_ticks": 150,
                        "user_seconds": 1.2,
                        "system_seconds": 0.3,
                        "total_seconds": 1.5,
                        "seconds_per_request": 0.05,
                        "average_cores_used": 1.5,
                    },
                },
            }
            result = validate_process_cpu(probe, cell_dir=cell, measured_requests=30)
            self.assertEqual(0.05, result["seconds_per_request"])
            probe["result"]["server_process_cpu"]["total_ticks"] = 149
            with self.assertRaisesRegex(ValueError, "counters are invalid"):
                validate_process_cpu(probe, cell_dir=cell, measured_requests=30)

    def test_selector_requires_cpu_quality_speed_and_latency_gates(self) -> None:
        def profile(
            threads: int,
            throughput: float,
            median: float,
            p95: float,
            cpu: float,
            exact: bool = True,
        ) -> dict:
            return {
                "threads": threads,
                "quality": {"exact_selected_predictions": exact},
                "requests_per_second": {"median": throughput},
                "http_ms": {"median": median, "p95": p95},
                "server_cpu_seconds_per_request": {"median": cpu},
            }

        performance = {
            "threads4": profile(4, 1.0, 1000, 1800, 3.0),
            "threads3": profile(3, 0.98, 1010, 1850, 2.7),
            "threads2": profile(2, 0.8, 1300, 2300, 2.3),
        }
        result = evaluate_profiles(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_configuration="threads4",
        )
        self.assertTrue(result["passed"])
        self.assertEqual("threads3", result["selected_configuration"])
        self.assertFalse(result["profile_gates"]["threads2"]["eligible"])

        performance["threads3"]["server_cpu_seconds_per_request"]["median"] = 2.9
        result = evaluate_profiles(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_configuration="threads4",
        )
        self.assertFalse(result["passed"])
        self.assertEqual("threads4", result["selected_configuration"])


if __name__ == "__main__":
    unittest.main()
