import unittest

from experiments.e12a_ingest import validate_command, validate_metadata


class E12aValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = {
            "imatrix": {
                "processed_chunks": 32,
                "tokens_per_chunk": 512,
                "argv_after_binary": [
                    "--model",
                    "MODEL_PATH",
                    "--file",
                    "CORPUS_PATH",
                    "--output-file",
                    "IMATRIX_PATH",
                    "--chunks",
                    "32",
                ],
            },
            "acceptance": {"minimum_imatrix_entries": 1},
        }

    def test_metadata_requires_paired_activation_tensors(self) -> None:
        dump = {
            "metadata": {
                "general.type": {"value": "imatrix"},
                "imatrix.datasets": {"value": ["corpus.txt"]},
                "imatrix.chunk_count": {"value": 32},
                "imatrix.chunk_size": {"value": 512},
            },
            "tensors": {
                "blk.0.attn_q.weight.in_sum2": {},
                "blk.0.attn_q.weight.counts": {},
            },
        }
        result = validate_metadata(dump, self.plan, "corpus.txt")
        self.assertEqual(result["entries"], 1)
        dump["tensors"].pop("blk.0.attn_q.weight.counts")
        with self.assertRaisesRegex(ValueError, "entry pairs"):
            validate_metadata(dump, self.plan, "corpus.txt")

    def test_command_substitutes_only_frozen_paths(self) -> None:
        command = {
            "argv": [
                "/build/bin/llama-imatrix",
                "--model",
                "/model.gguf",
                "--file",
                "/corpus.txt",
                "--output-file",
                "/imatrix.gguf",
                "--chunks",
                "32",
            ]
        }
        result = validate_command(
            command,
            self.plan,
            model_path="/model.gguf",
            corpus_path="/corpus.txt",
            imatrix_path="/imatrix.gguf",
        )
        self.assertEqual(result, command["argv"])
        command["argv"][-1] = "31"
        with self.assertRaisesRegex(ValueError, "command differs"):
            validate_command(
                command,
                self.plan,
                model_path="/model.gguf",
                corpus_path="/corpus.txt",
                imatrix_path="/imatrix.gguf",
            )


if __name__ == "__main__":
    unittest.main()
