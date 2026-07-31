from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from experiments.e6c_ingest import VARIANT, build_manifest


ROOT = Path(__file__).resolve().parents[1]


class E6cIngestTests(unittest.TestCase):
    def make_artifact(self, evidence: Path) -> tuple[Path, Path, Path]:
        contract_path = ROOT / "experiments/e6c_contract.json"
        models_path = ROOT / "experiments/e6c_models.json"
        tasks_path = ROOT / "experiments/e3_tasks.json"
        patch_path = (
            ROOT
            / "patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch"
        )
        contract = json.loads(contract_path.read_text())
        models = json.loads(models_path.read_text())
        tasks = json.loads(tasks_path.read_text())
        model = models["shared_model"]
        item = model["files"][0]
        variant_dir = evidence / "variants" / VARIANT
        variant_dir.mkdir(parents=True)

        (evidence / "contract.json").write_text(contract_path.read_text())
        (evidence / "models-manifest.json").write_text(models_path.read_text())
        (evidence / "tasks-manifest.json").write_text(tasks_path.read_text())
        (evidence / "patch.patch").write_bytes(patch_path.read_bytes())
        (evidence / "applied.patch").write_bytes(patch_path.read_bytes())
        (evidence / "changed-files.txt").write_text(
            "common/reasoning-budget.cpp\ntests/test-reasoning-budget.cpp\n"
        )
        for key, filename in (
            ("source_sha256_before", "source-before-sha256.txt"),
            ("source_sha256_after", "source-after-sha256.txt"),
            ("test_sha256_before", "test-before-sha256.txt"),
            ("test_sha256_after", "test-after-sha256.txt"),
        ):
            (evidence / filename).write_text(
                f"{contract['patch'][key]}  /tmp/{filename}\n"
            )
        (evidence / "baseline-test-exit.txt").write_text("134\n")
        (evidence / "baseline-test.stderr.log").write_text(
            contract["regression"]["baseline_failure_pattern"] + " failed\n"
        )
        (evidence / "patched-test-exit.txt").write_text("0\n")
        (evidence / "patched-test.stdout.log").write_text(
            "Testing reasoning budget sampler... OK (13 tests passed)\n"
        )
        (evidence / "build-exit.txt").write_text("0\n")
        (evidence / "configure.log").write_text(
            "Using KleidiAI optimized kernels if applicable\n"
        )
        (evidence / "CMakeCache.txt").write_text(
            "GGML_CPU_KLEIDIAI:BOOL=ON\n"
            "GGML_NATIVE:BOOL=ON\n"
            "LLAMA_BUILD_SERVER:BOOL=ON\n"
            "LLAMA_BUILD_TESTS:BOOL=ON\n"
            "LLAMA_CURL:UNINITIALIZED=OFF\n"
        )
        (evidence / "model-files.txt").write_text(
            f"{item['path']} {item['size_bytes']} bytes\n"
        )
        (evidence / "model-sha256.txt").write_text(
            f"{item['sha256']}  /tmp/models/{item['path']}\n"
        )
        (evidence / "lscpu.txt").write_text(
            "Architecture: aarch64\nCPU(s): 4\nModel name: Test\n"
            "Socket(s): 1\nThread(s) per core: 1\nFlags: asimd\n"
        )
        (evidence / "uname.txt").write_text("test aarch64\n")
        (evidence / "provenance.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "experiment_id": "E6c",
                    "github_run_id": "123",
                    "github_run_attempt": "1",
                    "git_commit": "test",
                    "llama_cpp_commit": contract["upstream"]["llama_cpp_commit"],
                    "llama_cpp_tag": contract["upstream"]["llama_cpp_tag"],
                    "kleidiai_release": contract["upstream"]["kleidiai_release"],
                    "kleidiai_archive_md5": contract["upstream"][
                        "kleidiai_archive_md5"
                    ],
                    "patch_sha256": contract["patch"]["sha256"],
                    "source_model_revision": models["source_model"]["revision"],
                    "quantization_revision": models["quantization_repository"][
                        "revision"
                    ],
                    "prior_failure": contract["prior_failure"],
                }
            )
        )
        proof_common = {
            "build_commit": contract["upstream"]["llama_cpp_commit"][:9],
            "model_filename": f"/tmp/models/{item['path']}",
            "n_threads": 4,
            "samples_ns": [1_000_000],
            "samples_ts": [10.0],
        }
        (variant_dir / "runtime-proof.json").write_text(
            json.dumps(
                [
                    {**proof_common, "n_prompt": 8, "n_gen": 0},
                    {**proof_common, "n_prompt": 0, "n_gen": 1},
                ]
            )
        )
        (variant_dir / "runtime-proof.stderr.log").write_text(
            "CPU_KLEIDIAI model buffer size = 1 MiB\n"
        )
        (variant_dir / "server.core.log").write_text("")
        (variant_dir / "server.stdout.log").write_text("")
        (variant_dir / "server.stderr.log").write_text("")
        (variant_dir / "readiness.json").write_text(
            json.dumps({"status": "ok", "ready_ms": 100.0})
        )
        (variant_dir / "server.time.log").write_text(
            "Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.00\n"
            "Maximum resident set size (kbytes): 1234\n"
            "Exit status: 0\n"
        )
        cases = [
            {
                "id": task["id"],
                "response": task["answer"],
                "reasoning_content": "",
                "reasoning_characters": 0,
                "generated_tokens": 2,
                "encode_ms": 10.0,
                "decode_ms": 5.0,
                "http_ms": 16.0,
                "termination_reason": "stop",
            }
            for task in tasks["tasks"]
        ]
        for repetition in (1, 2):
            (variant_dir / f"quality-repeat-{repetition}.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "framework": "llama.cpp",
                        "transport": "OpenAI-compatible HTTP",
                        "model_path": f"/tmp/models/{item['path']}",
                        "threads": 4,
                        "context_size": 2048,
                        "reasoning_budget_tokens": 0,
                        "max_output_tokens": 8,
                        "chat_template_mode": "model_jinja_enable_thinking_true",
                        "reasoning_format": "deepseek",
                        "temperature": 0.0,
                        "seed": 424242,
                        "model_load_ms": 100.0,
                        "cases": cases,
                    }
                )
            )
        return contract_path, models_path, tasks_path

    def test_complete_artifact_accepts_native_correctness_fix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            inputs = self.make_artifact(evidence)
            result = build_manifest(evidence, *inputs)
            self.assertEqual("valid_correctness_fix", result["status"])
            self.assertEqual(60, result["application"][VARIANT]["final_answer_count"])
            self.assertEqual(
                0.0,
                result["application"][VARIANT]["reasoning_characters"]["max"],
            )
            self.assertTrue(result["validation"]["baseline_regression_reproduced"])
            self.assertTrue(result["validation"]["quality_reference_floor_met"])

    def test_reasoning_content_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            inputs = self.make_artifact(evidence)
            path = evidence / "variants" / VARIANT / "quality-repeat-1.json"
            run = json.loads(path.read_text())
            run["cases"][0]["reasoning_content"] = "unexpected"
            run["cases"][0]["reasoning_characters"] = 10
            path.write_text(json.dumps(run))
            with self.assertRaisesRegex(ValueError, "clean immediate reasoning end"):
                build_manifest(evidence, *inputs)


if __name__ == "__main__":
    unittest.main()
