from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from pareto64.planner import load_object
from pareto64.runtime import (
    prepare_launch,
    validate_runtime_upgrade_service,
    validate_server_version,
)

ROOT = Path(__file__).resolve().parents[1]


class Pareto64RuntimeTests(unittest.TestCase):
    def runtime_upgrade_fixture(
        self,
        root: Path,
        model_manifest_path: Path,
        selected: str,
    ) -> dict:
        source_root = root / "llama.cpp"
        source_root.mkdir()
        subprocess.run(["git", "init", "-q", str(source_root)], check=True)
        subprocess.run(
            ["git", "-C", str(source_root), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(source_root), "config", "user.name", "Test"],
            check=True,
        )
        changed_files = [
            "common/reasoning-budget.cpp",
            "ggml/src/ggml-cpu/CMakeLists.txt",
            "ggml/src/ggml-cpu/arch/arm/quants.c",
            "tests/test-reasoning-budget.cpp",
        ]
        for relative in changed_files:
            path = source_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("baseline\n")
        subprocess.run(
            ["git", "-C", str(source_root), "add", "."], check=True
        )
        subprocess.run(
            ["git", "-C", str(source_root), "commit", "-qm", "baseline"],
            check=True,
        )
        selected_commit = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        for relative in changed_files:
            with (source_root / relative).open("a") as stream:
                stream.write("patched\n")
        source_diff = subprocess.run(
            [
                "git",
                "-C",
                str(source_root),
                "diff",
                "--binary",
                "--full-index",
                "HEAD",
                "--",
            ],
            check=True,
            capture_output=True,
        ).stdout

        build_root = root / "build"
        server_path = build_root / "bin/llama-server"
        server_path.parent.mkdir(parents=True)
        server_path.write_text("#!/bin/sh\nexit 0\n")
        server_path.chmod(0o755)
        cache_entries = [
            "CMAKE_BUILD_TYPE:STRING=Release",
            "CMAKE_GENERATOR:INTERNAL=Ninja",
            "GGML_CPU_KLEIDIAI:BOOL=ON",
            "GGML_NATIVE:BOOL=ON",
            "LLAMA_BUILD_EXAMPLES:BOOL=OFF",
            "LLAMA_BUILD_SERVER:BOOL=ON",
            "LLAMA_BUILD_TESTS:BOOL=OFF",
            "LLAMA_CURL:UNINITIALIZED=OFF",
        ]
        (build_root / "CMakeCache.txt").write_text(
            "\n".join(
                [*cache_entries, f"CMAKE_HOME_DIRECTORY:INTERNAL={source_root}"]
            )
            + "\n"
        )

        patches = [
            {"name": "feature", "path": "feature.patch", "sha256": "1" * 64},
            {"name": "q8", "path": "q8.patch", "sha256": "2" * 64},
            {"name": "reasoning", "path": "reasoning.patch", "sha256": "3" * 64},
        ]
        service = {
            "batch_size": 64,
            "client_concurrency": 1,
            "context_per_slot": 256,
            "flash_attention": "auto",
            "kv_cache_type_k": "f16",
            "kv_cache_type_v": "f16",
            "micro_batch_size": 64,
            "prompt_cache": True,
            "server_parallel_slots": 1,
            "threads": 4,
            "warmup_slot_ids": [0, 0],
            "weight_repack": True,
        }
        baseline_commit = "9d9a6d29f6b981cc7f41983d26e56485c6af1811"
        runtime_manifest = {
            "schema_version": 1,
            "experiment_id": "E6f",
            "status": "valid_current_runtime_upgrade_candidate",
            "contract": {
                "inputs": {
                    "manifest_sha256": hashlib.sha256(
                        model_manifest_path.read_bytes()
                    ).hexdigest()
                },
                "selected": {"candidate": selected},
                "execution": {"candidate_runtime": "current_patched"},
                "runtimes": {
                    "baseline": {"commit": baseline_commit, "patches": []},
                    "current_patched": {
                        "commit": selected_commit,
                        "patches": patches,
                    },
                },
                "service": service,
            },
            "selection": {
                "selected_runtime": "current_patched",
                "selected_commit": selected_commit,
            },
            "hypothesis": {"passed": True},
            "validation": {
                "upgrade_candidate_claim_allowed": True,
                "automatic_product_promotion_allowed": False,
                "exact_patch_series_verified": True,
                "exact_model_verified": True,
            },
            "performance": {
                "baseline": {"quality": {"exact_selected_predictions": True}},
                "current_patched": {
                    "quality": {"exact_selected_predictions": True}
                },
            },
        }
        runtime_manifest_path = root / "runtime-manifest.json"
        runtime_manifest_path.write_text(json.dumps(runtime_manifest))
        contract_service = dict(service)
        contract_service.pop("client_concurrency")
        contract_service.pop("warmup_slot_ids")
        contract_service["parallel_slots"] = contract_service.pop(
            "server_parallel_slots"
        )
        contract_service["log_verbosity"] = None
        runtime_contract = {
            "schema_version": 1,
            "contract_id": "test-current-runtime",
            "promotion_mode": "explicit_evidence_bound_upgrade",
            "runtime_manifest": {
                "experiment_id": "E6f",
                "sha256": hashlib.sha256(
                    runtime_manifest_path.read_bytes()
                ).hexdigest(),
            },
            "model_selection_manifest": {
                "experiment_id": "E3f",
                "sha256": hashlib.sha256(
                    model_manifest_path.read_bytes()
                ).hexdigest(),
            },
            "selected_candidate": selected,
            "runtime": {
                "baseline_commit": baseline_commit,
                "selected_commit": selected_commit,
                "source_diff_sha256": hashlib.sha256(source_diff).hexdigest(),
                "changed_files": changed_files,
                "patches": [
                    {"name": patch["name"], "sha256": patch["sha256"]}
                    for patch in patches
                ],
            },
            "build": {
                "server_relative_path": "bin/llama-server",
                "cmake_cache_entries": cache_entries,
            },
            "service": contract_service,
            "claim_boundary": "test boundary",
        }
        runtime_contract_path = root / "runtime-contract.json"
        runtime_contract_path.write_text(json.dumps(runtime_contract))
        return {
            "manifest": runtime_manifest,
            "contract": runtime_contract,
            "manifest_path": runtime_manifest_path,
            "contract_path": runtime_contract_path,
            "source_root": source_root,
            "build_root": build_root,
            "server_path": server_path,
            "selected_commit": selected_commit,
            "service": contract_service,
        }

    def test_selected_package_produces_exact_launch_recipe(self) -> None:
        manifest = load_object(ROOT / "results/manifests/e3f-30656151957.json")
        constraints = load_object(ROOT / "configs/cloud-quality.json")
        models = load_object(ROOT / "experiments/e3f_models.json")
        contract = load_object(ROOT / "experiments/e3f_contract.json")
        service_manifest = load_object(
            ROOT / "results/manifests/e5h-30672633366.json"
        )
        service_constraints = load_object(ROOT / "configs/service-memory.json")
        throughput_constraints = load_object(
            ROOT / "configs/service-throughput.json"
        )
        selected = "ministral3_3b_q4_k_m"
        payload = b"test model"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "manifest.json"
            constraints_path = root / "constraints.json"
            models_path = root / "models.json"
            contract_path = root / "contract.json"
            service_manifest_path = root / "service-manifest.json"
            service_constraints_path = root / "service-constraints.json"
            throughput_constraints_path = root / "throughput-constraints.json"
            server_path = root / "llama-server"
            model_root = root / "model-root"
            model_path = model_root / selected / "model.gguf"
            model_path.parent.mkdir(parents=True)
            model_path.write_bytes(payload)
            server_path.write_text("#!/bin/sh\nexit 0\n")
            server_path.chmod(0o755)
            models = copy.deepcopy(models)
            models["variants"][selected]["entrypoint"] = "model.gguf"
            models["variants"][selected]["files"] = [
                {
                    "path": "model.gguf",
                    "size_bytes": len(payload),
                    "sha256": digest,
                }
            ]
            manifest = copy.deepcopy(manifest)
            manifest["application"][selected]["package_size_bytes"] = len(payload)
            manifest_path.write_text(json.dumps(manifest))
            constraints_path.write_text(json.dumps(constraints))
            models_path.write_text(json.dumps(models))
            contract_path.write_text(json.dumps(contract))
            service_manifest_path.write_text(json.dumps(service_manifest))
            service_constraints_path.write_text(json.dumps(service_constraints))
            throughput_constraints_path.write_text(
                json.dumps(throughput_constraints)
            )
            recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=manifest_path,
                constraints_path=constraints_path,
                models_path=models_path,
                contract_path=contract_path,
                model_root=model_root,
                server_path=server_path,
                version_output="version b10208 (9d9a6d29f)",
                host="127.0.0.1",
                port=18081,
                parallel=2,
            )
            self.assertEqual("ready_to_launch", recipe["status"])
            self.assertEqual(selected, recipe["selected_candidate"])
            self.assertEqual(digest, recipe["model"]["files"][0]["sha256"])
            self.assertEqual(512, recipe["runtime"]["context_total"])
            self.assertEqual(256, recipe["runtime"]["context_per_slot"])
            self.assertEqual(64, recipe["runtime"]["batch_size"])
            self.assertEqual(64, recipe["runtime"]["micro_batch_size"])
            self.assertEqual(64, recipe["runtime"]["batch_size_requested"])
            self.assertEqual(64, recipe["runtime"]["micro_batch_size_requested"])
            self.assertIn("--cont-batching", recipe["runtime"]["argv"])
            self.assertIn("--batch-size", recipe["runtime"]["argv"])
            self.assertIn("--ubatch-size", recipe["runtime"]["argv"])
            self.assertIn("--cache-prompt", recipe["runtime"]["argv"])
            self.assertTrue(recipe["runtime"]["prompt_cache"])
            self.assertEqual("f16", recipe["runtime"]["kv_cache_type_k"])
            self.assertEqual("f16", recipe["runtime"]["kv_cache_type_v"])
            self.assertEqual("auto", recipe["runtime"]["flash_attention"])
            self.assertIn("--flash-attn", recipe["runtime"]["argv"])
            self.assertTrue(recipe["runtime"]["weight_repack"])
            self.assertNotIn("--no-repack", recipe["runtime"]["argv"])
            self.assertFalse(recipe["weighted_score_used"])

            three_thread_recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=manifest_path,
                constraints_path=constraints_path,
                models_path=models_path,
                contract_path=contract_path,
                model_root=model_root,
                server_path=server_path,
                version_output="version b10208 (9d9a6d29f)",
                host="127.0.0.1",
                port=18081,
                parallel=1,
                threads=3,
            )
            self.assertEqual(3, three_thread_recipe["runtime"]["threads"])
            thread_index = three_thread_recipe["runtime"]["argv"].index("--threads")
            batch_thread_index = three_thread_recipe["runtime"]["argv"].index(
                "--threads-batch"
            )
            self.assertEqual(
                "3", three_thread_recipe["runtime"]["argv"][thread_index + 1]
            )
            self.assertEqual(
                "3", three_thread_recipe["runtime"]["argv"][batch_thread_index + 1]
            )

            for invalid_threads in (0, 5, True):
                with self.subTest(invalid_threads=invalid_threads):
                    with self.assertRaisesRegex(ValueError, "runtime threads"):
                        prepare_launch(
                            manifest=manifest,
                            constraints=constraints,
                            models=models,
                            contract=contract,
                            manifest_path=manifest_path,
                            constraints_path=constraints_path,
                            models_path=models_path,
                            contract_path=contract_path,
                            model_root=model_root,
                            server_path=server_path,
                            version_output="version b10208 (9d9a6d29f)",
                            host="127.0.0.1",
                            port=18081,
                            parallel=1,
                            threads=invalid_threads,
                        )

            uncached_recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=manifest_path,
                constraints_path=constraints_path,
                models_path=models_path,
                contract_path=contract_path,
                model_root=model_root,
                server_path=server_path,
                version_output="version b10208 (9d9a6d29f)",
                host="127.0.0.1",
                port=18081,
                parallel=1,
                prompt_cache=False,
            )
            self.assertIn("--no-cache-prompt", uncached_recipe["runtime"]["argv"])
            self.assertNotIn("--cache-prompt", uncached_recipe["runtime"]["argv"])
            self.assertFalse(uncached_recipe["runtime"]["prompt_cache"])

            no_repack_recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=manifest_path,
                constraints_path=constraints_path,
                models_path=models_path,
                contract_path=contract_path,
                model_root=model_root,
                server_path=server_path,
                version_output="version b10208 (9d9a6d29f)",
                host="127.0.0.1",
                port=18081,
                parallel=1,
                weight_repack=False,
            )
            self.assertFalse(no_repack_recipe["runtime"]["weight_repack"])
            self.assertEqual(
                1, no_repack_recipe["runtime"]["argv"].count("--no-repack")
            )

            planned_memory_recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=manifest_path,
                constraints_path=constraints_path,
                models_path=models_path,
                contract_path=contract_path,
                model_root=model_root,
                server_path=server_path,
                version_output="version b10208 (9d9a6d29f)",
                host="127.0.0.1",
                port=18081,
                parallel=1,
                service_manifest=service_manifest,
                service_constraints=service_constraints,
                service_manifest_path=service_manifest_path,
                service_constraints_path=service_constraints_path,
            )
            self.assertFalse(planned_memory_recipe["runtime"]["weight_repack"])
            self.assertEqual(
                1, planned_memory_recipe["runtime"]["argv"].count("--no-repack")
            )
            self.assertEqual(
                "repack_off",
                planned_memory_recipe["selection"]["service_profile"]["name"],
            )
            self.assertEqual(
                hashlib.sha256(service_constraints_path.read_bytes()).hexdigest(),
                planned_memory_recipe["inputs"]["service_constraints_sha256"],
            )

            planned_throughput_recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=manifest_path,
                constraints_path=constraints_path,
                models_path=models_path,
                contract_path=contract_path,
                model_root=model_root,
                server_path=server_path,
                version_output="version b10208 (9d9a6d29f)",
                host="127.0.0.1",
                port=18081,
                parallel=1,
                service_manifest=service_manifest,
                service_constraints=throughput_constraints,
                service_manifest_path=service_manifest_path,
                service_constraints_path=throughput_constraints_path,
            )
            self.assertTrue(planned_throughput_recipe["runtime"]["weight_repack"])
            self.assertNotIn(
                "--no-repack", planned_throughput_recipe["runtime"]["argv"]
            )
            self.assertEqual(
                "repack_on",
                planned_throughput_recipe["selection"]["service_profile"]["name"],
            )

            with self.assertRaisesRegex(ValueError, "conflicts with the service plan"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=manifest_path,
                    constraints_path=constraints_path,
                    models_path=models_path,
                    contract_path=contract_path,
                    model_root=model_root,
                    server_path=server_path,
                    version_output="version b10208 (9d9a6d29f)",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                    weight_repack=True,
                    service_manifest=service_manifest,
                    service_constraints=service_constraints,
                    service_manifest_path=service_manifest_path,
                    service_constraints_path=service_constraints_path,
                )

            with self.assertRaisesRegex(ValueError, "requires both"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=manifest_path,
                    constraints_path=constraints_path,
                    models_path=models_path,
                    contract_path=contract_path,
                    model_root=model_root,
                    server_path=server_path,
                    version_output="version b10208 (9d9a6d29f)",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                    service_manifest=service_manifest,
                    service_manifest_path=service_manifest_path,
                )

            impossible_constraints = copy.deepcopy(service_constraints)
            impossible_constraints["requirements"]["maximum_rss_kib"] = {
                "at_most": 2 * 1024 * 1024
            }
            impossible_constraints_path = root / "impossible-constraints.json"
            impossible_constraints_path.write_text(json.dumps(impossible_constraints))
            with self.assertRaisesRegex(ValueError, "no selected measured profile"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=manifest_path,
                    constraints_path=constraints_path,
                    models_path=models_path,
                    contract_path=contract_path,
                    model_root=model_root,
                    server_path=server_path,
                    version_output="version b10208 (9d9a6d29f)",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                    service_manifest=service_manifest,
                    service_constraints=impossible_constraints,
                    service_manifest_path=service_manifest_path,
                    service_constraints_path=impossible_constraints_path,
                )

            flash_off_recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=manifest_path,
                constraints_path=constraints_path,
                models_path=models_path,
                contract_path=contract_path,
                model_root=model_root,
                server_path=server_path,
                version_output="version b10208 (9d9a6d29f)",
                host="127.0.0.1",
                port=18081,
                parallel=1,
                flash_attention="off",
            )
            self.assertEqual("off", flash_off_recipe["runtime"]["flash_attention"])
            flash_argument = flash_off_recipe["runtime"]["argv"].index(
                "--flash-attn"
            )
            self.assertEqual(
                "off", flash_off_recipe["runtime"]["argv"][flash_argument + 1]
            )

            profiled_recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=manifest_path,
                constraints_path=constraints_path,
                models_path=models_path,
                contract_path=contract_path,
                model_root=model_root,
                server_path=server_path,
                version_output="version b10208 (9d9a6d29f)",
                host="127.0.0.1",
                port=18081,
                parallel=1,
                context_per_slot=256,
                kv_cache_type_k="q8_0",
                batch_size=128,
                micro_batch_size=128,
                log_verbosity=3,
            )
            self.assertEqual(256, profiled_recipe["runtime"]["context_total"])
            self.assertEqual("q8_0", profiled_recipe["runtime"]["kv_cache_type_k"])
            self.assertEqual(128, profiled_recipe["runtime"]["batch_size"])
            self.assertEqual(128, profiled_recipe["runtime"]["micro_batch_size"])
            self.assertEqual(128, profiled_recipe["runtime"]["batch_size_requested"])
            self.assertIn("--batch-size", profiled_recipe["runtime"]["argv"])
            self.assertIn("--ubatch-size", profiled_recipe["runtime"]["argv"])
            self.assertEqual(3, profiled_recipe["runtime"]["log_verbosity"])
            self.assertIn("--cache-type-k", profiled_recipe["runtime"]["argv"])
            self.assertIn("--log-verbosity", profiled_recipe["runtime"]["argv"])

            with self.assertRaisesRegex(ValueError, "must be set together"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=manifest_path,
                    constraints_path=constraints_path,
                    models_path=models_path,
                    contract_path=contract_path,
                    model_root=model_root,
                    server_path=server_path,
                    version_output="version b10208 (9d9a6d29f)",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                    batch_size=128,
                    micro_batch_size=None,
                )

            with self.assertRaisesRegex(ValueError, "repack setting"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=manifest_path,
                    constraints_path=constraints_path,
                    models_path=models_path,
                    contract_path=contract_path,
                    model_root=model_root,
                    server_path=server_path,
                    version_output="version b10208 (9d9a6d29f)",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                    weight_repack=1,
                )

            with self.assertRaisesRegex(ValueError, "flash attention"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=manifest_path,
                    constraints_path=constraints_path,
                    models_path=models_path,
                    contract_path=contract_path,
                    model_root=model_root,
                    server_path=server_path,
                    version_output="version b10208 (9d9a6d29f)",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                    flash_attention="sometimes",
                )

    def test_model_hash_mismatch_fails_closed(self) -> None:
        manifest = load_object(ROOT / "results/manifests/e3f-30656151957.json")
        constraints = load_object(ROOT / "configs/cloud-quality.json")
        models = load_object(ROOT / "experiments/e3f_models.json")
        contract = load_object(ROOT / "experiments/e3f_contract.json")
        selected = "ministral3_3b_q4_k_m"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model_root = root / "models"
            model_path = model_root / selected / "model.gguf"
            model_path.parent.mkdir(parents=True)
            model_path.write_bytes(b"wrong")
            models = copy.deepcopy(models)
            models["variants"][selected]["entrypoint"] = "model.gguf"
            models["variants"][selected]["files"] = [
                {"path": "model.gguf", "size_bytes": 5, "sha256": "0" * 64}
            ]
            manifest = copy.deepcopy(manifest)
            manifest["application"][selected]["package_size_bytes"] = 5
            paths = {}
            for name, value in (
                ("manifest", manifest),
                ("constraints", constraints),
                ("models", models),
                ("contract", contract),
            ):
                path = root / f"{name}.json"
                path.write_text(json.dumps(value))
                paths[name] = path
            server = root / "llama-server"
            server.write_text("")
            server.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=paths["manifest"],
                    constraints_path=paths["constraints"],
                    models_path=paths["models"],
                    contract_path=paths["contract"],
                    model_root=model_root,
                    server_path=server,
                    version_output="9d9a6d29f",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                )

    def test_runtime_commit_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "version differs"):
            validate_server_version(
                "different build", "9d9a6d29f6b981cc7f41983d26e56485c6af1811"
            )

    def test_current_runtime_upgrade_binds_source_build_and_service(self) -> None:
        manifest = load_object(ROOT / "results/manifests/e3f-30656151957.json")
        constraints = load_object(ROOT / "configs/cloud-quality.json")
        models = load_object(ROOT / "experiments/e3f_models.json")
        contract = load_object(ROOT / "experiments/e3f_contract.json")
        selected = "ministral3_3b_q4_k_m"
        payload = b"test model"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model_root = root / "models"
            model_path = model_root / selected / "model.gguf"
            model_path.parent.mkdir(parents=True)
            model_path.write_bytes(payload)
            models = copy.deepcopy(models)
            models["variants"][selected]["entrypoint"] = "model.gguf"
            models["variants"][selected]["files"] = [
                {
                    "path": "model.gguf",
                    "size_bytes": len(payload),
                    "sha256": digest,
                }
            ]
            manifest = copy.deepcopy(manifest)
            manifest["application"][selected]["package_size_bytes"] = len(payload)
            paths = {}
            for name, value in (
                ("manifest", manifest),
                ("constraints", constraints),
                ("models", models),
                ("contract", contract),
            ):
                path = root / f"{name}.json"
                path.write_text(json.dumps(value))
                paths[name] = path
            upgrade = self.runtime_upgrade_fixture(root, paths["manifest"], selected)
            recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=paths["manifest"],
                constraints_path=paths["constraints"],
                models_path=paths["models"],
                contract_path=paths["contract"],
                model_root=model_root,
                server_path=upgrade["server_path"],
                version_output=f"version ({upgrade['selected_commit'][:9]})",
                host="127.0.0.1",
                port=18081,
                parallel=1,
                runtime_manifest=upgrade["manifest"],
                runtime_contract=upgrade["contract"],
                runtime_manifest_path=upgrade["manifest_path"],
                runtime_contract_path=upgrade["contract_path"],
                runtime_source_root=upgrade["source_root"],
                runtime_build_root=upgrade["build_root"],
            )
            self.assertEqual(
                upgrade["selected_commit"], recipe["runtime"]["llama_cpp_commit"]
            )
            self.assertEqual(
                "explicit_evidence_bound_upgrade",
                recipe["runtime"]["upgrade_provenance"]["promotion_mode"],
            )
            self.assertEqual(
                digest, recipe["model"]["files"][0]["sha256"]
            )

            invalid_service = dict(upgrade["service"])
            invalid_service["threads"] = 3
            with self.assertRaisesRegex(ValueError, "exact E6f service"):
                validate_runtime_upgrade_service(
                    upgrade["manifest"], upgrade["contract"], invalid_service
                )

            with (upgrade["source_root"] / "common/reasoning-budget.cpp").open(
                "a"
            ) as stream:
                stream.write("tampered\n")
            with self.assertRaisesRegex(ValueError, "exact patched series"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=paths["manifest"],
                    constraints_path=paths["constraints"],
                    models_path=paths["models"],
                    contract_path=paths["contract"],
                    model_root=model_root,
                    server_path=upgrade["server_path"],
                    version_output=f"version ({upgrade['selected_commit'][:9]})",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                    runtime_manifest=upgrade["manifest"],
                    runtime_contract=upgrade["contract"],
                    runtime_manifest_path=upgrade["manifest_path"],
                    runtime_contract_path=upgrade["contract_path"],
                    runtime_source_root=upgrade["source_root"],
                    runtime_build_root=upgrade["build_root"],
                )

    def test_model_symlink_cannot_escape_candidate_directory(self) -> None:
        manifest = load_object(ROOT / "results/manifests/e3f-30656151957.json")
        constraints = load_object(ROOT / "configs/cloud-quality.json")
        models = load_object(ROOT / "experiments/e3f_models.json")
        contract = load_object(ROOT / "experiments/e3f_contract.json")
        selected = "ministral3_3b_q4_k_m"
        payload = b"model outside the declared root"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.gguf"
            outside.write_bytes(payload)
            model_root = root / "models"
            candidate_root = model_root / selected
            candidate_root.mkdir(parents=True)
            (candidate_root / "model.gguf").symlink_to(outside)
            models = copy.deepcopy(models)
            models["variants"][selected]["entrypoint"] = "model.gguf"
            models["variants"][selected]["files"] = [
                {
                    "path": "model.gguf",
                    "size_bytes": len(payload),
                    "sha256": digest,
                }
            ]
            manifest = copy.deepcopy(manifest)
            manifest["application"][selected]["package_size_bytes"] = len(payload)
            paths = {}
            for name, value in (
                ("manifest", manifest),
                ("constraints", constraints),
                ("models", models),
                ("contract", contract),
            ):
                path = root / f"{name}.json"
                path.write_text(json.dumps(value))
                paths[name] = path
            with self.assertRaisesRegex(ValueError, "outside the candidate"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=paths["manifest"],
                    constraints_path=paths["constraints"],
                    models_path=paths["models"],
                    contract_path=paths["contract"],
                    model_root=model_root,
                    server_path=root / "llama-server",
                    version_output="9d9a6d29f",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                )


if __name__ == "__main__":
    unittest.main()
