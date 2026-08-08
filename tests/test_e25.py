import hashlib
import json
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class E25DecodeLayoutTests(unittest.TestCase):
    def test_frozen_contract_and_primary_gate(self) -> None:
        contract = json.loads((ROOT / "experiments/e25_contract.json").read_text())
        summary = json.loads((ROOT / "results/raw/e25-summary.json").read_text())

        self.assertEqual(contract["experiment_id"], "E25")
        self.assertEqual(
            contract["starting_point"]["required_ancestor"],
            "1c830dbf6eeb6e9261cbe2613a22ea89b733ea22",
        )
        target = contract["gates"]["target_whole_model_tg128_ratio"]
        self.assertGreaterEqual(summary["primary_axion"]["tg128"]["ratio"], target)
        self.assertTrue(summary["primary_axion"]["tg128"]["passed"])
        self.assertGreaterEqual(summary["primary_axion"]["prefill_pp512"]["ratio"], 0.98)

    def test_patch_contains_the_selected_representation_and_kernel(self) -> None:
        patch = (ROOT / "patches/llama.cpp/e25/0003-q4-k-decoded-metadata-layout.patch").read_text()

        self.assertIn("block_q4_Kx8_decoded", patch)
        self.assertIn("ggml_gemv_q4_K_8x4_q8_K_decoded", patch)
        self.assertIn("const int bsum_offset = 4 * sb", patch)
        self.assertIn("const int16_t * row_bsums", patch)
        self.assertFalse(any(line.startswith("+") and "bsums_arr" in line for line in patch.splitlines()))

    def test_direct_and_regression_gates_are_bound(self) -> None:
        summary = json.loads((ROOT / "results/raw/e25-summary.json").read_text())
        primary = summary["primary_axion"]

        self.assertGreaterEqual(primary["direct"]["3072x2304"]["ratio"], 1.20)
        self.assertGreaterEqual(primary["direct"]["9216x768"]["ratio"], 1.20)
        self.assertTrue(primary["q6_guard"]["passed"])
        self.assertFalse(summary["second_arm"]["packed_real_model_dispatch_selected"])
        self.assertAlmostEqual(summary["second_arm"]["tg128_ratio"], 1.0, delta=0.01)

    def test_raw_evidence_inventories_match(self) -> None:
        for relative in (
            "results/raw/e25a-axion-20260808/file-inventory-sha256.txt",
            "results/raw/e25b-axion-20260808/file-inventory-sha256.txt",
            "results/raw/e25c-n1-20260808/file-inventory-sha256.txt",
            "results/raw/e25d-31251352112/file-inventory-sha256.txt",
        ):
            inventory = ROOT / relative
            self.assertTrue(inventory.is_file())
            for line in inventory.read_text().splitlines():
                expected, raw_path = line.split(maxsplit=1)
                path = ROOT / raw_path.strip()
                if not path.exists():
                    path = inventory.parent / raw_path.strip()
                self.assertTrue(path.is_file(), path)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_reproducer_workflow_and_disclosures_exist(self) -> None:
        reproducer = ROOT / "experiments/e25_q4_layout_reproduce.sh"
        report = (ROOT / "results/reports/e25-q4-k-decode-layout.md").read_text()

        self.assertTrue(os.access(reproducer, os.X_OK))
        self.assertTrue((ROOT / ".github/workflows/e25-q4-k-decode-layout.yml").is_file())
        self.assertIn("not byte-identical", report)
        self.assertIn("neutral on Neoverse N1", report)


if __name__ == "__main__":
    unittest.main()
