import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class E10cNegativeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (ROOT / "results/manifests/e10c-30812791972.json").read_text()
        )

    def test_failed_parity_gates_are_not_promoted(self) -> None:
        self.assertEqual(self.manifest["status"], "failed_frozen_parity_gates")
        self.assertFalse(self.manifest["promote_candidate_scorer"])
        validation = self.manifest["validation"]
        self.assertFalse(validation["single_token_parity_gate"])
        self.assertFalse(validation["multi_token_sum_parity_gate"])
        self.assertFalse(validation["multi_token_token_parity_gate"])
        self.assertFalse(validation["candidate_scorer_promotion_allowed"])

    def test_efficiency_and_prediction_results_remain_visible(self) -> None:
        aggregate = self.manifest["aggregate"]
        self.assertTrue(aggregate["predictions_identical"])
        self.assertEqual(aggregate["accuracy"]["serial"], 0.7)
        self.assertEqual(aggregate["accuracy"]["forked"], 0.7)
        self.assertLess(
            aggregate["forked_to_serial_ratios"]["median_http_latency"], 0.7
        )
        self.assertLess(
            aggregate["forked_to_serial_ratios"]["median_cpu_seconds_per_task"],
            0.7,
        )

    def test_contract_and_negative_ingester_are_content_addressed(self) -> None:
        provenance = self.manifest["provenance"]
        self.assertEqual(
            provenance["contract_sha256"],
            sha256(ROOT / "experiments/e10c_contract.json"),
        )
        self.assertEqual(
            provenance["negative_ingest_sha256"],
            sha256(ROOT / provenance["negative_ingest_path"]),
        )


if __name__ == "__main__":
    unittest.main()
