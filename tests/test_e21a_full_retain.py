import unittest
from pathlib import Path

from experiments.e21a_full_retain import retain


class E21aFullRetainTests(unittest.TestCase):
    def test_complete_native_artifact_is_bound_when_downloaded(self) -> None:
        evidence = Path(".scratch/e21a-30980957266")
        if not evidence.exists():
            self.skipTest("downloaded E21a artifact is unavailable")
        result = retain(
            evidence, Path("experiments/e21a_full_contract.json"), Path(".")
        )
        self.assertEqual(result["status"], "invalid_online_transition_certificate")
        self.assertEqual(result["artifact_recovery"]["inventory"]["file_count"], 143)
        self.assertTrue(result["artifact_recovery"]["byte_stable"])
        self.assertFalse(result["campaign_decision"]["product_promotion_made"])
        self.assertTrue(
            result["campaign_decision"]["diagnostic_performance_gates_passed"]
        )


if __name__ == "__main__":
    unittest.main()
