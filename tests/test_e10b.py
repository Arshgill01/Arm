import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e10b_ingest import validate_raw_response
from experiments.e10b_probe import extract_scores

ROOT = Path(__file__).resolve().parents[1]


class E10bProbeTests(unittest.TestCase):
    def test_selected_scores_preserve_requested_order(self) -> None:
        response = {
            "completion_probabilities": [
                {
                    "selected_logprobs": [
                        {"id": 7, "logprob": -2.5},
                        {"id": 3, "logprob": -1.0},
                    ]
                }
            ]
        }
        scores, count, order = extract_scores(response, "selected", [7, 3], 10)
        self.assertEqual(scores, {"7": -2.5, "3": -1.0})
        self.assertEqual(count, 2)
        self.assertEqual(order, [7, 3])

    def test_full_vocab_requires_every_entry(self) -> None:
        response = {
            "completion_probabilities": [
                {
                    "top_logprobs": [
                        {"id": 2, "logprob": -0.1},
                        {"id": 0, "logprob": -1.0},
                        {"id": 1, "logprob": -2.0},
                    ]
                }
            ]
        }
        scores, count, order = extract_scores(response, "full_vocab", [0, 2], 3)
        self.assertEqual(scores, {"0": -1.0, "2": -0.1})
        self.assertEqual(count, 3)
        self.assertEqual(order, [2, 0, 1])


class E10bIngestTests(unittest.TestCase):
    def test_raw_response_integrity_round_trip(self) -> None:
        raw = b'{"completion_probabilities":[]}'
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        with tempfile.TemporaryDirectory() as directory:
            cell = Path(directory)
            (cell / "raw").mkdir()
            (cell / "raw" / "response.json.gz").write_bytes(compressed)
            validate_raw_response(
                cell,
                {
                    "path": "response.json.gz",
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "gzip_bytes": len(compressed),
                    "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
                },
            )

    def test_contract_freezes_bounded_negative_policy(self) -> None:
        contract = json.loads((ROOT / "experiments/e10b_contract.json").read_text())
        self.assertEqual(contract["experiment_id"], "E10b")
        self.assertFalse(contract["decision"]["weighted_score_used"])
        self.assertEqual(contract["execution"]["total_fresh_process_cells"], 4)
        self.assertFalse(contract["workload"]["cache_prompt"])
        self.assertFalse(contract["primitive"]["sampling_semantics_changed"])


if __name__ == "__main__":
    unittest.main()
