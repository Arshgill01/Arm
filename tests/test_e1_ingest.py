from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "e1_ingest.py"
SPEC = importlib.util.spec_from_file_location("e1_ingest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


class E1IngestTests(unittest.TestCase):
    def test_nearest_rank_and_summary(self) -> None:
        values = [3.0, 1.0, 2.0]
        self.assertEqual(3.0, INGEST.nearest_rank(values, 0.95))
        self.assertEqual(2.0, INGEST.summarize(values)["median"])

    def test_manifest_rejects_quality_claim_but_accepts_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            benchmark = {
                "parameters": {"num_iterations": 3},
                "iterations": [
                    {
                        "encode_tokens_per_sec": encode,
                        "decode_tokens_per_sec": decode,
                        "time_to_first_token_ms": ttft,
                        "total_time_ms": total,
                    }
                    for encode, decode, ttft, total in (
                        (100.0, 20.0, 600.0, 2000.0),
                        (110.0, 21.0, 610.0, 2010.0),
                        (120.0, 22.0, 620.0, 2020.0),
                    )
                ],
                "results": {},
            }
            provenance = {
                "experiment_id": "E1",
                "github_run_id": "1",
                "github_run_attempt": "1",
                "model_sha256": "abc123",
            }
            (evidence / "benchmark.json").write_text(json.dumps(benchmark))
            (evidence / "provenance.json").write_text(json.dumps(provenance))
            fixtures = {
                "benchmark.stderr.log": "GENERATION QUALITY WILL BE DEGRADED!\nElapsed (wall clock) time (h:mm:ss or m:ss): 0:09.07\nMaximum resident set size (kbytes): 10\nExit status: 0\n",
                "benchmark.stdout.log": "CPU_KLEIDIAI model buffer size",
                "build.log": "kleidiai\nBuilt target llm-bench-cli\nBuilt target llm-cpp-tests",
                "configure.log": "KleidiAI: ON",
                "ctest.log": "llamatextconfig_phi_2_json\n100% tests passed",
                "lscpu.txt": "Architecture: aarch64\nCPU(s): 4\nModel name: Neoverse-N2\nFlags: asimd i8mm sve2\n",
                "model.txt": "abc123 model.gguf",
                "uname.txt": "Linux test aarch64",
            }
            for name, contents in fixtures.items():
                (evidence / name).write_text(contents)

            manifest = INGEST.build_manifest(evidence)

        self.assertEqual("valid_performance_smoke_with_quality_warning", manifest["status"])
        self.assertFalse(manifest["validation"]["quality_claims_allowed"])
        self.assertFalse(manifest["validation"]["headline_comparison_allowed"])
        self.assertEqual(110.0, manifest["benchmark"]["derived_summary"]["encode_tokens_per_sec"]["median"])
        self.assertEqual("0:09.07", manifest["benchmark"]["process"]["elapsed"])


if __name__ == "__main__":
    unittest.main()
