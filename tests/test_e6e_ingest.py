from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "e6e_ingest", ROOT / "experiments/e6e_ingest.py"
)
assert SPEC and SPEC.loader
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


class E6eIngestTests(unittest.TestCase):
    def test_junit_parser_counts_only_clean_passes(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ctest.xml"
            path.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="Linux-g++" tests="4" failures="1" disabled="0" skipped="1">
  <testcase name="test-reasoning-budget" classname="test-reasoning-budget" />
  <testcase name="test-quantize-fns" classname="test-quantize-fns" />
  <testcase name="broken"><failure message="failed" /></testcase>
  <testcase name="not-run"><skipped /></testcase>
</testsuite>
""",
                encoding="utf-8",
            )
            parsed = INGEST.parse_ctest_junit(path)
        self.assertEqual(parsed["total"], 4)
        self.assertEqual(parsed["passed"], 2)
        self.assertEqual(parsed["failures"], 1)
        self.assertEqual(parsed["errors"], 0)
        self.assertEqual(parsed["skipped"], 1)
        self.assertEqual(
            parsed["passed_test_names"],
            ["test-quantize-fns", "test-reasoning-budget"],
        )

    def test_acceptance_requires_full_lane_and_critical_tests(self) -> None:
        contract = INGEST.load_object(ROOT / "experiments/e6e_contract.json")
        build = {
            "configuration_bound": True,
            "compiler_bound": True,
            "configure_exit_status": 0,
            "build_exit_status": 0,
        }
        tests = {
            "exit_status": 0,
            "total": 47,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "passed_test_names": [
                "test-reasoning-budget",
                "test-quantize-fns",
                "test-quantize-perf",
            ],
        }
        self.assertTrue(all(INGEST.evaluate(build, tests, contract).values()))
        tests["passed_test_names"].remove("test-reasoning-budget")
        criteria = INGEST.evaluate(build, tests, contract)
        self.assertFalse(criteria["required_tests_passed"])
        tests["passed_test_names"].append("test-reasoning-budget")
        build["build_exit_status"] = 1
        criteria = INGEST.evaluate(build, tests, contract)
        self.assertFalse(criteria["full_build_passed"])


if __name__ == "__main__":
    unittest.main()
