import json
import sys
import tempfile
import unittest
from pathlib import Path

from experiments.e11b_artifact_recovery import (
    build_recovered_summary,
    load_e11b_artifact_json,
)


class E11bArtifactRecoveryTests(unittest.TestCase):
    def test_slots_endpoint_array_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.json"
            slots = [{"id": 0, "n_ctx": 256, "is_processing": False}]
            path.write_text(json.dumps(slots))
            self.assertEqual(load_e11b_artifact_json(path), slots)

    def test_slots_endpoint_rejects_object_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.json"
            path.write_text(json.dumps({"slots": [{"id": 0}]}))
            with self.assertRaisesRegex(ValueError, "array of slot objects"):
                load_e11b_artifact_json(path)

    def test_non_slots_json_remains_object_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probe.json"
            path.write_text(json.dumps([]))
            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_e11b_artifact_json(path)

    def test_complete_retained_matrix_replays_when_downloaded(self) -> None:
        if sys.version_info[:3] != (3, 10, 20):
            self.skipTest("complete E11b replay requires Python 3.10.20")
        evidence = Path(".scratch/e11b-30869286295")
        if not evidence.exists():
            self.skipTest("downloaded E11b artifact is unavailable")
        summary = build_recovered_summary(
            evidence, Path("experiments/e11b_contract.json"), Path(".")
        )
        self.assertEqual(summary["status"], "valid_stock_quant_service_frontier")
        self.assertEqual(len(summary["pairs"]), 5)
        self.assertEqual(
            sum(
                len(pair[role]["repetitions"])
                for pair in summary["pairs"]
                for role in ("anchor", "candidate_performance")
            ),
            40,
        )


if __name__ == "__main__":
    unittest.main()
