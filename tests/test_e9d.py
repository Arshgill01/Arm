from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "e9d_ingest", ROOT / "experiments/e9d_ingest.py"
)
assert SPEC and SPEC.loader
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


def valid_compiler_lane() -> dict[str, object]:
    return {
        "compiler_bound": True,
        "native_configuration_bound": True,
        "native_build_exit_status": 0,
        "quantize_exit_status": 0,
        "quantize_output_present": True,
        "reasoning_exit_status": 0,
        "reasoning_suite_passed": True,
        "feature_configuration_bound": True,
        "feature_build_exit_status": 0,
        "invalid_sve_source_absent": True,
    }


def valid_sanitizers() -> dict[str, object]:
    return {
        "compiler_bound": True,
        "configuration_bound": True,
        "build_exit_status": 0,
        "quantize_exit_status": 0,
        "reasoning_exit_status": 0,
        "reasoning_suite_passed": True,
        "address_sanitizer_clean": True,
        "undefined_sanitizer_clean": True,
        "leak_sanitizer_clean": True,
    }


class E9dIngestTests(unittest.TestCase):
    def test_series_commit_log_accepts_the_workflow_array_shape(self) -> None:
        contract = {
            "upstream": {"commit": "base"},
            "mail_series": {
                "patches": [
                    {"subject": "one"},
                    {"subject": "two"},
                    {"subject": "three"},
                ],
                "expected_changed_files": ["changed.cpp"],
                "aggregate_diff_sha256": "unused",
            },
        }
        commits = [
            {"commit": str(index), "subject": subject, "signed_off_by": True}
            for index, subject in enumerate(("one", "two", "three"), start=1)
        ]
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            series = evidence / "series"
            mail = evidence / "mail"
            series.mkdir()
            mail.mkdir()
            (series / "commits.json").write_text(json.dumps(commits))
            (series / "base.txt").write_text("base\n")
            (series / "patched-files.txt").write_text("changed.cpp\n")
            (series / "tip.txt").write_text("3\n")
            (series / "applied-series.patch").write_text("diff\n")
            (mail / "0000-cover-letter.patch").write_text(
                "base-commit: base\n"
            )
            contract["mail_series"]["aggregate_diff_sha256"] = (
                INGEST.sha256_file(series / "applied-series.patch")
            )
            observed = INGEST.validate_series(evidence, contract)

        self.assertEqual(
            [entry["subject"] for entry in observed["commits"]],
            ["one", "two", "three"],
        )

    def test_acceptance_requires_both_compilers_and_sanitizers(self) -> None:
        series = {
            "git_am_three_way_passed": True,
            "cover_letter_complete": True,
            "aggregate_diff_sha256": "a" * 64,
        }
        compilers = {
            "gcc": valid_compiler_lane(),
            "clang": valid_compiler_lane(),
        }
        sanitizers = valid_sanitizers()
        self.assertTrue(all(INGEST.evaluate(series, compilers, sanitizers).values()))

        compilers["clang"]["reasoning_exit_status"] = 1
        criteria = INGEST.evaluate(series, compilers, sanitizers)
        self.assertFalse(criteria["clang_reasoning_passed"])
        compilers["clang"]["reasoning_exit_status"] = 0
        sanitizers["undefined_sanitizer_clean"] = False
        criteria = INGEST.evaluate(series, compilers, sanitizers)
        self.assertFalse(criteria["undefined_sanitizer_clean"])

    def test_contract_rejects_published_or_incomplete_series(self) -> None:
        contract = {
            "schema_version": 1,
            "contract_revision": 2,
            "experiment_id": "E9d",
            "mail_series": {"patches": [{}, {}, {}]},
            "acceptance": {"all_required": True},
            "claim_boundary": {"upstream_pr_opened": False},
        }
        INGEST.validate_contract(contract)
        contract["claim_boundary"]["upstream_pr_opened"] = True
        with self.assertRaisesRegex(ValueError, "invalid E9d contract"):
            INGEST.validate_contract(contract)


if __name__ == "__main__":
    unittest.main()
