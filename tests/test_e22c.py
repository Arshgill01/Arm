from __future__ import annotations

import json
import unittest
from pathlib import Path

from experiments.e22a_freeze import sha256_file
from experiments.e22c_freeze import build_contract
from experiments.e22c_ingest import distribution


class E22cRepeatedMaximumDensityTests(unittest.TestCase):
    @property
    def root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_frozen_contract_matches_generator(self) -> None:
        contract_path = self.root / "experiments/e22c_contract.json"
        frozen = json.loads(contract_path.read_text())
        self.assertEqual(frozen, build_contract(self.root))
        self.assertEqual(
            "9bc0e63c4a59e5b9efaba176a47f5efe4b8b4664e27847dae0d675d06a360207",
            sha256_file(contract_path),
        )

    def test_order_balances_modes_and_repetitions(self) -> None:
        contract = build_contract(self.root)
        order = contract["matrix"]["order"]
        self.assertEqual("NSSNSNNS", "".join(cell["mode"][0].upper() for cell in order))
        self.assertEqual(list(range(1, 9)), [cell["position"] for cell in order])
        for repetition in range(1, 5):
            cells = [cell for cell in order if cell["repetition"] == repetition]
            self.assertEqual({"normal", "shared"}, {cell["mode"] for cell in cells})

    def test_final_gates_are_frozen_above_curve_thresholds(self) -> None:
        advance = build_contract(self.root)["advance"]
        self.assertEqual(1.25, advance["minimum_median_aggregate_throughput_ratio"])
        self.assertEqual(1.20, advance["minimum_each_paired_aggregate_throughput_ratio"])
        self.assertEqual(0.10, advance["maximum_mode_throughput_coefficient_of_variation"])
        self.assertFalse(advance["post_result_gate_change_permitted"])

    def test_distribution_is_population_summary(self) -> None:
        result = distribution([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(2.5, result["median"])
        self.assertEqual(1.0, result["minimum"])
        self.assertEqual(4.0, result["maximum"])
        self.assertAlmostEqual(1.118033988749895, result["population_standard_deviation"])


if __name__ == "__main__":
    unittest.main()
