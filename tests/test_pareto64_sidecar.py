from __future__ import annotations

import hashlib
import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.e16a_sidecar import build_sidecar
from pareto64.planner import sha256_file
from pareto64.sidecar import (
    _evidence_boundaries,
    cleanup_sidecar,
    execute_sidecar_group,
    prepack_sidecar,
    prepare_normal_launch,
    prepare_sidecar_launch,
    verify_product_sidecar,
)


class Pareto64SidecarTests(unittest.TestCase):
    def make_dump(self, root: Path) -> Path:
        dump = root / "dump"
        dump.mkdir()
        (dump / "inventory.tsv").write_text(
            "tensor\tfile\ttype\tparameter_type\tne0\tne1\tne2\tne3\tbytes\tbuffer_offset\tcolumns\tinterleave\n"
            "a.weight\ta.weight.bin\tq4_0\tq8_0\t32\t4\t1\t1\t4\t0\t4\t4\n"
            "b.weight\tb.weight.bin\tq4_0\tq8_0\t32\t4\t1\t1\t3\t8\t4\t4\n",
            encoding="utf-8",
        )
        (dump / "runtime.tsv").write_text(
            "buffer_base\tbuffer_size_bytes\n0x12340000\t16\n", encoding="utf-8"
        )
        (dump / "a.weight.bin").write_bytes(b"abcd")
        (dump / "b.weight.bin").write_bytes(b"xyz")
        return dump

    def make_product(self, root: Path) -> dict[str, object]:
        commit = "876a4321163249c43ca4e986818fab5ab081f282"
        model = root / "model.gguf"
        model.write_bytes(b"tiny model fixture")
        model_sha = sha256_file(model)
        runtime = root / "runtime"
        server = runtime / "bin/llama-server"
        server.parent.mkdir(parents=True)
        server.write_text(f"#!/bin/sh\necho 'version: 10216 ({commit[:9]})'\n")
        server.chmod(0o755)
        single = Path("results/manifests/e16b-30842925537.json").resolve()
        contract = {
            "schema_version": 1,
            "experiment_id": "E16c",
            "selected": {
                "candidate": "ministral3_3b_q4_k_m",
                "model_sha256": model_sha,
                "model_size_bytes": model.stat().st_size,
            },
            "source": {
                "commit": commit,
                "aggregate_diff_sha256": "a" * 64,
            },
            "mechanism": {
                "dump_format_version": 1,
                "sidecar_format_version": 1,
                "proof_log_verbosity": 4,
            },
            "inputs": {
                "e16b_result_path": str(single),
                "e16b_result_sha256": sha256_file(single),
            },
            "claim_boundary": "tiny test boundary",
        }
        contract_path = root / "contract.json"
        contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
        identity = {
            "schema_version": 1,
            "experiment_id": "E16c",
            "source_model_sha256": model_sha,
            "llama_cpp_commit": commit,
            "source_diff_sha256": "a" * 64,
            "repack_dump_format_version": 1,
            "sidecar_format_version": 1,
            "cpu": {
                "architecture": "aarch64",
                "cpu_implementers": ["0x41"],
                "cpu_parts": ["0xd49"],
                "common_features": ["asimd", "asimddp"],
                "common_features_sha256": hashlib.sha256(b"asimd\nasimddp").hexdigest(),
                "sve_vector_length_bytes": 0,
            },
        }
        evidence = {
            "schema_version": 1,
            "experiment_id": "E16c",
            "status": "valid_shared_sidecar_workers_promoted",
            "promoted": True,
            "gates": {"all": True},
            "decision": {
                "multi_process_physical_sharing_claim_permitted": True,
            },
            "contract_sha256": sha256_file(contract_path),
            "source_build": {
                "runtime_closure": {
                    "server_relative_path": "bin/llama-server",
                    "file_count": 1,
                    "files": [
                        {
                            "relative_path": "bin/llama-server",
                            "size_bytes": server.stat().st_size,
                            "sha256": sha256_file(server),
                        }
                    ],
                }
            },
            "sidecar_identity": identity,
            "ratios": {"summed_post_workload_pss": 0.69},
            "summed_post_workload_pss_saved_kib": 2_000_000,
            "github": {"run_id": "fixture"},
        }
        evidence_path = root / "evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
        sidecar = root / "weights.sidecar"
        index_path = root / "weights.index.json"
        index = build_sidecar(self.make_dump(root), identity, sidecar)
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
        sidecar.chmod(0o444)
        index_path.chmod(0o444)
        receipt = {
            "schema_version": 1,
            "status": "valid_persistent_arm_sidecar",
            "contract": {"sha256": sha256_file(contract_path)},
            "evidence": {"sha256": sha256_file(evidence_path)},
            "model": {"sha256": model_sha},
            "runtime": {"server_sha256": sha256_file(server)},
            "sidecar": {
                "path": str(sidecar.resolve()),
                "index_path": str(index_path.resolve()),
                "index_sha256": sha256_file(index_path),
                "index_size_bytes": index_path.stat().st_size,
                "sha256": index["sidecar_sha256"],
            },
            "identity": identity,
        }
        receipt_path = root / "receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        receipt_path.chmod(0o444)
        return {
            "contract": contract_path,
            "evidence": evidence_path,
            "model": model,
            "server": server,
            "sidecar": sidecar,
            "index": index_path,
            "receipt": receipt_path,
            "identity": identity,
        }

    def verify(self, product: dict[str, object]) -> dict[str, object]:
        with patch(
            "pareto64.sidecar.create_identity", return_value=product["identity"]
        ):
            return verify_product_sidecar(
                contract_path=product["contract"],
                evidence_path=product["evidence"],
                model_path=product["model"],
                server_path=product["server"],
                sidecar_path=product["sidecar"],
                index_path=product["index"],
                receipt_path=product["receipt"],
            )

    def test_verify_binds_model_runtime_cpu_and_read_only_container(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            result = self.verify(product)
            self.assertEqual(result["status"], "valid_persistent_arm_sidecar")
            self.assertTrue(result["read_only"])
            self.assertTrue(result["receipt_verified"])
            self.assertEqual(result["mapping"]["protection"], "PROT_READ")
            self.assertEqual(result["mapping"]["sharing"], "MAP_SHARED")
            self.assertEqual(result["tensor_count"], 2)

    def test_tensor_corruption_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            sidecar = product["sidecar"]
            sidecar.chmod(0o600)
            with sidecar.open("r+b") as handle:
                handle.seek(1024 * 1024)
                handle.write(b"Z")
            sidecar.chmod(0o444)
            with self.assertRaisesRegex(ValueError, "differs"):
                self.verify(product)

    def test_magic_corruption_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            sidecar = product["sidecar"]
            sidecar.chmod(0o600)
            with sidecar.open("r+b") as handle:
                handle.write(b"X")
            sidecar.chmod(0o444)
            with self.assertRaisesRegex(ValueError, "magic differs"):
                self.verify(product)

    def test_model_and_runtime_closure_corruption_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            product["model"].write_bytes(b"different model")
            with self.assertRaisesRegex(ValueError, "model differs"):
                self.verify(product)
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            product["server"].write_text("#!/bin/sh\necho corrupt\n")
            product["server"].chmod(0o755)
            with self.assertRaisesRegex(ValueError, "runtime closure differs"):
                self.verify(product)

    def test_writable_container_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            product["sidecar"].chmod(0o644)
            with self.assertRaisesRegex(ValueError, "regular read-only"):
                self.verify(product)

    def test_symlink_container_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            product = self.make_product(root)
            linked = root / "linked.sidecar"
            linked.symlink_to(product["sidecar"])
            with (
                patch(
                    "pareto64.sidecar.create_identity", return_value=product["identity"]
                ),
                self.assertRaisesRegex(ValueError, "regular read-only"),
            ):
                verify_product_sidecar(
                    contract_path=product["contract"],
                    evidence_path=product["evidence"],
                    model_path=product["model"],
                    server_path=product["server"],
                    sidecar_path=linked,
                    index_path=product["index"],
                )

    def test_receipt_must_be_read_only_and_identity_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            product["receipt"].chmod(0o644)
            with self.assertRaisesRegex(ValueError, "receipt differs"):
                self.verify(product)
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            receipt = product["receipt"]
            receipt.chmod(0o600)
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["identity"]["cpu"]["common_features_sha256"] = "0" * 64
            receipt.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            receipt.chmod(0o444)
            with self.assertRaisesRegex(ValueError, "receipt differs"):
                self.verify(product)

    def test_cpu_identity_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            wrong = json.loads(json.dumps(product["identity"]))
            wrong["cpu"]["common_features_sha256"] = "0" * 64
            with (
                patch("pareto64.sidecar.create_identity", return_value=wrong),
                self.assertRaisesRegex(ValueError, "current model/source/CPU"),
            ):
                verify_product_sidecar(
                    contract_path=product["contract"],
                    evidence_path=product["evidence"],
                    model_path=product["model"],
                    server_path=product["server"],
                    sidecar_path=product["sidecar"],
                    index_path=product["index"],
                    receipt_path=product["receipt"],
                )

    def test_source_identity_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            wrong = json.loads(json.dumps(product["identity"]))
            wrong["source_diff_sha256"] = "0" * 64
            with (
                patch("pareto64.sidecar.create_identity", return_value=wrong),
                self.assertRaisesRegex(ValueError, "generated identity differs"),
            ):
                verify_product_sidecar(
                    contract_path=product["contract"],
                    evidence_path=product["evidence"],
                    model_path=product["model"],
                    server_path=product["server"],
                    sidecar_path=product["sidecar"],
                    index_path=product["index"],
                    receipt_path=product["receipt"],
                )

    def test_multi_worker_plan_verifies_once_then_shares_inode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            with patch(
                "pareto64.sidecar.create_identity", return_value=product["identity"]
            ):
                plan = prepare_sidecar_launch(
                    contract_path=product["contract"],
                    evidence_path=product["evidence"],
                    model_path=product["model"],
                    server_path=product["server"],
                    sidecar_path=product["sidecar"],
                    index_path=product["index"],
                    receipt_path=product["receipt"],
                    workers=2,
                    base_port=19081,
                )
            self.assertEqual(plan["verification_passes"], 1)
            self.assertIn("each worker mapping", plan["verification_scope"])
            self.assertEqual([item["port"] for item in plan["workers"]], [19081, 19082])
            self.assertEqual(
                {
                    item["environment"]["GGML_CPU_REPACK_SIDECAR"]
                    for item in plan["workers"]
                },
                {str(product["sidecar"].resolve())},
            )
            self.assertEqual(plan["sidecar"]["inode"], product["sidecar"].stat().st_ino)

    def test_normal_worker_plan_uses_the_same_verified_runtime_without_sidecar(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            with patch(
                "pareto64.sidecar.create_identity", return_value=product["identity"]
            ):
                plan = prepare_normal_launch(
                    contract_path=product["contract"],
                    evidence_path=product["evidence"],
                    model_path=product["model"],
                    server_path=product["server"],
                    workers=2,
                    threads=1,
                    base_port=19081,
                )
            self.assertEqual("ready_to_launch_normal_workers", plan["status"])
            self.assertEqual("normal_repack", plan["deployment_mode"])
            self.assertEqual(1, plan["threads_per_worker"])
            self.assertIsNone(plan["sidecar"])
            self.assertEqual(
                [{}, {}], [item["environment"] for item in plan["workers"]]
            )

    def test_execute_group_waits_for_health_and_writes_ready_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.py"
            worker.write_text(
                """\
import http.server
import sys
import threading

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass

server = http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler)
timer = threading.Timer(5.0, server.shutdown)
timer.daemon = True
timer.start()
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
""",
                encoding="utf-8",
            )
            with socket.socket() as candidate:
                candidate.bind(("127.0.0.1", 0))
                port = candidate.getsockname()[1]
            ready_path = root / "ready.json"
            stop_path = root / "stop"
            plan = {
                "status": "ready_to_launch_shared_sidecar_workers",
                "sidecar": {"path": "/fixture", "read_only": True},
                "workers": [
                    {
                        "worker": 1,
                        "host": "127.0.0.1",
                        "port": port,
                        "argv": [sys.executable, str(worker), str(port)],
                        "environment": {},
                    }
                ],
            }
            timer = threading.Timer(0.5, stop_path.touch)
            timer.start()
            outcome = execute_sidecar_group(
                plan,
                readiness_timeout=5.0,
                ready_output=ready_path,
                stop_file=stop_path,
            )
            timer.join()
            ready = json.loads(ready_path.read_text(encoding="utf-8"))
            self.assertEqual("shared_sidecar_workers_ready", ready["status"])
            self.assertEqual(1, ready["worker_count"])
            self.assertEqual("sidecar_worker_group_stopped", outcome["status"])
            self.assertTrue(outcome["stop_requested"])
            self.assertEqual(port, outcome["readiness"][0]["port"])

    def test_execute_group_retains_readiness_failure(self) -> None:
        plan = {
            "status": "ready_to_launch_shared_sidecar_workers",
            "sidecar": {"path": "/fixture", "read_only": True},
            "workers": [
                {
                    "worker": 1,
                    "host": "127.0.0.1",
                    "port": 1,
                    "argv": [sys.executable, "-c", "pass"],
                    "environment": {},
                }
            ],
        }
        outcome = execute_sidecar_group(plan, readiness_timeout=0.2)
        self.assertEqual("sidecar_worker_group_failed", outcome["status"])
        self.assertIn("exited before readiness", outcome["error"])
        self.assertEqual([], outcome["readiness"])

    def test_cleanup_requires_receipt_hash_and_retains_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            planned = cleanup_sidecar(product["receipt"])
            self.assertEqual(planned["status"], "sidecar_cleanup_planned")
            self.assertTrue(product["sidecar"].exists())
            complete = cleanup_sidecar(product["receipt"], execute=True)
            self.assertEqual(complete["status"], "sidecar_cleanup_complete")
            self.assertTrue(complete["targets_absent"])
            self.assertTrue(product["receipt"].exists())

    def test_cleanup_rejects_writable_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            product["receipt"].chmod(0o644)
            with self.assertRaisesRegex(ValueError, "does not match"):
                cleanup_sidecar(product["receipt"], execute=True)
            self.assertTrue(product["sidecar"].exists())
            self.assertTrue(product["index"].exists())

    def test_cleanup_rejects_tampered_receipt_without_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            receipt = product["receipt"]
            receipt.chmod(0o600)
            value = json.loads(receipt.read_text())
            value["sidecar"]["sha256"] = "0" * 64
            receipt.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
            with self.assertRaisesRegex(ValueError, "does not match"):
                cleanup_sidecar(receipt, execute=True)
            self.assertTrue(product["sidecar"].exists())
            self.assertTrue(product["index"].exists())

    def test_cleanup_rejects_corrupted_index_without_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            index = product["index"]
            index.chmod(0o600)
            value = json.loads(index.read_text(encoding="utf-8"))
            value["header"]["binding"]["cpu"]["common_features_sha256"] = "0" * 64
            index.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            index.chmod(0o444)
            with self.assertRaisesRegex(ValueError, "does not match"):
                cleanup_sidecar(product["receipt"], execute=True)
            self.assertTrue(product["sidecar"].exists())
            self.assertTrue(product["index"].exists())

    def test_lifecycle_boundaries_exclude_cold_energy_and_cost_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            product = self.make_product(Path(directory))
            contract = json.loads(product["contract"].read_text())
            evidence = json.loads(product["evidence"].read_text())
            boundaries = _evidence_boundaries(
                contract, evidence, product["identity"], 10.0
            )
            self.assertFalse(boundaries["cold_storage"]["measured"])
            self.assertFalse(boundaries["cold_storage"]["claim_permitted"])
            self.assertTrue(boundaries["warm_process_start"]["matched_native_evidence"])
            self.assertGreater(
                boundaries["amortization"][
                    "warm_start_break_even_worker_starts_estimate"
                ],
                0,
            )
            self.assertIn(
                "energy",
                boundaries["amortization"]["estimate_boundary"],
            )

    def test_prepack_rejects_overlapping_or_symlink_outputs_before_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = root / "shared"
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                prepack_sidecar(
                    contract_path=root / "contract.json",
                    evidence_path=root / "evidence.json",
                    model_path=root / "model.gguf",
                    server_path=root / "runtime/bin/llama-server",
                    sidecar_path=shared,
                    index_path=shared,
                    receipt_path=root / "receipt.json",
                    lifecycle_dir=root / "lifecycle",
                    scratch_root=root / "scratch",
                )
            sidecar = root / "sidecar"
            sidecar.symlink_to(root / "missing")
            with self.assertRaisesRegex(ValueError, "must not already exist"):
                prepack_sidecar(
                    contract_path=root / "contract.json",
                    evidence_path=root / "evidence.json",
                    model_path=root / "model.gguf",
                    server_path=root / "runtime/bin/llama-server",
                    sidecar_path=sidecar,
                    index_path=root / "index.json",
                    receipt_path=root / "receipt.json",
                    lifecycle_dir=root / "lifecycle",
                    scratch_root=root / "scratch",
                )


if __name__ == "__main__":
    unittest.main()
