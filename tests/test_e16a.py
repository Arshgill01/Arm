from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from experiments.e16a_freeze import build_contract
from experiments.e16a_ingest import inventory_matches_header, metadata_without_hashes
from experiments.e16a_sidecar import build_sidecar, parse_inventory, verify_sidecar


class E16aSidecarTests(unittest.TestCase):
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
            "buffer_base\tbuffer_size_bytes\n0x12340000\t16\n",
            encoding="utf-8",
        )
        (dump / "a.weight.bin").write_bytes(b"abcd")
        (dump / "b.weight.bin").write_bytes(b"xyz")
        return dump

    def test_sidecar_is_deterministic_and_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dump = self.make_dump(root)
            identity = {"model_sha256": "a" * 64, "cpu": {"architecture": "aarch64"}}
            indexes = []
            for repetition in (1, 2):
                sidecar = root / f"sidecar-{repetition}.bin"
                index_path = root / f"index-{repetition}.json"
                index = build_sidecar(dump, identity, sidecar)
                index_path.write_text(
                    json.dumps(index, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                self.assertEqual(
                    verify_sidecar(sidecar, index_path)["status"], "valid_sidecar"
                )
                indexes.append(index)
            self.assertEqual(indexes[0]["header"], indexes[1]["header"])
            self.assertEqual(indexes[0]["sidecar_sha256"], indexes[1]["sidecar_sha256"])
            self.assertEqual(indexes[0]["header"]["tensor_count"], 2)
            self.assertEqual(indexes[0]["header"]["packed_tensor_bytes"], 7)

    def test_overlap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dump = self.make_dump(Path(directory))
            inventory = dump / "inventory.tsv"
            inventory.write_text(
                inventory.read_text(encoding="utf-8").replace("\t3\t8\t", "\t3\t2\t"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "overlap"):
                parse_inventory(dump)

    def test_retained_inventory_matches_header_without_binary_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dump = self.make_dump(Path(directory))
            tensors, _ = parse_inventory(dump)
            rows = [
                {
                    key: str(tensor[key])
                    for key in (
                        "tensor",
                        "file",
                        "type",
                        "parameter_type",
                        "ne0",
                        "ne1",
                        "ne2",
                        "ne3",
                        "bytes",
                        "buffer_offset",
                        "columns",
                        "interleave",
                    )
                }
                for tensor in tensors
            ]
            self.assertTrue(inventory_matches_header(rows, tensors))
            rows[0]["buffer_offset"] = "1"
            self.assertFalse(inventory_matches_header(rows, tensors))

    def test_metadata_comparison_excludes_only_tensor_hashes(self) -> None:
        index = {
            "header": {
                "tensors": [{"tensor": "a.weight", "bytes": 4, "sha256": "a" * 64}]
            }
        }
        self.assertEqual(
            metadata_without_hashes(index), [{"tensor": "a.weight", "bytes": 4}]
        )

    def test_tampered_sidecar_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dump = self.make_dump(root)
            sidecar = root / "sidecar.bin"
            index_path = root / "index.json"
            index = build_sidecar(dump, {"architecture": "aarch64"}, sidecar)
            index_path.write_text(
                json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            with sidecar.open("r+b") as handle:
                handle.seek(index["header"]["data_offset"])
                handle.write(b"Z")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify_sidecar(sidecar, index_path)

    def test_entrypoints_are_directly_runnable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for script in (
            "e16a_sidecar.py",
            "e16a_freeze.py",
            "e16a_ingest.py",
            "e16a_retain.py",
        ):
            completed = subprocess.run(
                [sys.executable, str(root / "experiments" / script), "--help"],
                cwd=root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_frozen_contract_matches_generator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        frozen = json.loads((root / "experiments/e16a_contract.json").read_text())
        self.assertEqual(frozen, build_contract(root))

    def test_contract_is_a_preflight_not_a_performance_claim(self) -> None:
        root = Path(__file__).resolve().parents[1]
        contract = build_contract(root)
        self.assertEqual(contract["execution"]["total_fresh_processes"], 2)
        self.assertEqual(contract["execution"]["total_measured_requests"], 60)
        self.assertEqual(contract["acceptance"]["minimum_tensor_count"], 100)
        self.assertTrue(
            contract["mechanism"]["absolute_buffer_base_excluded_from_sidecar"]
        )
        self.assertIn("cannot claim a usable loader", contract["claim_boundary"])

    def test_retained_native_result_authorizes_only_loader_successor(self) -> None:
        root = Path(__file__).resolve().parents[1]
        retained = json.loads(
            (root / "results/manifests/e16a-30837796757.json").read_text()
        )
        self.assertEqual(retained["status"], "valid_loader_feasibility")
        self.assertTrue(retained["decision"]["loader_experiment_authorized"])
        self.assertTrue(retained["loader_successor_authorized"])
        self.assertFalse(retained["decision"]["performance_claim_permitted"])
        self.assertEqual(
            retained["sidecar"]["sha256_per_repetition"][0],
            retained["sidecar"]["sha256_per_repetition"][1],
        )
        self.assertEqual(retained["sidecar"]["tensor_count_per_repetition"], [183, 183])
        self.assertFalse(
            retained["artifact_validation"]["inventory"][
                "generated_raw_tensor_or_sidecar_binaries_retained"
            ]
        )


if __name__ == "__main__":
    unittest.main()
