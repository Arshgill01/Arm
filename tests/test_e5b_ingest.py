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

ROOT = Path(__file__).resolve().parents[1]


class E5bIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e5b_contract.json").read_text())
        cls.manifest = json.loads(
            (ROOT / "results/manifests/e3f-30656151957.json").read_text()
        )
        tasks_manifest = json.loads((ROOT / "experiments/e3_tasks.json").read_text())
        cls.tasks = load_tasks(tasks_manifest)
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
            "encode_ms": 10.0 + index,
            "decode_ms": 1.0,
            "http_ms": 12.0 + index,
            "error": None,
        }

    def probe(self) -> dict:
        request = self.contract["request"]
        config = self.contract["execution"]["configurations"]["baseline"]
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
            "experiment_id": "E5b",
            "parameters": {
                "base_url": "http://127.0.0.1:18081",
                "candidate": self.contract["selected"]["candidate"],
                "configuration": "baseline",
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
                "status_counts": {"200": len(cases)},
            },
        }

    def test_valid_probe_reproduces_selected_quality(self) -> None:
        result = validate_probe(
            self.probe(),
            configuration="baseline",
            repetition=1,
            config=self.contract["execution"]["configurations"]["baseline"],
            contract=self.contract,
            tasks=self.tasks,
            references=self.references,
        )
        self.assertEqual(23, result["correct"])
        self.assertEqual(0, result["reference_prediction_mismatches"])

    def test_answer_drift_fails_closed(self) -> None:
        probe = self.probe()
        case = probe["cases"][0]
        replacement = "A" if case["reference_prediction"] != "A" else "B"
        case["response"] = replacement
        case["predicted"] = replacement
        case["correct"] = replacement == case["expected"]
        case["reference_match"] = False
        probe["result"]["correct"] = sum(item["correct"] for item in probe["cases"])
        probe["result"]["accuracy"] = probe["result"]["correct"] / len(probe["cases"])
        probe["result"]["reference_prediction_mismatches"] = 1
        with self.assertRaisesRegex(ValueError, "selected E3f quality"):
            validate_probe(
                probe,
                configuration="baseline",
                repetition=1,
                config=self.contract["execution"]["configurations"]["baseline"],
                contract=self.contract,
                tasks=self.tasks,
                references=self.references,
            )

    def test_raw_summary_tampering_fails_closed(self) -> None:
        probe = copy.deepcopy(self.probe())
        probe["result"]["http_ms"]["median"] += 1
        with self.assertRaisesRegex(ValueError, "summary differs"):
            validate_probe(
                probe,
                configuration="baseline",
                repetition=1,
                config=self.contract["execution"]["configurations"]["baseline"],
                contract=self.contract,
                tasks=self.tasks,
                references=self.references,
            )

    def test_launch_recipe_is_bound_to_frozen_inputs(self) -> None:
        selected = self.contract["selected"]
        inputs = self.contract["inputs"]
        server_version = f"version b10208 ({selected['llama_cpp_commit'][:9]})"
        recipe = {
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
                "server_version": server_version,
                "threads": 4,
                "parallel_slots": 1,
                "context_per_slot": 2048,
                "context_total": 2048,
                "argv": [
                    "llama-server",
                    "--cont-batching",
                    "--no-cache-prompt",
                    "--metrics",
                    "--slots",
                    "--jinja",
                ],
            },
        }
        config = self.contract["execution"]["configurations"]["baseline"]
        validate_recipe(recipe, config=config, contract=self.contract)
        recipe["inputs"]["models_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "models hash"):
            validate_recipe(recipe, config=config, contract=self.contract)


if __name__ == "__main__":
    unittest.main()
