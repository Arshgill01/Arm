from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from experiments.e1_ingest import summarize
from experiments.e5b_ingest import (
    load_tasks,
    reference_predictions,
    validate_probe,
    validate_recipe,
)
from experiments.e5d_ingest import evaluate_hypothesis

ROOT = Path(__file__).resolve().parents[1]


class E5dIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e5d_contract.json").read_text())
        cls.manifest = json.loads(
            (ROOT / "results/manifests/e3f-30656151957.json").read_text()
        )
        cls.tasks = load_tasks(
            json.loads((ROOT / "experiments/e3_tasks.json").read_text())
        )
        cls.references = reference_predictions(
            cls.manifest, cls.contract["selected"]["candidate"]
        )

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
            "experiment_id": "E5d",
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
            "result": {
                "correct": 23,
                "total": 30,
                "accuracy": 23 / 30,
                "failures": 0,
                "reference_prediction_mismatches": 0,
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
            },
        }

    def recipe(self, configuration: str) -> dict:
        selected = self.contract["selected"]
        inputs = self.contract["inputs"]
        config = self.contract["execution"]["configurations"][configuration]
        slots = config["server_parallel_slots"]
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
                "parallel_slots": slots,
                "prompt_cache": True,
                "context_per_slot": 2048,
                "context_total": 2048 * slots,
                "argv": [
                    "llama-server",
                    "--cont-batching",
                    "--cache-prompt",
                    "--metrics",
                    "--slots",
                    "--jinja",
                ],
            },
        }

    def test_both_cached_configurations_bind_warmup_slots(self) -> None:
        for configuration in ("cached_single", "cached_dual"):
            config = self.contract["execution"]["configurations"][configuration]
            result = validate_probe(
                self.probe(configuration),
                configuration=configuration,
                repetition=1,
                config=config,
                contract=self.contract,
                tasks=self.tasks,
                references=self.references,
            )
            self.assertEqual(25.0, result["cached_tokens"]["median"])

            invalid = self.probe(configuration)
            invalid["parameters"]["warmup_slot_ids"] = [0, 0]
            if configuration == "cached_dual":
                with self.assertRaisesRegex(ValueError, "warmup slot"):
                    validate_probe(
                        invalid,
                        configuration=configuration,
                        repetition=1,
                        config=config,
                        contract=self.contract,
                        tasks=self.tasks,
                        references=self.references,
                    )

    def test_recipes_bind_cache_slots_and_context(self) -> None:
        for configuration in ("cached_single", "cached_dual"):
            config = self.contract["execution"]["configurations"][configuration]
            validate_recipe(
                self.recipe(configuration), config=config, contract=self.contract
            )
            invalid = copy.deepcopy(self.recipe(configuration))
            invalid["runtime"]["prompt_cache"] = False
            with self.assertRaisesRegex(ValueError, "serving arguments"):
                validate_recipe(invalid, config=config, contract=self.contract)

    def test_predeclared_cached_concurrency_gates(self) -> None:
        performance = {
            "cached_single": {
                "requests_per_second": {"median": 0.90},
                "maximum_rss_kib": {"max": 4_650_000.0},
            },
            "cached_dual": {
                "requests_per_second": {"median": 1.05},
                "http_ms": {"median": 1900.0, "p95": 2800.0},
                "maximum_rss_kib": {"max": 4_900_000.0},
            },
        }
        result = evaluate_hypothesis(performance, self.contract["acceptance"])
        self.assertTrue(result["passed"])
        self.assertAlmostEqual(1.05 / 0.90, result["throughput_improvement_ratio"])

        performance["cached_dual"]["requests_per_second"]["median"] = 0.95
        result = evaluate_hypothesis(performance, self.contract["acceptance"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["throughput_improvement_passed"])


if __name__ == "__main__":
    unittest.main()
