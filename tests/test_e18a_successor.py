import copy
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from experiments.e18a_successor_freeze import build_contract
from experiments.e18a_successor_ingest import build_manifest, validate_training
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

    def test_training_adapter_delegates_without_recursive_monkeypatch(self) -> None:
        contract = build_contract(self.root)
        delegated = {"performance_claim_allowed": False}
        with mock.patch(
            "experiments.e18a_successor_ingest._BASE_VALIDATE_TRAINING",
            return_value=delegated,
        ) as original:
            observed = validate_training(Path("evidence"), contract, [], {})
        adjusted = original.call_args.args[1]
        self.assertEqual(adjusted["request"]["timeout_seconds"], 180.0)
        self.assertEqual(contract["request"]["timeout_seconds"], 30.0)
        self.assertEqual(observed["request_timeout_seconds"], 180.0)
        self.assertEqual(observed["timeout_scope"], "instrumented training only")

    def test_original_contract_is_unchanged(self) -> None:
        before = copy.deepcopy(self.original)
        build_contract(self.root)
        self.assertEqual(
            json.loads((self.root / "experiments/e18a_contract.json").read_text()),
            before,
        )

    def test_successor_manifest_adds_decision_when_base_has_none(self) -> None:
        contract = build_contract(self.root)
        base_result = {"campaign_variant": None, "predecessor_failure": None}
        with tempfile.TemporaryDirectory() as directory:
            contract_path = Path(directory) / "contract.json"
            contract_path.write_text(json.dumps(contract))
            with (
                mock.patch(
                    "experiments.e18a_successor_ingest.load_object",
                    side_effect=[contract, {
                        "status": "invalid_instrumented_training_timeout_after_complete_matrix",
                        "decision": {
                            "separately_frozen_training_timeout_successor_allowed": True
                        },
                    }],
                ),
                mock.patch(
                    "experiments.e18a_successor_ingest.sha256_file",
                    return_value=contract["inputs"]["predecessor_failure_sha256"],
                ),
                mock.patch(
                    "experiments.e18a_successor_ingest.base.build_manifest",
                    return_value=base_result,
                ),
            ):
                observed = build_manifest(Path(directory), contract_path, self.root)
        self.assertIs(observed, base_result)
        self.assertFalse(observed["decision"]["failed_predecessor_rehabilitated"])
        self.assertTrue(observed["decision"]["predecessor_failure_retained"])


if __name__ == "__main__":
    unittest.main()
