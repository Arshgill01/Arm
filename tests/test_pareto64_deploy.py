from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from pareto64.deploy import execute_deployment, prepare_deployment


class DeploymentTests(unittest.TestCase):
    def free_port(self) -> int:
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            return candidate.getsockname()[1]

    def make_worker(self, root: Path) -> Path:
        worker = root / "worker.py"
        worker.write_text(
            """\
import http.server
import json
import mmap
import sys

sidecar = open(sys.argv[2], "rb")
mapping = mmap.mmap(sidecar.fileno(), 0, access=mmap.ACCESS_READ)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        content = payload["messages"][-1]["content"]
        body = json.dumps({
            "choices": [{
                "message": {"content": content},
                "finish_reason": "stop",
            }],
            "timings": {
                "predicted_n": 1,
                "cache_n": 16 if payload["cache_prompt"] else 0,
            },
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

server = http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    mapping.close()
    sidecar.close()
""",
            encoding="utf-8",
        )
        return worker

    def make_sidecar_plan(self, root: Path) -> dict[str, object]:
        sidecar = root / "weights.sidecar"
        sidecar.write_bytes(b"sidecar fixture")
        sidecar.chmod(0o444)
        port = self.free_port()
        worker = self.make_worker(root)
        return {
            "schema_version": 1,
            "status": "ready_to_launch_shared_sidecar_workers",
            "deployment_mode": "shared_sidecar",
            "worker_count": 1,
            "runtime_server_sha256": "2" * 64,
            "sidecar": {
                "path": str(sidecar.resolve()),
                "sha256": "f" * 64,
                "read_only": True,
                "device": sidecar.stat().st_dev,
                "inode": sidecar.stat().st_ino,
                "mapping_protection": "PROT_READ",
                "mapping_sharing": "MAP_SHARED",
            },
            "product_identity": {
                "source_model_sha256": "1" * 64,
                "source_diff_sha256": "3" * 64,
            },
            "workers": [
                {
                    "worker": 1,
                    "host": "127.0.0.1",
                    "port": port,
                    "argv": [
                        sys.executable,
                        str(worker),
                        str(port),
                        str(sidecar),
                    ],
                    "environment": {
                        "GGML_CPU_REPACK_SIDECAR_MODEL_SHA256": "1" * 64,
                        "GGML_CPU_REPACK_SIDECAR_SOURCE_DIFF_SHA256": "3" * 64,
                    },
                }
            ],
            "claim_boundary": "test deployment boundary",
        }

    def test_prepare_binds_workers_gateway_and_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = prepare_deployment(
                self.make_sidecar_plan(root),
                gateway_host="127.0.0.1",
                gateway_port=self.free_port(),
                registry_path=root / "registry.json",
                minimum_cached_tokens=8,
                revalidate_every=16,
            )
            self.assertEqual("ready_to_deploy_pareto64", plan["status"])
            self.assertEqual("1" * 64, plan["certificate_identity"]["model_sha256"])
            self.assertEqual(64, len(plan["deployment_sha256"]))

    def test_execute_verifies_mapping_and_writes_complete_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = prepare_deployment(
                self.make_sidecar_plan(root),
                gateway_host="127.0.0.1",
                gateway_port=self.free_port(),
                registry_path=root / "registry.json",
                minimum_cached_tokens=8,
                revalidate_every=16,
            )
            stop = root / "stop"
            timer = threading.Timer(0.5, stop.touch)
            timer.start()
            receipt_path = root / "deployment-receipt.json"
            receipt = execute_deployment(
                plan,
                receipt_path=receipt_path,
                readiness_timeout=5.0,
                upstream_timeout=2.0,
                ready_output=root / "ready.json",
                stop_file=stop,
            )
            timer.join()
            self.assertEqual("valid_pareto64_deployment_lifecycle", receipt["status"])
            self.assertTrue(receipt["shared_mappings"][0]["read_only"])
            self.assertTrue(receipt["shared_mappings"][0]["shared"])
            self.assertEqual(0o444, receipt_path.stat().st_mode & 0o777)
            retained = json.loads(receipt_path.read_text())
            self.assertEqual(plan["deployment_sha256"], retained["deployment_sha256"])

    def test_normal_control_runs_without_a_sidecar_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker_plan = self.make_sidecar_plan(root)
            worker_plan["status"] = "ready_to_launch_normal_workers"
            worker_plan["deployment_mode"] = "normal_repack"
            worker_plan["sidecar"] = None
            plan = prepare_deployment(
                worker_plan,
                gateway_host="127.0.0.1",
                gateway_port=self.free_port(),
                registry_path=root / "registry.json",
                minimum_cached_tokens=8,
                revalidate_every=16,
            )
            stop = root / "stop"
            timer = threading.Timer(0.5, stop.touch)
            timer.start()
            receipt = execute_deployment(
                plan,
                receipt_path=root / "deployment-receipt.json",
                readiness_timeout=5.0,
                stop_file=stop,
            )
            timer.join()
            self.assertEqual("valid_pareto64_deployment_lifecycle", receipt["status"])
            self.assertEqual("normal_repack", receipt["deployment_mode"])
            self.assertEqual([], receipt["shared_mappings"])


if __name__ == "__main__":
    unittest.main()
