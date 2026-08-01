from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e6f_ingest import expected_server_argv
from experiments.e6g_ingest import (
    launch_profile,
    parse_dependency_basenames,
    validate_outer_invocation,
    validate_recipe,
)

ROOT = Path(__file__).resolve().parents[1]


class E7cIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "experiments/e7c_contract.json").read_text())
        cls.launch_contract = json.loads(
            (ROOT / "configs/runtime-b10216-http-service.json").read_text()
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
                    "status": "valid_http_dependency_pruning_candidate",
                    "experiment_id": "E7b",
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
                    "dynamic_dependency_basenames": [
                        "ld-linux-aarch64.so.1",
                        "libc.so.6",
                        "libggml.so.0",
                    ],
                    "claim_boundary": self.launch_contract["claim_boundary"],
                },
            },
            "weighted_score_used": False,
        }

    def test_contract_binds_exact_e7b_http_service(self) -> None:
        self.assertEqual("E7c", self.contract["experiment_id"])
        reference_request = json.loads(
            (ROOT / "experiments/e6g_contract.json").read_text()
        )["request"]
        self.assertEqual(reference_request, self.contract["request"])
        self.assertEqual("E7b", self.launch_contract["runtime_manifest"]["experiment_id"])
        self.assertEqual(
            ["libcrypto.so.3", "libssl.so.3"],
            self.launch_contract["build"][
                "forbidden_dynamic_dependency_basenames"
            ],
        )
        self.assertIn(
            "LLAMA_OPENSSL:BOOL=OFF",
            self.launch_contract["build"]["cmake_cache_entries"],
        )
        expected_service = dict(self.contract["service"])
        expected_service.pop("client_concurrency")
        expected_service.pop("explicit_batch_arguments")
        expected_service.pop("warmup_slot_ids")
        expected_service["parallel_slots"] = expected_service.pop(
            "server_parallel_slots"
        )
        self.assertEqual(expected_service, self.launch_contract["service"])
        self.assertTrue(launch_profile(self.contract)["dependency_proof"])

    def test_recipe_requires_e7b_provenance_and_exact_argv(self) -> None:
        recipe = self.recipe()
        validate_recipe(
            recipe,
            contract=self.contract,
            launch_contract=self.launch_contract,
        )
        self.assertNotIn("--no-repack", recipe["runtime"]["argv"])
        invalid = copy.deepcopy(recipe)
        invalid["selection"]["runtime_upgrade"]["experiment_id"] = "E6f"
        with self.assertRaisesRegex(ValueError, "preserve selection"):
            validate_recipe(
                invalid,
                contract=self.contract,
                launch_contract=self.launch_contract,
            )

    def test_timed_invocation_keeps_fast_service_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence_dir = Path(temporary)
            command = (
                'Command being timed: "python3 -m pareto64 launch '
                "--runtime-manifest runtime.json --runtime-contract contract.json "
                '--llama-source-root source --llama-build-root build --parallel 1"\n'
            )
            (evidence_dir / "server-time.log").write_text(command)
            validate_outer_invocation(evidence_dir, self.contract)
            (evidence_dir / "server-time.log").write_text(
                command.replace('"\n', ' --no-weight-repack"\n')
            )
            with self.assertRaisesRegex(ValueError, "exact upgrade adapter"):
                validate_outer_invocation(evidence_dir, self.contract)

    def test_raw_dependency_inventory_matches_launcher_names(self) -> None:
        output = """
        linux-vdso.so.1 (0x0)
        libggml.so.0 => /tmp/build/bin/libggml.so.0 (0x1)
        libc.so.6 => /usr/lib/aarch64-linux-gnu/libc.so.6 (0x2)
        /lib/ld-linux-aarch64.so.1 (0x3)
        """
        self.assertEqual(
            ["ld-linux-aarch64.so.1", "libc.so.6", "libggml.so.0"],
            parse_dependency_basenames(output),
        )


if __name__ == "__main__":
    unittest.main()
