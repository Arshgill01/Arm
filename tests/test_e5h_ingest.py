from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e5b_ingest import validate_recipe
from experiments.e5h_ingest import (
    evaluate_boundary,
    parse_model_buffers,
    validate_pareto64_invocation,
)

ROOT = Path(__file__).resolve().parents[1]


class E5hIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e5h_contract.json").read_text())

    def recipe(self, configuration: str) -> dict:
        selected = self.contract["selected"]
        inputs = self.contract["inputs"]
        config = self.contract["execution"]["configurations"][configuration]
        argv = [
            "llama-server",
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
        if not config["weight_repack"]:
            argv.append("--no-repack")
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
                "threads": 4,
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
                "weight_repack": config["weight_repack"],
                "argv": argv,
            },
        }

    def test_contract_is_reverse_balanced_repack_pair(self) -> None:
        execution = self.contract["execution"]
        self.assertEqual("repack_on", execution["baseline_configuration"])
        self.assertEqual("repack_off", execution["candidate_configuration"])
        self.assertEqual(
            ["repack_on", "repack_off", "repack_off", "repack_on"],
            [item["configuration"] for item in execution["order"]],
        )
        self.assertGreaterEqual(
            self.contract["acceptance"]["minimum_process_rss_reduction_kib"],
            1536 * 1024,
        )

    def test_recipe_binds_repack_setting(self) -> None:
        for name, config in self.contract["execution"]["configurations"].items():
            validate_recipe(self.recipe(name), config=config, contract=self.contract)

        invalid = copy.deepcopy(self.recipe("repack_off"))
        invalid["runtime"]["argv"].remove("--no-repack")
        with self.assertRaisesRegex(ValueError, "weight repack"):
            validate_recipe(
                invalid,
                config=self.contract["execution"]["configurations"]["repack_off"],
                contract=self.contract,
            )

    def test_mechanism_requires_repack_only_when_enabled(self) -> None:
        on = self.contract["execution"]["configurations"]["repack_on"]
        off = self.contract["execution"]["configurations"]["repack_off"]
        baseline_log = (
            "CPU_Mapped model buffer size = 2024.36 MiB\n"
            "CPU_REPACK model buffer size = 2038.92 MiB\n"
            "repack: repack tensor blk.0.attn_q.weight with q4_K_8x8\n"
        )
        parsed = parse_model_buffers(baseline_log, config=on)
        self.assertEqual(2038.92, parsed["repack_buffer_mib"])
        candidate_log = "CPU_Mapped model buffer size = 2024.36 MiB\n"
        self.assertEqual(
            0.0, parse_model_buffers(candidate_log, config=off)["repack_buffer_mib"]
        )
        with self.assertRaisesRegex(ValueError, "unexpectedly repacked"):
            parse_model_buffers(baseline_log, config=off)

        with tempfile.TemporaryDirectory() as raw:
            cell = Path(raw)
            (cell / "server-time.log").write_text(
                'Command being timed: "python3 -m pareto64 launch --no-weight-repack"\n'
            )
            validate_pareto64_invocation(cell, off)

    def test_memory_tier_requires_quality_speed_latency_and_rss(self) -> None:
        def profile(
            throughput: float,
            rss: float,
            median: float,
            p95: float,
            exact: bool = True,
        ) -> dict:
            return {
                "quality": {"exact_selected_predictions": exact},
                "requests_per_second": {"median": throughput},
                "http_ms": {"median": median, "p95": p95},
                "maximum_rss_kib": {"max": rss},
            }

        performance = {
            "repack_on": profile(1.0, 4_500_000, 1000, 2000),
            "repack_off": profile(0.4, 2_400_000, 3000, 6000),
        }
        result = evaluate_boundary(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_configuration="repack_on",
            candidate_configuration="repack_off",
        )
        self.assertTrue(result["passed"])
        self.assertEqual("repack_off", result["memory_tier_configuration"])

        performance["repack_off"]["maximum_rss_kib"]["max"] = 3_200_000
        result = evaluate_boundary(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_configuration="repack_on",
            candidate_configuration="repack_off",
        )
        self.assertFalse(result["passed"])
        self.assertIsNone(result["memory_tier_configuration"])


if __name__ == "__main__":
    unittest.main()
