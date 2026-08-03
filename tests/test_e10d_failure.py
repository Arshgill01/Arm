import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from experiments.e10d_failure_ingest import (
    MISSING_PROBABILITY_ERROR,
    infer_failed_request,
    raw_inventory,
)
from experiments.e10d_failure_pair import build_pair


class E10dFailureIngestTests(unittest.TestCase):
    def test_raw_inventory_validates_and_counts_every_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = [{"tokens": [1]}, {"tokens": [2], "timings": {"cache_n": 0}}]
            for index, value in enumerate(values):
                raw = json.dumps(value, sort_keys=True).encode()
                (root / f"response-{index}.json.gz").write_bytes(gzip.compress(raw))
            result = raw_inventory(root)
            self.assertEqual(result["file_count"], 2)
            self.assertGreater(result["compressed_bytes"], 0)
            self.assertGreater(result["uncompressed_bytes"], 0)
            self.assertEqual(len(result["inventory_sha256"]), 64)

    def test_raw_inventory_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "response.json.gz"
            path.write_bytes(gzip.compress(b"not-json"))
            with self.assertRaises(json.JSONDecodeError):
                raw_inventory(path.parent)

    def test_failed_request_is_inferred_from_contiguous_raw_prefix(self) -> None:
        sample = {
            "sample_ordinal": 44,
            "requests": [
                {"choice_index": 0, "candidate_tokens": [1]},
                {"choice_index": 1, "candidate_tokens": [7, 8, 9]},
            ],
        }
        result, paths = infer_failed_request(
            raw_names={
                "held-044-c00-t000.json.gz",
                "held-044-c01-t000.json.gz",
                "held-044-c01-t001.json.gz",
            },
            task_name="held",
            sample=sample,
            completed_choices=1,
            error=MISSING_PROBABILITY_ERROR,
        )
        self.assertEqual(result["failed_choice_index"], 1)
        self.assertEqual(result["failed_token_index"], 2)
        self.assertEqual(result["failed_target_token_id"], 9)
        self.assertEqual(len(paths), 2)

    def test_failed_request_rejects_noncontiguous_partial_responses(self) -> None:
        sample = {
            "sample_ordinal": 44,
            "requests": [{"choice_index": 0, "candidate_tokens": [1, 2, 3]}],
        }
        with self.assertRaises(ValueError):
            infer_failed_request(
                raw_names={
                    "held-044-c00-t000.json.gz",
                    "held-044-c00-t002.json.gz",
                },
                task_name="held",
                sample=sample,
                completed_choices=0,
                error=MISSING_PROBABILITY_ERROR,
            )

    def test_failed_pair_requires_and_retains_both_frozen_models(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = [
                {"candidate": "primary", "role": "primary", "quantization": "Q4"},
                {"candidate": "control", "role": "control", "quantization": "Q0"},
            ]
            contract_path = root / "contract.json"
            contract_path.write_text(
                json.dumps(
                    {"schema_version": 1, "experiment_id": "E10d", "models": models}
                )
            )
            contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()

            def cell(model: dict[str, str]) -> dict[str, object]:
                return {
                    "status": "invalid_external_holdout_cell_retained",
                    "contract_sha256": contract_sha,
                    "github": {"run_id": "123", "run_attempt": 1},
                    "model": model,
                    "platform": {"architecture": "aarch64"},
                    "prepared_sha256": "a" * 64,
                    "strict_ingest_error": "ValueError: failed",
                    "preflight": {"status": "pass"},
                    "server_process": {"exit_status": 0},
                    "partial_evidence": {
                        "probe_result": {"failures": 1},
                        "errors": [
                            {
                                "task": "held",
                                "sample_ordinal": 1,
                                "source_index": 2,
                                "failed_choice_index": 0,
                                "failed_token_index": 3,
                                "failed_target_token_id": 4,
                            }
                        ],
                        "raw_inventory": {"file_count": 3},
                        "completed_choice_records": 1,
                        "completed_token_records": 2,
                        "referenced_raw_responses": 2,
                        "unreferenced_partial_raw_responses": 1,
                        "received_response_count_including_unretained_failures": 4,
                        "unattempted_frozen_token_requests": 5,
                    },
                    "decision": {
                        "negative_result_retained": True,
                        "metrics_comparable": False,
                    },
                }

            paths = [root / "primary.json", root / "control.json"]
            for path, model in zip(paths, models, strict=True):
                path.write_text(json.dumps(cell(model)))
            result = build_pair(paths[0], paths[1], contract_path, "10", "11")
            self.assertEqual(
                result["status"], "invalid_external_holdout_pair_retained"
            )
            self.assertFalse(result["validation"]["paired_aggregate_valid"])
            self.assertEqual(len(result["cells"]), 2)


if __name__ == "__main__":
    unittest.main()
