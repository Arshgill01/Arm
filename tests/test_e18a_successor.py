import copy
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e18a_successor_freeze import build_contract
from experiments.e18a_successor_ingest import validate_training
from experiments.e5b_ingest import sha256_file


class E18aSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(".")
        cls.original = json.loads(
            (cls.root / "experiments/e18a_contract.json").read_text()
        )

    def test_successor_changes_only_training_timeout_boundary(self) -> None:
        successor = build_contract(self.root)
        self.assertEqual(successor["request"], self.original["request"])
        self.assertEqual(successor["acceptance"], self.original["acceptance"])
        self.assertEqual(successor["execution"], self.original["execution"])
        self.assertEqual(successor["build"], self.original["build"])
        self.assertEqual(successor["service"], self.original["service"])
        self.assertEqual(successor["training"]["request_timeout_seconds"], 180.0)
        self.assertEqual(
            successor["inputs"]["predecessor_failure_sha256"],
            sha256_file(
                self.root
                / "results/manifests/e18a-training-timeout-30858852227.json"
            ),
        )

    def test_training_adapter_rejects_any_other_timeout_boundary(self) -> None:
        contract = build_contract(self.root)
        contract["training"]["request_timeout_seconds"] = 179.0
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "timeout boundary"):
                validate_training(Path(directory), contract, [], {})

    def test_original_contract_is_unchanged(self) -> None:
        before = copy.deepcopy(self.original)
        build_contract(self.root)
        self.assertEqual(
            json.loads((self.root / "experiments/e18a_contract.json").read_text()),
            before,
        )


if __name__ == "__main__":
    unittest.main()
