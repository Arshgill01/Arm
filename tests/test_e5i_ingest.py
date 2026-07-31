from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e5b_ingest import validate_recipe
from experiments.e5i_ingest import (
    evaluate_boundary,
    parse_flash_mechanism,
    validate_pareto64_invocation,
)

ROOT = Path(__file__).resolve().parents[1]


class E5iIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e5i_contract.json").read_text())

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
            config["flash_attention"],
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
                "threads": 4,
                "parallel_slots": 1,
                "prompt_cache": True,
                "context_per_slot": 256,
                "context_total": 256,
                "kv_cache_type_k": "f16",
                "kv_cache_type_v": "f16",
                "flash_attention": config["flash_attention"],
                "batch_size_requested": 64,
                "micro_batch_size_requested": 64,
                "batch_size": 64,
                "micro_batch_size": 64,
                "weight_repack": True,
                "argv": argv,
            },
        }

    def test_contract_is_reverse_balanced_flash_pair(self) -> None:
        execution = self.contract["execution"]
        self.assertEqual("flash_off", execution["baseline_configuration"])
        self.assertEqual("flash_auto", execution["candidate_configuration"])
        self.assertEqual(
            ["flash_off", "flash_auto", "flash_auto", "flash_off"],
            [item["configuration"] for item in execution["order"]],
        )
        self.assertGreaterEqual(
            self.contract["acceptance"]["minimum_throughput_improvement_ratio"],
            1.05,
        )

    def test_recipe_binds_flash_setting(self) -> None:
        for name, config in self.contract["execution"]["configurations"].items():
            validate_recipe(self.recipe(name), config=config, contract=self.contract)

        invalid = copy.deepcopy(self.recipe("flash_off"))
        flash_index = invalid["runtime"]["argv"].index("--flash-attn")
        invalid["runtime"]["argv"][flash_index + 1] = "auto"
        with self.assertRaisesRegex(ValueError, "KV cache type"):
            validate_recipe(
                invalid,
                config=self.contract["execution"]["configurations"]["flash_off"],
                contract=self.contract,
            )

    def test_mechanism_and_outer_invocation_bind_each_mode(self) -> None:
        auto = self.contract["execution"]["configurations"]["flash_auto"]
        off = self.contract["execution"]["configurations"]["flash_off"]
        auto_log = (
            "llama_context: flash_attn    = auto\n"
            "resolve_fused_ops: Flash Attention enabled\n"
            "sched_reserve: CPU compute buffer size = 10.03 MiB\n"
        )
        off_log = (
            "llama_context: flash_attn    = disabled\n"
            "sched_reserve: CPU compute buffer size = 18.50 MiB\n"
        )
        self.assertTrue(parse_flash_mechanism(auto_log, config=auto)["resolved_enabled"])
        self.assertFalse(parse_flash_mechanism(off_log, config=off)["resolved_enabled"])
        with self.assertRaisesRegex(ValueError, "resolved Flash Attention"):
            parse_flash_mechanism(
                off_log + "resolve_fused_ops: Flash Attention enabled\n",
                config=off,
            )

        with tempfile.TemporaryDirectory() as raw:
            cell = Path(raw)
            (cell / "server-time.log").write_text(
                'Command being timed: "python3 -m pareto64 launch --flash-attention off"\n'
            )
            validate_pareto64_invocation(cell, off)

    def test_win_requires_quality_speed_latency_and_bounded_rss(self) -> None:
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
            "flash_off": profile(0.8, 4_450_000, 1200, 2200),
            "flash_auto": profile(0.9, 4_455_000, 1000, 2000),
        }
        result = evaluate_boundary(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_configuration="flash_off",
            candidate_configuration="flash_auto",
        )
        self.assertTrue(result["passed"])
        self.assertEqual("flash_auto", result["validated_default_configuration"])

        performance["flash_auto"]["requests_per_second"]["median"] = 0.82
        result = evaluate_boundary(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_configuration="flash_off",
            candidate_configuration="flash_auto",
        )
        self.assertFalse(result["passed"])
        self.assertIsNone(result["validated_default_configuration"])


if __name__ == "__main__":
    unittest.main()
