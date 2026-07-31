from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "e2_ingest.py"
SPEC = importlib.util.spec_from_file_location("e2_ingest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


class E2IngestTests(unittest.TestCase):
    def test_elapsed_seconds_supports_time_output_formats(self) -> None:
        self.assertEqual(69.25, INGEST.elapsed_seconds("1:09.25"))
        self.assertEqual(3723.5, INGEST.elapsed_seconds("1:02:03.5"))

    def test_paired_effect_applies_metric_direction(self) -> None:
        generic = {round_number: [100.0] for round_number in range(1, 5)}
        faster = {round_number: [120.0] for round_number in range(1, 5)}
        lower = {round_number: [80.0] for round_number in range(1, 5)}
        self.assertAlmostEqual(
            1.2,
            INGEST.paired_effect(generic, faster, "higher")[
                "median_improvement_ratio"
            ],
        )
        self.assertAlmostEqual(
            1.25,
            INGEST.paired_effect(generic, lower, "lower")[
                "median_improvement_ratio"
            ],
        )

    def test_manifest_accepts_predeclared_primary_win(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            provenance = {
                "experiment_id": "E2",
                "github_run_id": "2",
                "github_run_attempt": "1",
                "model_sha256": "model-sha",
                "controlled_difference": "USE_KLEIDIAI only",
                "benchmark": {
                    "execution_order": [
                        ["generic", "kleidiai"],
                        ["kleidiai", "generic"],
                        ["generic", "kleidiai"],
                        ["kleidiai", "generic"],
                    ]
                },
            }
            (evidence / "provenance.json").write_text(json.dumps(provenance))
            (evidence / "lscpu.txt").write_text(
                "Architecture: aarch64\nCPU(s): 4\nModel name: Neoverse-N2\n"
            )
            (evidence / "uname.txt").write_text("Linux test aarch64\n")
            (evidence / "model.txt").write_text("model-sha model.gguf\n")
            for variant in INGEST.VARIANTS:
                variant_dir = evidence / variant
                variant_dir.mkdir()
                enabled = variant == "kleidiai"
                (variant_dir / "configure.log").write_text(
                    f"KleidiAI: {'ON' if enabled else 'OFF'}\n"
                )
                (variant_dir / "build.log").write_text(
                    "Built target llm-bench-cli\nBuilt target llm-cpp-tests\n"
                )
                (variant_dir / "ctest.log").write_text(
                    "llamatextconfig_phi_2_json\n100% tests passed\n"
                )
                for round_number in range(1, 5):
                    generic_first = round_number % 2 == 1
                    position = 1 if (enabled != generic_first) else 2
                    run_dir = variant_dir / f"round-{round_number}-position-{position}"
                    run_dir.mkdir()
                    encode = 120.0 if enabled else 100.0
                    benchmark = {
                        "parameters": {"num_iterations": 3, "threads": 4},
                        "iterations": [
                            {
                                "encode_tokens_per_sec": encode,
                                "decode_tokens_per_sec": 22.0,
                                "time_to_first_token_ms": 600.0,
                                "total_time_ms": 2000.0,
                            }
                            for _ in range(3)
                        ],
                        "results": {},
                    }
                    (run_dir / "benchmark.json").write_text(json.dumps(benchmark))
                    (run_dir / "stdout.log").write_text(
                        "CPU_KLEIDIAI model buffer size" if enabled else "CPU model buffer"
                    )
                    (run_dir / "stderr.log").write_text(
                        "GENERATION QUALITY WILL BE DEGRADED"
                    )
                    (run_dir / "time.log").write_text(
                        "Elapsed (wall clock) time (h:mm:ss or m:ss): 0:09.00\n"
                        "Maximum resident set size (kbytes): 100\nExit status: 0\n"
                    )

            manifest = INGEST.build_manifest(evidence)

        self.assertEqual("valid_primary_win", manifest["status"])
        self.assertTrue(manifest["validation"]["primary_threshold_met"])
        self.assertAlmostEqual(
            1.2,
            manifest["benchmark"]["paired_comparison"]["encode_tokens_per_sec"][
                "median_improvement_ratio"
            ],
        )


if __name__ == "__main__":
    unittest.main()
