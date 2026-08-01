from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from experiments.e6f_ingest import expected_server_argv
from experiments.e6g_ingest import validate_recipe

ROOT = Path(__file__).resolve().parents[1]


class E6gIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e6g_contract.json").read_text())
        cls.launch_contract = json.loads(
            (ROOT / "configs/runtime-b10216-selected-service.json").read_text()
        )

    def recipe(self) -> dict:
        contract = self.contract
        inputs = contract["inputs"]
        selected = contract["selected"]
        service = contract["service"]
        server_path = "/tmp/build/bin/llama-server"
        model_path = "/tmp/models/selected/model.gguf"
        return {
            "schema_version": 1,
            "service": "Pareto64",
            "status": "ready_to_launch",
            "selected_candidate": selected["candidate"],
            "selection": {
                "plan_status": "selected",
                "runtime_upgrade": {
                    "status": "valid_current_runtime_upgrade_candidate",
                    "experiment_id": "E6f",
                    "selected_commit": contract["runtime"]["commit"],
                    "promotion_mode": "explicit_evidence_bound_upgrade",
                },
            },
            "inputs": {
                "manifest_sha256": inputs["manifest_sha256"],
                "constraints_sha256": inputs["policy_sha256"],
                "models_sha256": inputs["models_sha256"],
                "contract_sha256": inputs["model_contract_sha256"],
                "runtime_manifest_sha256": inputs["runtime_manifest_sha256"],
                "runtime_contract_sha256": inputs["runtime_contract_sha256"],
            },
            "model": {
                "files": [
                    {
                        "path": model_path,
                        "sha256": selected["model_sha256"],
                        "size_bytes": selected["model_size_bytes"],
                    }
                ]
            },
            "runtime": {
                "llama_cpp_commit": contract["runtime"]["commit"],
                "server_path": server_path,
                "server_version": f"version ({contract['runtime']['commit'][:9]})",
                "threads": service["threads"],
                "parallel_slots": service["server_parallel_slots"],
                "prompt_cache": service["prompt_cache"],
                "kv_cache_type_k": service["kv_cache_type_k"],
                "kv_cache_type_v": service["kv_cache_type_v"],
                "flash_attention": service["flash_attention"],
                "context_per_slot": service["context_per_slot"],
                "context_total": service["context_per_slot"],
                "batch_size_requested": service["batch_size"],
                "micro_batch_size_requested": service["micro_batch_size"],
                "batch_size": service["batch_size"],
                "micro_batch_size": service["micro_batch_size"],
                "weight_repack": service["weight_repack"],
                "log_verbosity": service["log_verbosity"],
                "argv": expected_server_argv(
                    server_path,
                    model_path,
                    candidate=selected["candidate"],
                    service=service,
                ),
                "upgrade_provenance": {
                    "contract_id": self.launch_contract["contract_id"],
                    "promotion_mode": self.launch_contract["promotion_mode"],
                    "runtime_manifest_sha256": inputs["runtime_manifest_sha256"],
                    "runtime_contract_sha256": inputs["runtime_contract_sha256"],
                    "claim_boundary": self.launch_contract["claim_boundary"],
                },
            },
            "weighted_score_used": False,
        }

    def test_contract_binds_the_exact_e6f_service(self) -> None:
        self.assertEqual("E6g", self.contract["experiment_id"])
        self.assertEqual(
            self.contract["runtime"]["commit"],
            self.launch_contract["runtime"]["selected_commit"],
        )
        expected_service = dict(self.contract["service"])
        expected_service.pop("client_concurrency")
        expected_service.pop("explicit_batch_arguments")
        expected_service.pop("warmup_slot_ids")
        expected_service["parallel_slots"] = expected_service.pop(
            "server_parallel_slots"
        )
        self.assertEqual(expected_service, self.launch_contract["service"])

    def test_recipe_requires_current_provenance_and_exact_argv(self) -> None:
        recipe = self.recipe()
        validate_recipe(
            recipe,
            contract=self.contract,
            launch_contract=self.launch_contract,
        )
        invalid_provenance = copy.deepcopy(recipe)
        invalid_provenance["runtime"]["upgrade_provenance"]["promotion_mode"] = (
            "automatic"
        )
        with self.assertRaisesRegex(ValueError, "current-runtime provenance"):
            validate_recipe(
                invalid_provenance,
                contract=self.contract,
                launch_contract=self.launch_contract,
            )
        invalid_argv = copy.deepcopy(recipe)
        invalid_argv["runtime"]["argv"].append("--no-repack")
        with self.assertRaisesRegex(ValueError, "server argv"):
            validate_recipe(
                invalid_argv,
                contract=self.contract,
                launch_contract=self.launch_contract,
            )


if __name__ == "__main__":
    unittest.main()
