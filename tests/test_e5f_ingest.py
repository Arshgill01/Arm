from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e5b_ingest import validate_recipe
from experiments.e5f_ingest import (
    bind_promoted_default,
    compute_buffers_microbatch_monotonic,
    evaluate_profiles,
    parse_batch_mechanism,
    validate_mechanisms,
)

ROOT = Path(__file__).resolve().parents[1]


class E5fIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e5f_contract.json").read_text())
        cls.floor_contract = json.loads(
            (ROOT / "experiments/e5g_contract.json").read_text()
        )

    def recipe(self, configuration: str) -> dict:
        selected = self.contract["selected"]
        inputs = self.contract["inputs"]
        config = self.contract["execution"]["configurations"][configuration]
        explicit = config["explicit_batch_arguments"]
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
            "--log-verbosity",
            str(self.contract["mechanism"]["proof_log_verbosity"]),
            "--cont-batching",
            "--cache-prompt",
            "--metrics",
            "--slots",
            "--jinja",
        ]
        if explicit:
            argv.extend(
                [
                    "--batch-size",
                    str(config["batch_size"]),
                    "--ubatch-size",
                    str(config["micro_batch_size"]),
                ]
            )
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
                "batch_size_requested": config["batch_size"] if explicit else None,
                "micro_batch_size_requested": (
                    config["micro_batch_size"] if explicit else None
                ),
                "batch_size": config["batch_size"],
                "micro_batch_size": config["micro_batch_size"],
                "log_verbosity": self.contract["mechanism"]["proof_log_verbosity"],
                "argv": argv,
            },
        }

    def test_contract_is_reverse_balanced_three_profile_study(self) -> None:
        execution = self.contract["execution"]
        profiles = {
            (
                config["batch_size"],
                config["micro_batch_size"],
                config["explicit_batch_arguments"],
            )
            for config in execution["configurations"].values()
        }
        self.assertEqual(
            {(256, 256, False), (128, 128, True), (64, 64, True)},
            profiles,
        )
        first = execution["order"][:3]
        second = execution["order"][3:]
        self.assertEqual(
            [item["configuration"] for item in first][::-1],
            [item["configuration"] for item in second],
        )
        self.assertTrue(all(item["repetition"] == 1 for item in first))
        self.assertTrue(all(item["repetition"] == 2 for item in second))

    def test_promoted_default_controls_only_invocation_binding(self) -> None:
        configurations = self.contract["execution"]["configurations"]
        rebound = bind_promoted_default(configurations, "batch64")
        self.assertTrue(rebound["batch64"]["explicit_batch_arguments"])
        self.assertTrue(rebound["batch128"]["explicit_batch_arguments"])
        self.assertTrue(rebound["batch256"]["explicit_batch_arguments"])
        self.assertFalse(rebound["batch64"]["pareto64_batch_arguments"])
        self.assertTrue(rebound["batch128"]["pareto64_batch_arguments"])
        self.assertTrue(rebound["batch256"]["pareto64_batch_arguments"])
        self.assertFalse(
            configurations["batch256"]["explicit_batch_arguments"],
            "the frozen first-run contract must not be mutated",
        )

    def test_all_explicit_floor_contract_keeps_recipe_binding(self) -> None:
        configurations = self.floor_contract["execution"]["configurations"]
        rebound = bind_promoted_default(configurations, "batch64")
        self.assertTrue(rebound["batch64"]["explicit_batch_arguments"])
        self.assertTrue(rebound["batch32"]["explicit_batch_arguments"])
        self.assertFalse(rebound["batch64"]["pareto64_batch_arguments"])
        self.assertTrue(rebound["batch32"]["pareto64_batch_arguments"])

    def test_floor_contract_is_staged_reverse_balanced_study(self) -> None:
        execution = self.floor_contract["execution"]
        self.assertEqual("batch64", execution["baseline_configuration"])
        self.assertEqual(
            {"batch64": 64, "batch32": 32},
            {
                name: config["batch_size"]
                for name, config in execution["configurations"].items()
            },
        )
        self.assertEqual(
            ["batch64", "batch32", "batch32", "batch64"],
            [item["configuration"] for item in execution["order"]],
        )
        geometry = self.floor_contract["prior_evidence"][
            "measured_prompt_chunk_geometry"
        ]
        self.assertEqual(34, geometry["batch64_total_chunks"])
        self.assertEqual(63, geometry["batch32_total_chunks"])
        self.assertIn("Do not test 16", geometry["decision"])

    def test_recipe_binds_implicit_baseline_and_explicit_candidates(self) -> None:
        for name, config in self.contract["execution"]["configurations"].items():
            validate_recipe(self.recipe(name), config=config, contract=self.contract)

        invalid = copy.deepcopy(self.recipe("batch128"))
        invalid["runtime"]["batch_size"] = 64
        with self.assertRaisesRegex(ValueError, "batch sizes"):
            validate_recipe(
                invalid,
                config=self.contract["execution"]["configurations"]["batch128"],
                contract=self.contract,
            )

        invalid = copy.deepcopy(self.recipe("batch256"))
        invalid["runtime"]["argv"].extend(["--batch-size", "256"])
        with self.assertRaisesRegex(ValueError, "unexpectedly pins"):
            validate_recipe(
                invalid,
                config=self.contract["execution"]["configurations"]["batch256"],
                contract=self.contract,
            )

    def test_mechanism_parser_and_monotonicity(self) -> None:
        config = self.contract["execution"]["configurations"]["batch128"]
        log = (
            "llama_context: n_batch       = 128\n"
            "llama_context: n_ubatch      = 128\n"
            "sched_reserve:        CPU compute buffer size =    24.00 MiB\n"
        )
        parsed = parse_batch_mechanism(log, config=config)
        self.assertEqual(24.0, parsed["compute_buffer_mib"])
        with self.assertRaisesRegex(ValueError, "frozen batch profile"):
            parse_batch_mechanism(
                log.replace("n_batch       = 128", "n_batch = 64"),
                config=config,
            )

        buffers = {"batch256": 40.13, "batch128": 24.0, "batch64": 15.0}
        with tempfile.TemporaryDirectory() as raw:
            evidence = Path(raw)
            for name, profile in self.contract["execution"]["configurations"].items():
                proof = evidence / "mechanisms" / name
                proof.mkdir(parents=True)
                (proof / "recipe.json").write_text(json.dumps(self.recipe(name)))
                batch_arguments = ""
                if profile["explicit_batch_arguments"]:
                    batch_arguments = (
                        f" --batch-size {profile['batch_size']}"
                        f" --micro-batch-size {profile['micro_batch_size']}"
                    )
                (proof / "server-time.log").write_text(
                    'Command being timed: "python3 -m pareto64 launch'
                    f'{batch_arguments}"\n'
                )
                (proof / "server.stderr.log").write_text(
                    f"llama_context: n_batch = {profile['batch_size']}\n"
                    f"llama_context: n_ubatch = {profile['micro_batch_size']}\n"
                    "sched_reserve: CPU compute buffer size = "
                    f"{buffers[name]:.2f} MiB\n"
                )
            observed = validate_mechanisms(
                evidence,
                configurations=self.contract["execution"]["configurations"],
                contract=self.contract,
            )
        self.assertEqual(buffers["batch64"], observed["batch64"]["compute_buffer_mib"])
        configurations = self.contract["execution"]["configurations"]
        self.assertTrue(compute_buffers_microbatch_monotonic(observed, configurations))
        observed["batch64"]["compute_buffer_mib"] = 24.0
        self.assertFalse(compute_buffers_microbatch_monotonic(observed, configurations))

        floor_configurations = self.floor_contract["execution"]["configurations"]
        floor_observed = {
            "batch64": {"compute_buffer_mib": 10.03},
            "batch32": {"compute_buffer_mib": 5.02},
        }
        self.assertTrue(
            compute_buffers_microbatch_monotonic(
                floor_observed,
                floor_configurations,
            )
        )

    def test_selector_prefers_lower_rss_after_all_gates(self) -> None:
        def profile(
            batch: int,
            rss: float,
            buffer: float,
            *,
            throughput: float = 0.99,
            median: float = 1010.0,
            p95: float = 2020.0,
            exact: bool = True,
        ) -> dict:
            return {
                "batch_size": batch,
                "micro_batch_size": batch,
                "quality": {"exact_selected_predictions": exact},
                "requests_per_second": {"median": throughput},
                "http_ms": {"median": median, "p95": p95},
                "maximum_rss_kib": {"max": rss},
                "mechanism": {"compute_buffer_mib": buffer},
            }

        performance = {
            "batch256": profile(
                256,
                4_500_000.0,
                40.13,
                throughput=1.0,
                median=1000.0,
                p95=2000.0,
            ),
            "batch128": profile(128, 4_480_000.0, 24.0),
            "batch64": profile(
                64,
                4_460_000.0,
                15.0,
                throughput=0.98,
                median=1040.0,
                p95=2080.0,
            ),
        }
        result = evaluate_profiles(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_configuration="batch256",
        )
        self.assertEqual("batch64", result["selected_configuration"])

        performance["batch64"]["quality"]["exact_selected_predictions"] = False
        result = evaluate_profiles(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_configuration="batch256",
        )
        self.assertEqual("batch128", result["selected_configuration"])


if __name__ == "__main__":
    unittest.main()
