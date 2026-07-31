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
from experiments.e5c_ingest import evaluate_hypothesis

ROOT = Path(__file__).resolve().parents[1]


class E5cIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e5c_contract.json").read_text())
        cls.manifest = json.loads(
            (ROOT / "results/manifests/e3f-30656151957.json").read_text()
        )
        cls.tasks = load_tasks(
            json.loads((ROOT / "experiments/e3_tasks.json").read_text())
        )
        cls.references = reference_predictions(
            cls.manifest, cls.contract["selected"]["candidate"]
        )

    def make_case(
        self, index: int, task: dict, reference: str, cached_tokens: int
    ) -> dict:
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
            "cached_tokens": cached_tokens,
            "evaluated_prompt_tokens": 80 + index,
            "encode_ms": 10.0 + index,
            "decode_ms": 1.0,
            "http_ms": 12.0 + index,
            "error": None,
        }

    def probe(self, configuration: str) -> dict:
        request = self.contract["request"]
        config = self.contract["execution"]["configurations"][configuration]
        cached_tokens = 24 if config["prompt_cache"] else 0
        task_by_id = {task["id"]: task for task in self.tasks}
        warmups = [
            self.make_case(
                index,
                task_by_id[task_id],
                self.references[task_id],
                cached_tokens,
            )
            for index, task_id in enumerate(request["warmup_task_ids"])
        ]
        cases = [
            self.make_case(index, task, self.references[task["id"]], cached_tokens)
            for index, task in enumerate(self.tasks)
        ]
        elapsed = 60.0
        return {
            "schema_version": 1,
            "experiment_id": "E5c",
            "parameters": {
                "base_url": "http://127.0.0.1:18081",
                "candidate": self.contract["selected"]["candidate"],
                "configuration": configuration,
                "repetition": 1,
                "warmup_task_ids": request["warmup_task_ids"],
                "measured_tasks": request["measured_tasks"],
                "client_concurrency": config["client_concurrency"],
                "max_output_tokens": request["max_output_tokens"],
                "instruction_role": request["instruction_role"],
                "chat_template_mode": request["chat_template_mode"],
                "temperature": request["temperature"],
                "seed": request["seed"],
                "timeout_seconds": request["timeout_seconds"],
                "prompt_cache": config["prompt_cache"],
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

    def test_valid_cached_probe_reuses_prefix_and_preserves_quality(self) -> None:
        configuration = "prompt_cache"
        result = validate_probe(
            self.probe(configuration),
            configuration=configuration,
            repetition=1,
            config=self.contract["execution"]["configurations"][configuration],
            contract=self.contract,
            tasks=self.tasks,
            references=self.references,
        )
        self.assertEqual(23, result["correct"])
        self.assertEqual(24.0, result["cached_tokens"]["median"])

    def test_missing_prefix_reuse_fails_closed(self) -> None:
        configuration = "prompt_cache"
        probe = self.probe(configuration)
        probe["cases"][0]["cached_tokens"] = 0
        probe["result"]["cached_tokens"] = summarize(
            [case["cached_tokens"] for case in probe["cases"]]
        )
        with self.assertRaisesRegex(ValueError, "did not reuse"):
            validate_probe(
                probe,
                configuration=configuration,
                repetition=1,
                config=self.contract["execution"]["configurations"][configuration],
                contract=self.contract,
                tasks=self.tasks,
                references=self.references,
            )

    def test_no_cache_cell_rejects_hidden_reuse(self) -> None:
        configuration = "no_cache"
        probe = self.probe(configuration)
        probe["cases"][0]["cached_tokens"] = 1
        probe["result"]["cached_tokens"] = summarize(
            [case["cached_tokens"] for case in probe["cases"]]
        )
        with self.assertRaisesRegex(ValueError, "unexpectedly reused"):
            validate_probe(
                probe,
                configuration=configuration,
                repetition=1,
                config=self.contract["execution"]["configurations"][configuration],
                contract=self.contract,
                tasks=self.tasks,
                references=self.references,
            )

    def recipe(self, prompt_cache: bool) -> dict:
        selected = self.contract["selected"]
        inputs = self.contract["inputs"]
        cache_argument = "--cache-prompt" if prompt_cache else "--no-cache-prompt"
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
                "prompt_cache": prompt_cache,
                "context_per_slot": 2048,
                "context_total": 2048,
                "argv": [
                    "llama-server",
                    "--cont-batching",
                    cache_argument,
                    "--metrics",
                    "--slots",
                    "--jinja",
                ],
            },
        }

    def test_launch_recipe_binds_each_cache_mode(self) -> None:
        for name in ("no_cache", "prompt_cache"):
            config = self.contract["execution"]["configurations"][name]
            validate_recipe(
                self.recipe(config["prompt_cache"]),
                config=config,
                contract=self.contract,
            )
            wrong = copy.deepcopy(self.recipe(not config["prompt_cache"]))
            with self.assertRaisesRegex(ValueError, "serving arguments"):
                validate_recipe(wrong, config=config, contract=self.contract)

    def test_predeclared_improvement_gates(self) -> None:
        performance = {
            "no_cache": {
                "requests_per_second": {"median": 0.5},
                "repetition_encode_median_ms": {"median": 1800.0},
            },
            "prompt_cache": {
                "requests_per_second": {"median": 0.6},
                "repetition_encode_median_ms": {"median": 1400.0},
                "http_ms": {"median": 1500.0, "p95": 2200.0},
            },
        }
        result = evaluate_hypothesis(performance, self.contract["acceptance"])
        self.assertTrue(result["passed"])
        performance["prompt_cache"]["requests_per_second"]["median"] = 0.52
        result = evaluate_hypothesis(performance, self.contract["acceptance"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["throughput_improvement_passed"])


if __name__ == "__main__":
    unittest.main()
