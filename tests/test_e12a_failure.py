import unittest

from experiments.e12a_failure_retain import (
    parse_generation_log,
    validate_partial_metadata,
)


class E12aFailureRetentionTests(unittest.TestCase):
    def test_generation_eta_is_parsed(self) -> None:
        result = parse_generation_log(
            "computing over 32 chunks, n_ctx=512, batch_size=512, n_seq=1\n"
            "569.39 seconds per pass - ETA 5 hours 3.67 minutes\n"
        )
        self.assertEqual(result["declared_chunks"], 32)
        self.assertAlmostEqual(result["estimated_generation_seconds"], 18220.2)

    def test_partial_checkpoint_must_be_periodic_and_incomplete(self) -> None:
        plan = {
            "imatrix": {"processed_chunks": 32, "tokens_per_chunk": 512},
        }
        dump = {
            "metadata": {
                "general.type": {"value": "imatrix"},
                "imatrix.datasets": {"value": ["corpus.txt"]},
                "imatrix.chunk_count": {"value": 24},
                "imatrix.chunk_size": {"value": 512},
            },
            "tensors": {
                "blk.0.weight.in_sum2": {},
                "blk.0.weight.counts": {},
            },
        }
        result = validate_partial_metadata(dump, plan, "corpus.txt")
        self.assertEqual(result["chunk_count"], 24)
        dump["metadata"]["imatrix.chunk_count"]["value"] = 32
        with self.assertRaisesRegex(ValueError, "checkpoint differs"):
            validate_partial_metadata(dump, plan, "corpus.txt")


if __name__ == "__main__":
    unittest.main()
