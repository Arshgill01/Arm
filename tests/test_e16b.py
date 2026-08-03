from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from experiments.e16b_freeze import build_contract
from experiments.e16b_ingest import (
    parse_page_faults,
    parse_smaps_rollup,
    summarize_configuration,
)


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

    def test_configuration_summary_reads_cases_from_validated_cell(self) -> None:
        cell = {
            "probe": {
                "correct": 23,
                "failures": 0,
                "reference_prediction_mismatches": 0,
                "requests_per_second": 1.0,
            },
            "raw_cases": [{"http_ms": 1000, "encode_ms": 900, "decode_ms": 50}],
            "prediction_map": {"task": "A"},
            "process_cpu": {"seconds_per_request": 1.0},
            "process": {"maximum_rss_kib": 1000},
            "smaps_rollup_kib": {"Rss": 900, "Pss": 800},
            "ready_ms": 100,
            "page_faults": {"major": 0, "minor": 1},
        }
        summary = summarize_configuration([cell])
        self.assertEqual(summary["http_ms"]["median"], 1000)
        self.assertEqual(summary["quality"]["correct_per_repetition"], [23])


if __name__ == "__main__":
    unittest.main()
