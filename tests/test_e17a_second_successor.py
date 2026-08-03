import unittest
from pathlib import Path

from experiments.e17a_second_successor_freeze import build_contract
from experiments.e17a_subset_probe import select_reference_subset


class E17aSecondSuccessorTests(unittest.TestCase):
    def test_subset_repair_does_not_change_scientific_contract(self) -> None:
        contract = build_contract(Path("."))
        self.assertEqual(contract["second_failure"]["configuration_processes_ready"], 3)
        self.assertEqual(contract["second_failure"]["measured_model_requests_completed"], 0)
        self.assertEqual(
            contract["execution"]["order"],
            ["f16_f16", "q8_0_q8_0", "q4_0_q4_0"],
        )
        self.assertEqual(
            contract["quality_preflight"]["task_ids"],
            ["arithmetic-02", "logic-01", "systems-04"],
        )
        self.assertFalse(
            contract["decision"]["second_successor_changes_scientific_contract"]
        )

    def test_adapter_filters_in_frozen_task_order(self) -> None:
        tasks = {"tasks": [{"id": "logic-01"}, {"id": "systems-04"}]}
        reference = {"systems-04": "B", "unused": "A", "logic-01": "C"}
        self.assertEqual(
            select_reference_subset(tasks, reference),
            {"logic-01": "C", "systems-04": "B"},
        )

    def test_adapter_fails_closed_on_duplicate_or_missing_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "not uniquely covered"):
            select_reference_subset(
                {"tasks": [{"id": "logic-01"}, {"id": "logic-01"}]},
                {"logic-01": "C"},
            )
        with self.assertRaisesRegex(ValueError, "not uniquely covered"):
            select_reference_subset(
                {"tasks": [{"id": "missing"}]},
                {"logic-01": "C"},
            )


if __name__ == "__main__":
    unittest.main()
