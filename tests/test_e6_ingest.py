from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "e6_ingest.py"
SPEC = importlib.util.spec_from_file_location("e6_ingest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


class E6IngestTests(unittest.TestCase):
    def test_failure_signature_requires_validated_disable_and_bad_source(self) -> None:
        INGEST.validate_failure_signature(
            "Performing Test HAVE_SVE - Failed -mcpu=n2+sve2-sm4+nosve",
            "path/sve_dotprod_asm.S: selected processor does not support `ptrue'",
        )
        with self.assertRaisesRegex(ValueError, "nosve"):
            INGEST.validate_failure_signature(
                "Performing Test HAVE_SVE - Failed -mcpu=n2+sve2-sm4",
                "sve_dotprod_asm.S: selected processor does not support",
            )

    def test_benchmark_requires_full_output_and_contract_parameters(self) -> None:
        expected = {
            "input_tokens": 64,
            "output_tokens": 32,
            "context": 512,
            "threads": 4,
            "warmup_iterations": 1,
            "measured_iterations": 1,
        }
        benchmark = {
            "parameters": {
                "num_input_tokens": 64,
                "num_output_tokens": 32,
                "context_size": 512,
                "num_threads": 4,
                "num_warmup": 1,
                "num_iterations": 1,
            },
            "iterations": [
                {
                    "tokens_generated": 32,
                    "encode_tokens_per_sec": 100.0,
                    "decode_tokens_per_sec": 20.0,
                    "time_to_first_token_ms": 600.0,
                    "total_time_ms": 2000.0,
                }
            ],
        }
        summary = INGEST.validate_benchmark(benchmark, expected)
        self.assertEqual(20.0, summary["metrics"]["decode_tokens_per_sec"]["median"])
        benchmark["iterations"][0]["tokens_generated"] = 31
        with self.assertRaisesRegex(ValueError, "every contracted output token"):
            INGEST.validate_benchmark(benchmark, expected)


if __name__ == "__main__":
    unittest.main()
