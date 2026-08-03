import unittest
from pathlib import Path

from experiments.e17a_successor_freeze import build_contract


class E17aSuccessorTests(unittest.TestCase):
    def test_repair_does_not_change_scientific_contract(self) -> None:
        contract = build_contract(Path("."))
        self.assertEqual(contract["first_failure"]["configuration_attempts_started"], 0)
        self.assertEqual(
            contract["execution"]["order"],
            ["f16_f16", "q8_0_q8_0", "q4_0_q4_0"],
        )
        self.assertEqual(
            contract["first_failure"]["repair"],
            [
                "create the already-frozen cell evidence directory before invocation",
                "invoke the exact hash-bound cell runner through bash",
            ],
        )
        self.assertFalse(contract["decision"]["successor_changes_scientific_contract"])


if __name__ == "__main__":
    unittest.main()
