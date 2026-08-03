from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from experiments.e16b_freeze import build_contract
from experiments.e16b_ingest import parse_page_faults, parse_smaps_rollup


class E16bLoaderTests(unittest.TestCase):
    def test_frozen_contract_matches_generator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        frozen = root / "experiments/e16b_contract.json"
        if not frozen.exists():
            self.skipTest("E16b contract has not been frozen yet")
        self.assertEqual(json.loads(frozen.read_text()), build_contract(root))

    def test_order_is_position_balanced_and_complete(self) -> None:
        root = Path(__file__).resolve().parents[1]
        contract = build_contract(root)
        order = contract["execution"]["order"]
        pairs = [(item["configuration"], item["repetition"]) for item in order]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertEqual(
            Counter(name for name, _ in pairs),
            {"normal_repack": 4, "sidecar_loader": 4},
        )
        self.assertEqual(
            [name for name, _ in pairs],
            [
                "normal_repack",
                "sidecar_loader",
                "sidecar_loader",
                "normal_repack",
                "sidecar_loader",
                "normal_repack",
                "normal_repack",
                "sidecar_loader",
            ],
        )

    def test_contract_retains_strict_claim_boundary(self) -> None:
        root = Path(__file__).resolve().parents[1]
        contract = build_contract(root)
        self.assertEqual(contract["acceptance"]["request_failures"], 0)
        self.assertEqual(contract["acceptance"]["reference_prediction_mismatches"], 0)
        self.assertGreaterEqual(
            contract["acceptance"]["minimum_throughput_retention_ratio"], 0.97
        )
        self.assertIn(
            "page cache is neither flushed nor claimed cold",
            contract["measurement_boundary"],
        )
        self.assertIn("multi-process", contract["claim_boundary"])

    def test_patch_is_read_only_fail_closed_and_default_off(self) -> None:
        root = Path(__file__).resolve().parents[1]
        patch = (
            root / "patches/llama.cpp/b10216/0007-repack-sidecar-readonly-loader.patch"
        ).read_text()
        for required in (
            'std::getenv("GGML_CPU_REPACK_SIDECAR")',
            "PROT_READ",
            "MAP_SHARED",
            "binding differs for",
            "layout differs for tensor",
            "attempted to modify read-only mapped weights",
            "without runtime repacking",
        ):
            self.assertIn(required, patch)

    def test_smaps_and_page_fault_parsers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            smaps = root / "smaps.txt"
            smaps.write_text(
                "00400000-00401000 ---p 00000000 00:00 0 [rollup]\n"
                "Rss:                100 kB\n"
                "Pss:                 80 kB\n"
                "Shared_Clean:        40 kB\n"
                "Shared_Dirty:         0 kB\n"
                "Private_Clean:       20 kB\n"
                "Private_Dirty:       40 kB\n"
                "Anonymous:           40 kB\n"
                "Swap:                 0 kB\n",
                encoding="utf-8",
            )
            self.assertEqual(parse_smaps_rollup(smaps)["Pss"], 80)
            timing = root / "time.txt"
            timing.write_text(
                "Major (requiring I/O) page faults: 3\n"
                "Minor (reclaiming a frame) page faults: 99\n",
                encoding="utf-8",
            )
            self.assertEqual(parse_page_faults(timing), {"major": 3, "minor": 99})


if __name__ == "__main__":
    unittest.main()
