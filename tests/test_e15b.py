from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from experiments.e15b_affinity_freeze import build_contract
from experiments.e15b_affinity_ingest import expand_cpu_list


class E15bAffinitySchedulerTests(unittest.TestCase):
    def test_frozen_contract_matches_generator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        frozen = root / "experiments/e15b_contract.json"
        if not frozen.exists():
            self.skipTest("E15b contract has not been frozen yet")
        self.assertEqual(json.loads(frozen.read_text()), build_contract(root))

    def test_only_confirmatory_two_point_boundary_remains(self) -> None:
        contract = build_contract(Path("."))
        configs = contract["execution"]["configurations"]
        self.assertEqual(
            {
                name: (config["threads_decode"], config["threads_batch"])
                for name, config in configs.items()
            },
            {"tied4_4": (4, 4), "split2_4": (2, 4)},
        )
        ignored = {"threads_decode", "threads_batch"}
        self.assertEqual(
            {
                key: value
                for key, value in configs["tied4_4"].items()
                if key not in ignored
            },
            {
                key: value
                for key, value in configs["split2_4"].items()
                if key not in ignored
            },
        )

    def test_six_pairs_are_position_balanced(self) -> None:
        contract = build_contract(Path("."))
        order = contract["execution"]["order"]
        self.assertEqual(len(order), 12)
        self.assertEqual(
            Counter(item["configuration"] for item in order),
            {"tied4_4": 6, "split2_4": 6},
        )
        for name in contract["execution"]["configurations"]:
            positions = [
                index % 2
                for index, item in enumerate(order)
                if item["configuration"] == name
            ]
            self.assertEqual(Counter(positions), {0: 3, 1: 3})

    def test_original_performance_gates_are_not_weakened(self) -> None:
        root = Path(".")
        successor = build_contract(root)["acceptance"]
        predecessor = json.loads((root / "experiments/e15a_contract.json").read_text())[
            "acceptance"
        ]
        shared = (
            "minimum_candidate_throughput_ratio",
            "maximum_candidate_median_http_latency_ratio",
            "maximum_candidate_p95_http_latency_ratio",
            "maximum_candidate_cpu_seconds_per_request_ratio",
            "maximum_candidate_encode_latency_ratio",
            "maximum_throughput_coefficient_of_variation",
        )
        self.assertEqual(
            {name: successor[name] for name in shared},
            {name: predecessor[name] for name in shared},
        )
        self.assertFalse(successor["post_result_gate_change_permitted"])

    def test_cpu_list_parser_accepts_ranges_and_rejects_descending(self) -> None:
        self.assertEqual(expand_cpu_list("0-1,4,6-7"), [0, 1, 4, 6, 7])
        with self.assertRaises(ValueError):
            expand_cpu_list("3-1")

    def test_runner_pins_server_client_and_records_every_server_thread(self) -> None:
        runner = Path("experiments/e15b_affinity_cell.sh").read_text()
        self.assertGreaterEqual(runner.count('taskset --cpu-list "$affinity_cpu_list"'), 3)
        self.assertIn("thread_affinities", runner)
        self.assertIn("os.sched_getaffinity(int(task.name))", runner)
        self.assertIn("--experiment-id E15b", runner)


if __name__ == "__main__":
    unittest.main()
