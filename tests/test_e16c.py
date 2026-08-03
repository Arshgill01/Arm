from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from experiments.e16c_shared_arena_freeze import build_contract
from experiments.e16c_shared_arena_ingest import (
    parse_sidecar_mapping,
    summarize_configuration,
)


class E16cSharedArenaTests(unittest.TestCase):
    def test_frozen_contract_matches_generator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        frozen = root / "experiments/e16c_contract.json"
        if not frozen.exists():
            self.skipTest("E16c contract has not been frozen yet")
        self.assertEqual(json.loads(frozen.read_text()), build_contract(root))

    def test_order_is_reverse_balanced_and_complete(self) -> None:
        root = Path(__file__).resolve().parents[1]
        contract = build_contract(root)
        order = contract["execution"]["order"]
        pairs = [(item["configuration"], item["repetition"]) for item in order]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertEqual(
            Counter(name for name, _ in pairs),
            {"normal_repack_workers": 4, "shared_sidecar_workers": 4},
        )
        self.assertEqual(
            [name for name, _ in pairs],
            [
                "normal_repack_workers",
                "shared_sidecar_workers",
                "shared_sidecar_workers",
                "normal_repack_workers",
                "shared_sidecar_workers",
                "normal_repack_workers",
                "normal_repack_workers",
                "shared_sidecar_workers",
            ],
        )

    def test_contract_uses_summed_pss_and_keeps_claims_bounded(self) -> None:
        root = Path(__file__).resolve().parents[1]
        contract = build_contract(root)
        acceptance = contract["acceptance"]
        self.assertEqual(contract["execution"]["measured_worker_processes"], 16)
        self.assertEqual(contract["execution"]["total_measured_requests"], 480)
        self.assertLessEqual(
            acceptance["maximum_summed_post_workload_pss_ratio"], 0.75
        )
        self.assertGreaterEqual(
            acceptance["minimum_summed_post_workload_pss_saved_kib"], 1024**2
        )
        self.assertFalse(
            contract["mechanism"]["per_process_rss_memory_claim_allowed"]
        )
        self.assertIn("cannot claim per-process RSS", contract["claim_boundary"])

    def test_map_parser_binds_permissions_offset_device_and_inode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "maps.txt"
            path.write_text(
                "ffff0000-ffff1000 r--s 00100000 08:01 42 "
                "/tmp/pareto64-e16c-sidecar.bin\n",
                encoding="utf-8",
            )
            self.assertEqual(
                parse_sidecar_mapping(path),
                (
                    "r--s",
                    "00100000",
                    "08:01:42:/tmp/pareto64-e16c-sidecar.bin",
                ),
            )
            path.write_text("ffff0000-ffff1000 rw-p 0 00:00 0 [heap]\n")
            self.assertIsNone(parse_sidecar_mapping(path))

    def test_configuration_summary_uses_group_values_and_all_cases(self) -> None:
        worker = {
            "probe": {
                "correct": 23,
                "failures": 0,
                "reference_prediction_mismatches": 0,
            },
            "prediction_map": {"task": "A"},
        }
        group = {
            "group": {
                "requests_per_second": 2.0,
                "server_cpu_seconds_per_request": 1.0,
                "measurement_start_skew_ms": 0.2,
            },
            "workers": [worker, worker],
            "raw_cases": [
                {"http_ms": 900, "encode_ms": 800, "decode_ms": 50},
                {"http_ms": 1100, "encode_ms": 1000, "decode_ms": 60},
            ],
            "summed_post_workload_pss_kib": 4000,
            "summed_post_workload_rss_kib": 5000,
            "group_ready_ms": 100,
        }
        summary = summarize_configuration([group])
        self.assertEqual(summary["aggregate_requests_per_second"]["median"], 2.0)
        self.assertEqual(summary["http_ms"]["median"], 1000)
        self.assertEqual(summary["quality"]["correct_per_worker"], [23, 23])


if __name__ == "__main__":
    unittest.main()
