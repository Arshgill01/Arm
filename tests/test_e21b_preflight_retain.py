import json
import unittest
from pathlib import Path

from experiments.e21b_preflight_retain import (
    ARTIFACT_DIGEST,
    ARTIFACT_NAME,
    HEAD_SHA,
    RUN_ID,
    retain,
)


class E21bPreflightRetentionTests(unittest.TestCase):
    def test_native_artifact_replays_when_available(self) -> None:
        evidence = Path(f".scratch/e21b-preflight-{RUN_ID}")
        if not evidence.is_dir():
            self.skipTest("downloaded native E21b preflight artifact is unavailable")
        result = retain(
            evidence,
            Path("experiments/e21b_preflight_contract.json"),
            Path("."),
        )
        self.assertEqual(result["status"], "valid_openai_online_certificate_preflight")
        self.assertEqual(result["github"]["repository_commit"], HEAD_SHA)
        self.assertEqual(result["github"]["artifact_name"], ARTIFACT_NAME)
        self.assertEqual(result["github"]["artifact_digest"], ARTIFACT_DIGEST)
        self.assertTrue(result["preflight_decision"]["full_experiment_authorized"])
        self.assertFalse(
            result["preflight_decision"]["native_performance_claim_allowed"]
        )
        self.assertGreater(
            result["preflight_decision"]["diagnostic_p95_latency_ratio"], 1.0
        )
        self.assertTrue(
            result["retention_validation"]["independent_replay_byte_identical"]
        )
        retained = Path(f"results/manifests/e21b-preflight-{RUN_ID}.json")
        if retained.is_file():
            self.assertEqual(json.loads(retained.read_text()), result)


if __name__ == "__main__":
    unittest.main()
