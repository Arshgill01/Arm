import unittest
from pathlib import Path

from experiments.e15a_split_scheduler_freeze import build_contract
from experiments.e15a_split_scheduler_ingest import evaluate, expected_server_argv


class E15aTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = build_contract(Path("."))

    def test_four_points_change_only_the_two_thread_pools(self) -> None:
        configs = self.contract["execution"]["configurations"]
        self.assertEqual(
            {
                name: (config["threads_decode"], config["threads_batch"])
                for name, config in configs.items()
            },
            {
                "tied4_4": (4, 4),
                "split2_4": (2, 4),
                "split1_4": (1, 4),
                "prefill_control4_2": (4, 2),
            },
        )
        ignored = {"threads_decode", "threads_batch"}
        baseline = configs["tied4_4"]
        for config in configs.values():
            self.assertEqual(
                {key: value for key, value in config.items() if key not in ignored},
                {key: value for key, value in baseline.items() if key not in ignored},
            )

    def test_williams_order_balances_every_position(self) -> None:
        order = self.contract["execution"]["order"]
        by_repetition = {
            repetition: [
                item["configuration"]
                for item in order
                if item["repetition"] == repetition
            ]
            for repetition in range(1, 5)
        }
        for name in self.contract["execution"]["configurations"]:
            positions = [values.index(name) for values in by_repetition.values()]
            self.assertEqual(sorted(positions), [0, 1, 2, 3])

    def test_expected_argv_binds_pools_independently(self) -> None:
        argv = expected_server_argv(
            "/tmp/runtime-files/bin/llama-server",
            "/tmp/model.gguf",
            self.contract,
            "split2_4",
        )
        self.assertEqual(argv[argv.index("--threads") + 1], "2")
        self.assertEqual(argv[argv.index("--threads-batch") + 1], "4")
        self.assertEqual(argv.count("--threads"), 1)
        self.assertEqual(argv.count("--threads-batch"), 1)

    def test_selection_requires_cpu_and_service_gates(self) -> None:
        def profile(throughput: float, latency: float, cpu: float):
            return {
                "threads_decode": 2,
                "quality": {
                    "exact_selected_predictions": True,
                    "predictions_stable_between_repetitions": True,
                },
                "cached_tokens": {"min": 1.0},
                "requests_per_second": {
                    "median": throughput,
                    "coefficient_of_variation": 0.01,
                },
                "http_ms": {"median": latency, "p95": latency},
                "encode_ms": {"median": latency},
                "server_cpu_seconds_per_request": {"median": cpu},
            }

        performance = {
            "tied4_4": profile(1.0, 100.0, 4.0),
            "split2_4": profile(0.99, 101.0, 3.9),
            "split1_4": profile(1.0, 100.0, 4.0),
            "prefill_control4_2": profile(1.1, 90.0, 3.0),
        }
        performance["tied4_4"]["threads_decode"] = 4
        performance["split1_4"]["threads_decode"] = 1
        performance["prefill_control4_2"]["threads_decode"] = 4
        decision = evaluate(performance, self.contract)
        self.assertEqual(decision["selected_configuration"], "split2_4")
        self.assertFalse(decision["profile_gates"]["prefill_control4_2"]["promotable"])
        performance["split2_4"]["server_cpu_seconds_per_request"]["median"] = 4.0
        self.assertEqual(
            evaluate(performance, self.contract)["selected_configuration"],
            "tied4_4",
        )


if __name__ == "__main__":
    unittest.main()
