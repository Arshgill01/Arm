import json
import unittest
from pathlib import Path

from experiments.e5b_ingest import load_object
from experiments.e17b_probe import task_user_text
from experiments.e17c_freeze import build_contract, task_identity


class E17cTests(unittest.TestCase):
    def test_frozen_contract_matches_generator(self) -> None:
        path = Path("experiments/e17c_contract.json")
        if not path.exists():
            self.skipTest("E17c contract has not been frozen")
        self.assertEqual(json.loads(path.read_text()), build_contract(Path(".")))

    def test_successor_is_separate_and_bounded(self) -> None:
        contract = build_contract(Path("."))
        self.assertEqual(contract["experiment_id"], "E17c")
        self.assertEqual(contract["predecessor"]["experiment_id"], "E17b")
        self.assertFalse(contract["predecessor"]["failed_contract_rehabilitated"])
        self.assertEqual(contract["workload"]["context_tokens_per_slot"], 8192)
        self.assertEqual(contract["workload"]["prompt_token_minimum"], 4500)
        self.assertEqual(contract["workload"]["prompt_token_maximum"], 5000)
        self.assertFalse(contract["decision"]["sixteen_k_claim_allowed"])

    def test_task_identities_are_inherited_before_results(self) -> None:
        old = load_object(Path("experiments/e17b_tasks.json"))
        new = load_object(Path("experiments/e17c_tasks.json"))
        self.assertEqual(
            [task_identity(item) for item in old["tasks"]],
            [task_identity(item) for item in new["tasks"]],
        )
        self.assertEqual(old["system_instruction"], new["system_instruction"])
        self.assertNotEqual(old["target_prompt_tokens"], new["target_prompt_tokens"])

    def test_execution_order_and_gates_are_not_weakened(self) -> None:
        predecessor = load_object(Path("experiments/e17b_contract.json"))
        contract = build_contract(Path("."))
        self.assertEqual(
            contract["execution"]["cells"], predecessor["execution"]["cells"]
        )
        self.assertEqual(
            contract["execution"]["configurations"],
            predecessor["execution"]["configurations"],
        )
        self.assertEqual(contract["acceptance"], predecessor["acceptance"])

    def test_shorter_ledger_remains_deterministic(self) -> None:
        task = load_object(Path("experiments/e17c_tasks.json"))["tasks"][7]
        first = task_user_text(task, 100)
        self.assertEqual(first, task_user_text(task, 100))
        self.assertEqual(first.count(task["retrieval_key"]), 2)
        self.assertEqual(first.count(task["options"][3]), 2)


if __name__ == "__main__":
    unittest.main()
