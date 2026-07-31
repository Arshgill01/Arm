from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from experiments.e3e_http_quality import run_quality
from experiments.e3e_ingest import build_manifest


ROOT = Path(__file__).resolve().parents[1]


class FakeReasoningHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        self.server.last_request = request  # type: ignore[attr-defined]
        budget = request["reasoning_budget_tokens"]
        body = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "A",
                            "reasoning_content": "brief thought" if budget else "",
                        },
                    }
                ],
                "timings": {
                    "prompt_ms": 10.0,
                    "predicted_ms": 5.0,
                    "predicted_n": 2,
                },
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class E3eTests(unittest.TestCase):
    def test_http_quality_sends_and_records_reasoning_budget(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeReasoningHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = run_quality(
                f"http://127.0.0.1:{server.server_address[1]}",
                {
                    "schema_version": 1,
                    "instruction": "Choose one.",
                    "tasks": [{"id": "one", "prompt": "A or B?"}],
                },
                "budget-16",
                "/models/model.gguf",
                100.0,
                4,
                2048,
                16,
                24,
                424242,
                2.0,
            )
            request = server.last_request  # type: ignore[attr-defined]
            self.assertEqual(16, request["reasoning_budget_tokens"])
            self.assertEqual("deepseek", request["reasoning_format"])
            self.assertEqual({"enable_thinking": True}, request["chat_template_kwargs"])
            self.assertEqual("brief thought", result["cases"][0]["reasoning_content"])
            self.assertEqual(13, result["cases"][0]["reasoning_characters"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_complete_synthetic_artifact_builds_budget_frontier(self) -> None:
        contract_path = ROOT / "experiments/e3e_contract.json"
        models_path = ROOT / "experiments/e3e_models.json"
        tasks_path = ROOT / "experiments/e3_tasks.json"
        policy_path = ROOT / "configs/cloud-quality.json"
        contract = json.loads(contract_path.read_text())
        models = json.loads(models_path.read_text())
        tasks = json.loads(tasks_path.read_text())
        model = models["shared_model"]
        item = model["files"][0]
        time_log = (
            "Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.00\n"
            "Maximum resident set size (kbytes): 1234\n"
            "Exit status: 0\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            (evidence / "contract.json").write_text(contract_path.read_text())
            (evidence / "models-manifest.json").write_text(models_path.read_text())
            (evidence / "tasks-manifest.json").write_text(tasks_path.read_text())
            (evidence / "deployment-policy.json").write_text(policy_path.read_text())
            (evidence / "build-exit.txt").write_text("0\n")
            (evidence / "configure.log").write_text(
                "Using KleidiAI optimized kernels if applicable\n"
            )
            (evidence / "CMakeCache.txt").write_text(
                "GGML_CPU_KLEIDIAI:BOOL=ON\n"
                "GGML_NATIVE:BOOL=ON\n"
                "LLAMA_BUILD_SERVER:BOOL=ON\n"
                "LLAMA_CURL:UNINITIALIZED=OFF\n"
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
                        "experiment_id": "E3e",
                        "github_run_id": "123",
                        "github_run_attempt": "1",
                        "git_commit": "test",
                        "llama_cpp_commit": contract["upstream"]["llama_cpp_commit"],
                        "llama_cpp_tag": contract["upstream"]["llama_cpp_tag"],
                        "kleidiai_release": contract["upstream"]["kleidiai_release"],
                        "kleidiai_archive_md5": contract["upstream"][
                            "kleidiai_archive_md5"
                        ],
                        "deployment_policy_sha256": contract["deployment_policy"][
                            "sha256"
                        ],
                        "source_model_revision": models["source_model"]["revision"],
                        "quantization_revision": models["quantization_repository"][
                            "revision"
                        ],
                        "execution_order": contract["execution_order"],
                        "controlled_difference": contract["controlled_difference"],
                        "calibration_evidence": contract["calibration_evidence"],
                    }
                )
            )
            (evidence / "model-files.txt").write_text(
                f"{item['path']} {item['size_bytes']} bytes\n"
            )
            (evidence / "model-sha256.txt").write_text(
                f"{item['sha256']}  /tmp/models/{item['path']}\n"
            )

            for variant in contract["variants"]:
                config = models["variants"][variant]
                budget = config["reasoning_budget_tokens"]
                variant_dir = evidence / "variants" / variant
                variant_dir.mkdir(parents=True)
                cases = [
                    {
                        "id": task["id"],
                        "response": task["answer"],
                        "reasoning_content": "" if budget == 0 else "brief thought",
                        "reasoning_characters": 0 if budget == 0 else 13,
                        "generated_tokens": 2 if budget == 0 else budget + 2,
                        "encode_ms": 10.0,
                        "decode_ms": 5.0 + budget,
                        "http_ms": 16.0 + budget,
                        "termination_reason": "stop",
                    }
                    for task in tasks["tasks"]
                ]
                for repetition, round_order in enumerate(
                    contract["execution_order"], start=1
                ):
                    position = round_order.index(variant) + 1
                    ready_ms = 100.0 + repetition
                    round_dir = (
                        variant_dir / f"round-{repetition}-position-{position}"
                    )
                    round_dir.mkdir()
                    (round_dir / "readiness.json").write_text(
                        json.dumps({"status": "ok", "ready_ms": ready_ms})
                    )
                    proof_common = {
                        "build_commit": "9d9a6d29f",
                        "model_filename": f"/tmp/models/{item['path']}",
                        "n_threads": 4,
                        "samples_ns": [1_000_000],
                        "samples_ts": [10.0],
                    }
                    (round_dir / "runtime-proof.json").write_text(
                        json.dumps(
                            [
                                {**proof_common, "n_prompt": 8, "n_gen": 0},
                                {**proof_common, "n_prompt": 0, "n_gen": 1},
                            ]
                        )
                    )
                    (round_dir / "runtime-proof.stderr.log").write_text(
                        "CPU_KLEIDIAI model buffer size = 1 MiB\n"
                    )
                    (round_dir / "server.core.log").write_text("")
                    (round_dir / "server.stdout.log").write_text("")
                    (round_dir / "server.stderr.log").write_text("")
                    (round_dir / "server.time.log").write_text(time_log)
                    (variant_dir / f"quality-repeat-{repetition}.json").write_text(
                        json.dumps(
                            {
                                "schema_version": 1,
                                "framework": "llama.cpp",
                                "transport": "OpenAI-compatible HTTP",
                                "model_path": f"/tmp/models/{item['path']}",
                                "threads": 4,
                                "context_size": 2048,
                                "reasoning_budget_tokens": budget,
                                "max_output_tokens": config["max_output_tokens"],
                                "chat_template_mode": (
                                    "model_jinja_enable_thinking_true"
                                ),
                                "reasoning_format": "deepseek",
                                "temperature": 0.0,
                                "seed": 424242,
                                "model_load_ms": ready_ms,
                                "cases": cases,
                            }
                        )
                    )

            result = build_manifest(
                evidence, contract_path, models_path, tasks_path
            )
            self.assertEqual("valid_frontier", result["status"])
            self.assertEqual(["qwen35_q4_think_0"], result["pareto"]["frontier"])
            self.assertEqual(
                48,
                result["application"]["qwen35_q4_think_48"][
                    "reasoning_budget_tokens"
                ],
            )
            self.assertTrue(result["validation"]["kleidiai_runtime_buffer_proven"])


if __name__ == "__main__":
    unittest.main()
