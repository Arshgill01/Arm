from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from experiments.e3d_http_quality import run_quality, wait_for_health
from experiments.e3d_ingest import benchmark_round, build_manifest


ROOT = Path(__file__).resolve().parents[1]


class FakeLlamaHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        body = json.dumps({"status": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        self.server.last_request = request  # type: ignore[attr-defined]
        body = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "A"},
                    }
                ],
                "timings": {
                    "prompt_ms": 10.0,
                    "predicted_ms": 5.0,
                    "predicted_n": 1,
                },
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class E3dTests(unittest.TestCase):
    def test_http_quality_uses_non_thinking_template_and_timings(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLlamaHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}"
            readiness = wait_for_health(url, 2.0)
            self.assertEqual("ok", readiness["status"])
            result = run_quality(
                url,
                {
                    "schema_version": 1,
                    "instruction": "Choose one.",
                    "tasks": [{"id": "one", "prompt": "A or B?"}],
                },
                "model",
                "/models/model.gguf",
                123.0,
                4,
                2048,
                8,
                424242,
                2.0,
            )
            self.assertEqual(10.0, result["cases"][0]["encode_ms"])
            self.assertEqual(5.0, result["cases"][0]["decode_ms"])
            self.assertEqual(
                {"enable_thinking": False},
                server.last_request["chat_template_kwargs"],  # type: ignore[attr-defined]
            )
            self.assertEqual(0.0, server.last_request["temperature"])  # type: ignore[attr-defined]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_current_llama_benchmark_shape_is_validated(self) -> None:
        common = {
            "build_commit": "9d9a6d29",
            "model_filename": "/models/variant/model.gguf",
            "n_threads": 4,
            "samples_ns": [1_000_000, 2_000_000, 3_000_000],
            "samples_ts": [10.0, 11.0, 12.0],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "benchmark.json").write_text(
                json.dumps(
                    [
                        {**common, "n_prompt": 128, "n_gen": 0},
                        {**common, "n_prompt": 0, "n_gen": 64},
                    ]
                )
            )
            (root / "time.log").write_text(
                "Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.00\n"
                "Maximum resident set size (kbytes): 1234\n"
                "Exit status: 0\n"
            )
            result = benchmark_round(root, "/variant/model.gguf", 128, 64, 4, 3)
            self.assertEqual([2.0, 4.0, 6.0], result["total_ms"])
            self.assertEqual(1234, result["process"]["maximum_rss_kib"])

    def test_complete_current_runtime_artifact_builds_frontier(self) -> None:
        contract_path = ROOT / "experiments/e3d_contract.json"
        models_path = ROOT / "experiments/e3d_models.json"
        tasks_path = ROOT / "experiments/e3_tasks.json"
        policy_path = ROOT / "configs/cloud-quality.json"
        contract = json.loads(contract_path.read_text())
        models = json.loads(models_path.read_text())
        tasks = json.loads(tasks_path.read_text())
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
                "LLAMA_CURL:BOOL=OFF\n"
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
                        "experiment_id": "E3d",
                        "github_run_id": "123",
                        "github_run_attempt": "1",
                        "git_commit": "test",
                        "llama_cpp_commit": contract["upstream"]["llama_cpp_commit"],
                        "llama_cpp_tag": contract["upstream"]["llama_cpp_tag"],
                        "kleidiai_release": contract["upstream"]["kleidiai_release"],
                        "kleidiai_archive_md5": contract["upstream"]["kleidiai_archive_md5"],
                        "deployment_policy_sha256": contract["deployment_policy"]["sha256"],
                        "source_model_revision": models["source_model"]["revision"],
                        "model_revisions": {
                            name: model["revision"]
                            for name, model in models["variants"].items()
                        },
                        "execution_order": contract["benchmark"]["execution_order"],
                        "controlled_difference": contract["controlled_difference"],
                    }
                )
            )
            size_lines = []
            hash_lines = []
            for variant in contract["variants"]:
                model = models["variants"][variant]
                item = model["files"][0]
                size_lines.append(f"{variant}/{item['path']} {item['size_bytes']} bytes")
                hash_lines.append(
                    f"{item['sha256']}  /tmp/models/{variant}/{item['path']}"
                )
                variant_dir = evidence / "variants" / variant
                variant_dir.mkdir(parents=True)
                (variant_dir / "readiness.json").write_text(
                    json.dumps({"status": "ok", "ready_ms": 100.0})
                )
                (variant_dir / "server.stdout.log").write_text(
                    "CPU_KLEIDIAI model buffer size = 1 MiB\n"
                )
                (variant_dir / "server.stderr.log").write_text("")
                (variant_dir / "server.time.log").write_text(time_log)
                cases = [
                    {
                        "id": task["id"],
                        "response": task["answer"],
                        "generated_tokens": 1,
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
                                "model_path": f"/tmp/models/{variant}/{item['path']}",
                                "threads": 4,
                                "context_size": 2048,
                                "max_output_tokens": 8,
                                "chat_template_mode": "model_jinja_enable_thinking_false",
                                "temperature": 0.0,
                                "seed": 424242,
                                "model_load_ms": 100.0,
                                "cases": cases,
                            }
                        )
                    )
                for round_number, round_order in enumerate(
                    contract["benchmark"]["execution_order"], start=1
                ):
                    position = round_order.index(variant) + 1
                    round_dir = (
                        variant_dir / f"round-{round_number}-position-{position}"
                    )
                    round_dir.mkdir()
                    common = {
                        "build_commit": "9d9a6d29",
                        "model_filename": f"/tmp/models/{variant}/{item['path']}",
                        "n_threads": 4,
                        "samples_ns": [1_000_000, 2_000_000, 3_000_000],
                        "samples_ts": [10.0, 11.0, 12.0],
                    }
                    (round_dir / "benchmark.json").write_text(
                        json.dumps(
                            [
                                {**common, "n_prompt": 128, "n_gen": 0},
                                {**common, "n_prompt": 0, "n_gen": 64},
                            ]
                        )
                    )
                    (round_dir / "time.log").write_text(time_log)
            (evidence / "model-files.txt").write_text(
                "\n".join(sorted(size_lines)) + "\n"
            )
            (evidence / "model-sha256.txt").write_text("\n".join(hash_lines) + "\n")
            result = build_manifest(evidence, contract_path, models_path, tasks_path)
            self.assertEqual("valid_frontier", result["status"])
            self.assertEqual(["qwen35_4b_q4_0"], result["pareto"]["frontier"])
            self.assertTrue(result["validation"]["kleidiai_runtime_buffer_proven"])


if __name__ == "__main__":
    unittest.main()
