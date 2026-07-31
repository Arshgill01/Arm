from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e1_ingest import summarize
from experiments.e5b_ingest import (
    load_tasks,
    reference_predictions,
    validate_probe,
    validate_recipe,
)
from experiments.e5e_ingest import (
    evaluate_profiles,
    parse_kv_cache_log,
    validate_mechanisms,
)

ROOT = Path(__file__).resolve().parents[1]


class E5eIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e5e_contract.json").read_text())
        cls.manifest = json.loads(
            (ROOT / "results/manifests/e3f-30656151957.json").read_text()
        )
        cls.tasks = load_tasks(
            json.loads((ROOT / "experiments/e3_tasks.json").read_text())
        )
        cls.references = reference_predictions(
            cls.manifest, cls.contract["selected"]["candidate"]
        )

    def recipe(self, configuration: str) -> dict:
        selected = self.contract["selected"]
        inputs = self.contract["inputs"]
        config = self.contract["execution"]["configurations"][configuration]
        context = config["context_per_slot"]
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
                "context_per_slot": context,
                "context_total": context,
                "kv_cache_type_k": config["kv_cache_type_k"],
                "kv_cache_type_v": config["kv_cache_type_v"],
                "flash_attention": config["flash_attention"],
                "log_verbosity": self.contract["mechanism"]["proof_log_verbosity"],
                "argv": [
                    "llama-server",
                    "--ctx-size",
                    str(context),
                    "--cache-type-k",
                    config["kv_cache_type_k"],
                    "--cache-type-v",
                    config["kv_cache_type_v"],
                    "--flash-attn",
                    config["flash_attention"],
                    "--log-verbosity",
                    str(self.contract["mechanism"]["proof_log_verbosity"]),
                    "--cont-batching",
                    "--cache-prompt",
                    "--metrics",
                    "--slots",
                    "--jinja",
                ],
            },
        }

    def make_case(self, index: int, task: dict, reference: str) -> dict:
        return {
            "index": index,
            "id": task["id"],
            "category": task["category"],
            "expected": task["answer"],
            "reference_prediction": reference,
            "status": 200,
            "response": reference,
            "predicted": reference,
            "correct": reference == task["answer"],
            "reference_match": True,
            "termination_reason": "stop",
            "generated_tokens": 1,
            "cached_tokens": 25,
            "evaluated_prompt_tokens": 80 + index,
            "encode_ms": 10.0 + index,
            "decode_ms": 1.0,
            "http_ms": 12.0 + index,
            "error": None,
        }

    def probe(self, configuration: str) -> dict:
        request = self.contract["request"]
        config = self.contract["execution"]["configurations"][configuration]
        task_by_id = {task["id"]: task for task in self.tasks}
        warmups = [
            self.make_case(index, task_by_id[task_id], self.references[task_id])
            for index, task_id in enumerate(request["warmup_task_ids"])
        ]
        cases = [
            self.make_case(index, task, self.references[task["id"]])
            for index, task in enumerate(self.tasks)
        ]
        elapsed = 60.0
        return {
            "schema_version": 1,
            "experiment_id": "E5e",
            "parameters": {
                "base_url": "http://127.0.0.1:18081",
                "candidate": self.contract["selected"]["candidate"],
                "configuration": configuration,
                "repetition": 1,
                "warmup_task_ids": request["warmup_task_ids"],
                "warmup_slot_ids": config["warmup_slot_ids"],
                "measured_tasks": request["measured_tasks"],
                "client_concurrency": config["client_concurrency"],
                "max_output_tokens": request["max_output_tokens"],
                "instruction_role": request["instruction_role"],
                "chat_template_mode": request["chat_template_mode"],
                "temperature": request["temperature"],
                "seed": request["seed"],
                "timeout_seconds": request["timeout_seconds"],
                "prompt_cache": True,
            },
            "warmups": warmups,
            "cases": cases,
            "result": self.probe_result(cases, elapsed),
        }

    @staticmethod
    def probe_result(cases: list[dict], elapsed: float) -> dict:
        return {
            "correct": sum(case["correct"] for case in cases),
            "total": len(cases),
            "accuracy": sum(case["correct"] for case in cases) / len(cases),
            "failures": 0,
            "reference_prediction_mismatches": sum(
                not case["reference_match"] for case in cases
            ),
            "elapsed_seconds": elapsed,
            "requests_per_second": len(cases) / elapsed,
            "http_ms": summarize([case["http_ms"] for case in cases]),
            "encode_ms": summarize([case["encode_ms"] for case in cases]),
            "decode_ms": summarize([case["decode_ms"] for case in cases]),
            "cached_tokens": summarize([case["cached_tokens"] for case in cases]),
            "evaluated_prompt_tokens": summarize(
                [case["evaluated_prompt_tokens"] for case in cases]
            ),
            "status_counts": {"200": len(cases)},
        }

    def test_recipe_binds_context_and_cache_types(self) -> None:
        configuration = "ctx256_k_q8_0"
        config = self.contract["execution"]["configurations"][configuration]
        validate_recipe(
            self.recipe(configuration), config=config, contract=self.contract
        )

        invalid = copy.deepcopy(self.recipe(configuration))
        index = invalid["runtime"]["argv"].index("--cache-type-k") + 1
        invalid["runtime"]["argv"][index] = "f16"
        with self.assertRaisesRegex(ValueError, "KV cache type"):
            validate_recipe(invalid, config=config, contract=self.contract)

    def test_contract_is_reverse_balanced_two_by_three_factorial(self) -> None:
        execution = self.contract["execution"]
        configurations = execution["configurations"]
        factors = {
            (
                config["context_per_slot"],
                config["kv_cache_type_k"],
                config["kv_cache_type_v"],
                config["flash_attention"],
            )
            for config in configurations.values()
        }
        self.assertEqual(
            {
                (context, k_type, "f16", "auto")
                for context in (256, 2048)
                for k_type in ("f16", "q8_0", "q4_0")
            },
            factors,
        )
        order = execution["order"]
        first = [item["configuration"] for item in order[:6]]
        second = [item["configuration"] for item in order[6:]]
        self.assertEqual(first[::-1], second)
        self.assertTrue(all(item["repetition"] == 1 for item in order[:6]))
        self.assertTrue(all(item["repetition"] == 2 for item in order[6:]))

    def test_quality_drift_invalidates_only_the_profile(self) -> None:
        configuration = "ctx256_k_q8_0"
        config = self.contract["execution"]["configurations"][configuration]
        probe = self.probe(configuration)
        case = probe["cases"][0]
        replacement = next(letter for letter in "ABCD" if letter != case["predicted"])
        case["response"] = replacement
        case["predicted"] = replacement
        case["correct"] = replacement == case["expected"]
        case["reference_match"] = False
        probe["result"] = self.probe_result(probe["cases"], 60.0)

        result = validate_probe(
            probe,
            configuration=configuration,
            repetition=1,
            config=config,
            contract=self.contract,
            tasks=self.tasks,
            references=self.references,
            require_selected_quality=False,
        )
        self.assertEqual(1, result["reference_prediction_mismatches"])
        with self.assertRaisesRegex(ValueError, "selected E3f quality"):
            validate_probe(
                probe,
                configuration=configuration,
                repetition=1,
                config=config,
                contract=self.contract,
                tasks=self.tasks,
                references=self.references,
            )

    def test_mechanism_parser_and_factor_monotonicity(self) -> None:
        config = self.contract["execution"]["configurations"]["ctx256_k_f16"]
        line = (
            "llama_kv_cache: size = 26.00 MiB (256 cells, 26 layers, 1/1 seqs), "
            "K (f16): 13.00 MiB, V (f16): 13.00 MiB\n"
        )
        parsed = parse_kv_cache_log(line, config=config, expected_layers=26)
        self.assertEqual(26.0, parsed["total_mib"])
        with self.assertRaisesRegex(ValueError, "frozen KV-cache profile"):
            parse_kv_cache_log(
                line.replace("256 cells", "2048 cells"),
                config=config,
                expected_layers=26,
            )

        sizes = {
            "ctx2048_k_f16": (208.0, 104.0, 104.0),
            "ctx2048_k_q8_0": (159.25, 55.25, 104.0),
            "ctx2048_k_q4_0": (133.25, 29.25, 104.0),
            "ctx256_k_f16": (26.0, 13.0, 13.0),
            "ctx256_k_q8_0": (19.91, 6.91, 13.0),
            "ctx256_k_q4_0": (16.66, 3.66, 13.0),
        }
        with tempfile.TemporaryDirectory() as raw:
            evidence_dir = Path(raw)
            for name, profile in self.contract["execution"]["configurations"].items():
                proof_dir = evidence_dir / "mechanisms" / name
                proof_dir.mkdir(parents=True)
                (proof_dir / "recipe.json").write_text(
                    json.dumps(self.recipe(name)), encoding="utf-8"
                )
                total, k_mib, v_mib = sizes[name]
                (proof_dir / "server.stderr.log").write_text(
                    "llama_kv_cache: size = "
                    f"{total:.2f} MiB ({profile['context_per_slot']} cells, "
                    "26 layers, 1/1 seqs), K "
                    f"({profile['kv_cache_type_k']}): {k_mib:.2f} MiB, "
                    f"V (f16): {v_mib:.2f} MiB\n",
                    encoding="utf-8",
                )
            observed = validate_mechanisms(
                evidence_dir,
                configurations=self.contract["execution"]["configurations"],
                contract=self.contract,
            )
        self.assertEqual(6, len(observed))

    def test_selector_preserves_k_precision_before_extra_savings(self) -> None:
        def profile(k_type: str, rss: float, *, exact: bool = True) -> dict:
            return {
                "context_per_slot": 256,
                "kv_cache_type_k": k_type,
                "quality": {"exact_selected_predictions": exact},
                "requests_per_second": {"median": 0.98},
                "http_ms": {"median": 1010.0, "p95": 2020.0},
                "maximum_rss_kib": {"max": rss},
            }

        performance = {
            "baseline": {
                **profile("f16", 4_800_000.0),
                "context_per_slot": 2048,
                "requests_per_second": {"median": 1.0},
                "http_ms": {"median": 1000.0, "p95": 2000.0},
            },
            "f16": profile("f16", 4_620_000.0),
            "q8": profile("q8_0", 4_550_000.0),
            "q4": profile("q4_0", 4_500_000.0),
        }
        result = evaluate_profiles(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_configuration="baseline",
            precision_preference=["f16", "q8_0", "q4_0"],
            max_required_context=135,
        )
        self.assertEqual("f16", result["selected_configuration"])

        performance["f16"]["quality"]["exact_selected_predictions"] = False
        result = evaluate_profiles(
            performance,
            acceptance=self.contract["acceptance"],
            baseline_configuration="baseline",
            precision_preference=["f16", "q8_0", "q4_0"],
            max_required_context=135,
        )
        self.assertEqual("q8", result["selected_configuration"])


if __name__ == "__main__":
    unittest.main()
