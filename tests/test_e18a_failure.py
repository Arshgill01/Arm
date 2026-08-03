import unittest
from pathlib import Path

from experiments.e18a_failure_retain import retain


class E18aFailureTests(unittest.TestCase):
    def test_relative_patch_failure_precedes_measurement(self) -> None:
        evidence = Path(".scratch/e18a-30858644241")
        if not evidence.exists():
            self.skipTest("downloaded E18a failure artifact is not present")
        result = retain(evidence, Path("."))
        self.assertEqual(result["failure"]["builds_started"], 0)
        self.assertEqual(result["failure"]["measured_requests_completed"], 0)
        self.assertFalse(result["decision"]["pgo_result_accepted"])
        self.assertTrue(
            result["decision"]["exact_contract_retry_after_path_repair_allowed"]
        )


if __name__ == "__main__":
    unittest.main()
