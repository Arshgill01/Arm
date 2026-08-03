import unittest

from experiments.e12a_resume_ingest import (
    validate_metadata_pair,
    validate_resume_command,
)


class E12aResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = {
            "prerequisite": {
                "checkpoint": {
                    "metadata": {"datasets": ["prior/corpus.txt"]},
                }
            },
            "resume": {
                "tokens_per_chunk": 512,
                "argv_after_binary": [
                    "--model", "MODEL_PATH",
                    "--file", "CORPUS_PATH",
                    "--in-file", "CHECKPOINT_PATH",
                    "--output-file", "IMATRIX_PATH",
                    "--chunk", "24",
                    "--chunks", "8",
                ],
            },
            "acceptance": {
                "required_checkpoint_chunks": 24,
                "required_final_chunks": 32,
                "required_imatrix_entries": 1,
            },
        }

    @staticmethod
    def dump(chunks: int, datasets: list[str]) -> dict:
        return {
            "metadata": {
                "general.type": {"value": "imatrix"},
                "imatrix.datasets": {"value": datasets},
                "imatrix.chunk_count": {"value": chunks},
                "imatrix.chunk_size": {"value": 512},
            },
            "tensors": {
                "blk.0.weight.in_sum2": {},
                "blk.0.weight.counts": {},
            },
        }

    def test_metadata_requires_exact_ordered_continuation(self) -> None:
        result = validate_metadata_pair(
            self.dump(24, ["prior/corpus.txt"]),
            self.dump(32, ["prior/corpus.txt", "current/corpus.txt"]),
            self.contract,
            "current/corpus.txt",
        )
        self.assertTrue(result["entry_names_match_checkpoint"])
        with self.assertRaisesRegex(ValueError, "final metadata differs"):
            validate_metadata_pair(
                self.dump(24, ["prior/corpus.txt"]),
                self.dump(31, ["prior/corpus.txt", "current/corpus.txt"]),
                self.contract,
                "current/corpus.txt",
            )

    def test_command_binds_checkpoint_and_chunk_range(self) -> None:
        command = {
            "argv": [
                "/build/bin/llama-imatrix",
                "--model", "/model.gguf",
                "--file", "/corpus.txt",
                "--in-file", "/checkpoint.gguf",
                "--output-file", "/imatrix.gguf",
                "--chunk", "24",
                "--chunks", "8",
            ]
        }
        validate_resume_command(
            command,
            self.contract,
            model_path="/model.gguf",
            corpus_path="/corpus.txt",
            checkpoint_path="/checkpoint.gguf",
            imatrix_path="/imatrix.gguf",
        )
        command["argv"][-1] = "7"
        with self.assertRaisesRegex(ValueError, "differs from the frozen"):
            validate_resume_command(
                command,
                self.contract,
                model_path="/model.gguf",
                corpus_path="/corpus.txt",
                checkpoint_path="/checkpoint.gguf",
                imatrix_path="/imatrix.gguf",
            )


if __name__ == "__main__":
    unittest.main()
