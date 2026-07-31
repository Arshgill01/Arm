from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from experiments.e3b_ingest import (
    build_manifest,
    discover_performance,
    pareto_front,
    validate_execution_order,
)
from experiments.e3_score import sha256_file


ROOT = Path(__file__).resolve().parents[1]


class E3bIngestTests(unittest.TestCase):
    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_execution_order_requires_every_variant_once(self) -> None:
        variants = ["small", "quality"]
        order = validate_execution_order(
            [["small", "quality"], ["quality", "small"]], variants, 2
        )
        self.assertEqual(["quality", "small"], order[1])
        with self.assertRaisesRegex(ValueError, "every variant once"):
            validate_execution_order(
                [["small", "small"], ["quality", "small"]], variants, 2
            )

    def test_pareto_front_preserves_non_dominated_tradeoffs(self) -> None:
        candidates = {
            "fast": {"quality": 0.8, "latency": 100.0},
            "accurate": {"quality": 0.9, "latency": 150.0},
            "dominated": {"quality": 0.7, "latency": 200.0},
        }
        self.assertEqual(
            ["accurate", "fast"],
            pareto_front(candidates, {"quality": "higher", "latency": "lower"}),
        )

    def test_performance_discovery_enforces_frozen_parameters(self) -> None:
        parameters = {
            "context_size": 2048,
            "model_path": "/tmp/models/small/model.gguf",
            "num_input_tokens": 128,
            "num_iterations": 3,
            "num_output_tokens": 64,
            "num_threads": 4,
            "num_warmup": 1,
        }
        iterations = [
            {
                "encode_tokens_per_sec": 10.0,
                "decode_tokens_per_sec": 5.0,
                "time_to_first_token_ms": 100.0,
                "total_time_ms": 200.0,
            }
            for _ in range(3)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            round_dir = root / "variants" / "small" / "round-1-position-2"
            round_dir.mkdir(parents=True)
            (round_dir / "benchmark.json").write_text(
                json.dumps(
                    {
                        "framework": "llama.cpp",
                        "parameters": parameters,
                        "iterations": iterations,
                    }
                )
            )
            (round_dir / "time.log").write_text(
                "Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.00\n"
                "Maximum resident set size (kbytes): 1234\n"
                "Exit status: 0\n"
            )
            frozen_parameters = {
                key: value for key, value in parameters.items() if key != "model_path"
            }
            rounds = discover_performance(
                root, "small", {1: 2}, frozen_parameters, "/small/model.gguf"
            )
            self.assertEqual(2, rounds[1]["position"])
            bad = {**frozen_parameters, "num_threads": 2}
            with self.assertRaisesRegex(ValueError, "parameters differ"):
                discover_performance(
                    root, "small", {1: 2}, bad, "/small/model.gguf"
                )

    def test_complete_synthetic_artifact_builds_quality_frontier(self) -> None:
        variants = ["small", "quality"]
        order = [
            ["small", "quality"],
            ["quality", "small"],
            ["small", "quality"],
            ["quality", "small"],
        ]
        models = {
            "schema_version": 1,
            "variants": {
                variant: {
                    "display_name": variant,
                    "framework": "llama.cpp",
                    "repository": f"example/{variant}",
                    "revision": f"revision-{variant}",
                    "license": "Apache-2.0",
                    "entrypoint": "model.gguf",
                    "files": [
                        {
                            "path": "model.gguf",
                            "sha256": character * 64,
                            "size_bytes": size,
                        }
                    ],
                }
                for variant, character, size in (
                    ("small", "a", 100),
                    ("quality", "b", 200),
                )
            },
        }
        tasks_path = ROOT / "experiments" / "e3_tasks.json"
        contract = {
            "schema_version": 1,
            "experiment_id": "E3b",
            "upstream": {"llm_runner_commit": "runner", "llama_cpp_commit": "llama"},
            "configuration": {
                "threads": 4,
                "context": 2048,
                "chat_template_mode": "framework_auto",
                "patches": [
                    {"sha256": "patch-one"},
                    {"sha256": "patch-two"},
                ],
            },
            "variants": variants,
            "quality": {
                "tasks_sha256": sha256_file(tasks_path),
                "task_count": 30,
                "repetitions": 2,
                "max_output_tokens": 8,
                "prediction_parser": "first standalone uppercase A-D after case folding",
                "predictions_must_be_stable": True,
                "absolute_accuracy_floor": 0.75,
                "maximum_task_deficit_from_best": 1,
            },
            "benchmark": {
                "input_tokens": 128,
                "output_tokens": 64,
                "context": 2048,
                "threads": 4,
                "rounds_per_variant": 4,
                "warmup_iterations_per_round": 1,
                "measured_iterations_per_round": 3,
                "execution_order": order,
            },
            "pareto": {
                "directions": {
                    "minimum_accuracy": "higher",
                    "same_text_total_ms_median": "lower",
                    "maximum_quality_process_rss_kib": "lower",
                    "package_size_bytes": "lower",
                }
            },
        }
        tasks = json.loads(tasks_path.read_text())
        time_log = (
            "Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.00\n"
            "Maximum resident set size (kbytes): 1234\n"
            "Exit status: 0\n"
        )
        parameters = {
            "context_size": 2048,
            "num_input_tokens": 128,
            "num_iterations": 3,
            "num_output_tokens": 64,
            "num_threads": 4,
            "num_warmup": 1,
        }
        iterations = [
            {
                "encode_tokens_per_sec": 10.0,
                "decode_tokens_per_sec": 5.0,
                "time_to_first_token_ms": 100.0,
                "total_time_ms": 200.0,
            }
            for _ in range(3)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            contract_path = root / "contract.json"
            models_path = root / "models.json"
            frozen_tasks = root / "tasks.json"
            self.write_json(contract_path, contract)
            self.write_json(models_path, models)
            frozen_tasks.write_text(tasks_path.read_text())
            self.write_json(evidence / "contract.json", contract)
            self.write_json(evidence / "models-manifest.json", models)
            (evidence / "tasks-manifest.json").write_text(tasks_path.read_text())
            self.write_json(
                evidence / "provenance.json",
                {
                    "experiment_id": "E3b",
                    "github_run_id": "123",
                    "github_run_attempt": "1",
                    "llm_runner_commit": "runner",
                    "llama_cpp_commit": "llama",
                    "patch_sha256": ["patch-one", "patch-two"],
                    "model_revisions": {
                        "small": "revision-small",
                        "quality": "revision-quality",
                    },
                    "execution_order": order,
                },
            )
            (evidence / "build-exit.txt").write_text("0\n")
            (evidence / "changed-files.txt").write_text(
                "ggml/src/ggml-cpu/CMakeLists.txt\n"
                "ggml/src/ggml-cpu/arch/arm/quants.c\n"
            )
            (evidence / "configure.log").write_text("KleidiAI: ON\n")
            (evidence / "model-files.txt").write_text(
                "quality/model.gguf 200 bytes\nsmall/model.gguf 100 bytes\n"
            )
            (evidence / "model-sha256.txt").write_text(
                f"{'b' * 64}  /tmp/models/quality/model.gguf\n"
                f"{'a' * 64}  /tmp/models/small/model.gguf\n"
            )
            (evidence / "lscpu.txt").write_text(
                "Architecture: aarch64\nCPU(s): 4\nModel name: Test\n"
                "Socket(s): 1\nThread(s) per core: 1\nFlags: asimd\n"
            )
            (evidence / "uname.txt").write_text("test aarch64\n")

            for variant in variants:
                variant_dir = evidence / "variants" / variant
                variant_dir.mkdir(parents=True)
                cases = [
                    {
                        "id": task["id"],
                        "response": task["answer"],
                        "generated_tokens": 1,
                        "encode_ms": 10.0,
                        "decode_ms": 5.0,
                        "termination_reason": "backend_eos",
                    }
                    for task in tasks["tasks"]
                ]
                for repetition in (1, 2):
                    self.write_json(
                        variant_dir / f"quality-repeat-{repetition}.json",
                        {
                            "schema_version": 1,
                            "framework": "llama.cpp",
                            "model_path": f"/tmp/models/{variant}/model.gguf",
                            "threads": 4,
                            "context_size": 2048,
                            "max_output_tokens": 8,
                            "chat_template_mode": "framework_auto",
                            "model_load_ms": 20.0,
                            "cases": cases,
                        },
                    )
                    (variant_dir / f"quality-repeat-{repetition}.time.log").write_text(
                        time_log
                    )
                    (variant_dir / f"quality-repeat-{repetition}.stdout.log").write_text(
                        "CPU_REPACK model buffer size = 1 MiB\n"
                    )
                for round_number, round_order in enumerate(order, start=1):
                    position = round_order.index(variant) + 1
                    round_dir = (
                        variant_dir
                        / f"round-{round_number}-position-{position}"
                    )
                    round_dir.mkdir()
                    self.write_json(
                        round_dir / "benchmark.json",
                        {
                            "framework": "llama.cpp",
                            "parameters": {
                                **parameters,
                                "model_path": f"/tmp/models/{variant}/model.gguf",
                            },
                            "iterations": iterations,
                        },
                    )
                    (round_dir / "time.log").write_text(time_log)

            result = build_manifest(
                evidence, contract_path, models_path, frozen_tasks
            )
            self.assertEqual("valid_frontier", result["status"])
            self.assertEqual(
                sorted(variants),
                result["validation"]["quality_eligible_variants"],
            )
            self.assertEqual(["small"], result["pareto"]["frontier"])

            policy_path = root / "policy.json"
            policy = {
                "schema_version": 1,
                "requirements": {"minimum_accuracy": {"at_least": 0.75}},
                "selection_priority": ["minimum_accuracy"],
            }
            self.write_json(policy_path, policy)
            contract["experiment_id"] = "E3c"
            contract["artifact_name_prefix"] = "e3c-quality-per-byte"
            contract["controlled_difference"] = "quantization only"
            contract["deployment_policy"] = {
                "artifact_path": "deployment-policy.json",
                "path": str(policy_path),
                "sha256": sha256_file(policy_path),
            }
            models["source_model"] = {
                "repository": "example/source",
                "revision": "source-revision",
                "license": "Apache-2.0",
                "parameter_scale": "test",
            }
            models["quantization_repository"] = {
                "repository": "example/quantized",
                "revision": "quantized-revision",
                "license": "Apache-2.0",
                "base_model": "example/source",
            }
            for index, model in enumerate(models["variants"].values(), start=1):
                model["repository"] = "example/quantized"
                model["revision"] = "quantized-revision"
                model["parameter_scale"] = "test"
                model["quantization"] = f"Q{index}"
                model["runtime_buffer_patterns"] = [
                    "CPU_REPACK model buffer size"
                ]
            provenance = json.loads((evidence / "provenance.json").read_text())
            provenance.update(
                {
                    "controlled_difference": "quantization only",
                    "deployment_policy_sha256": sha256_file(policy_path),
                    "experiment_id": "E3c",
                    "model_revisions": {
                        variant: "quantized-revision" for variant in variants
                    },
                    "source_model_revision": "source-revision",
                }
            )
            self.write_json(contract_path, contract)
            self.write_json(models_path, models)
            self.write_json(evidence / "contract.json", contract)
            self.write_json(evidence / "models-manifest.json", models)
            self.write_json(evidence / "provenance.json", provenance)
            self.write_json(evidence / "deployment-policy.json", policy)

            e3c_result = build_manifest(
                evidence, contract_path, models_path, frozen_tasks
            )
            self.assertEqual("E3c", e3c_result["experiment_id"])
            self.assertEqual(
                "e3c-quality-per-byte-123-1",
                e3c_result["source"]["artifact_name"],
            )
            self.assertTrue(
                e3c_result["validation"]["deployment_policy_predeclared"]
            )
            self.assertTrue(
                e3c_result["validation"]["runtime_model_buffer_proven"]
            )
            self.assertEqual(
                ["CPU_REPACK model buffer size"],
                e3c_result["application"]["small"][
                    "runtime_buffer_evidence"
                ],
            )


if __name__ == "__main__":
    unittest.main()
