from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.e16e_lifecycle_freeze import build_contract
from experiments.e16e_lifecycle_retain import mechanism_log


class E16eLifecycleTests(unittest.TestCase):
    def test_contract_freezes_one_reader_repair_without_new_measurement(self) -> None:
        contract = build_contract(Path.cwd())
        self.assertEqual("E16e", contract["experiment_id"])
        self.assertEqual(14, contract["acceptance"]["unchanged_e16d_gates"])
        self.assertEqual(0, contract["repair"]["native_measurements_added"])
        self.assertFalse(contract["repair"]["acceptance_gate_changes_permitted"])
        self.assertEqual("failure", contract["predecessor"]["workflow_conclusion"])

    def test_byte_reader_accepts_non_utf8_tokenizer_diagnostics(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "worker.stderr.log"
            path.write_bytes(
                b'tokenizer piece = ["\xc4\xa0", "\xc4..."]\n'
                b"CPU repack sidecar: mapped 100 bytes read-only "
                b"from /tmp/sidecar with 2 bound tensors\n"
                b"CPU repack sidecar: validated and loaded all 2 tensors "
                b"without runtime repacking\n"
            )
            with self.assertRaises(UnicodeDecodeError):
                path.read_text(encoding="utf-8")
            result = mechanism_log(path, 100, 2)

        self.assertTrue(result["mapped_read_only"])
        self.assertTrue(result["all_tensors_loaded_without_runtime_repacking"])
        self.assertFalse(result["identity_rejection_observed"])


if __name__ == "__main__":
    unittest.main()
