import json
import tempfile
import unittest
from pathlib import Path

from experiments.e11a_recovery_freeze import build_contract
from experiments.e11a_recovery_ingest import validate_artifacts


class E11aRecoveryTests(unittest.TestCase):
    def test_freeze_accounts_for_every_attempt_without_raising_gate(self) -> None:
        contract = build_contract(Path("."))
        self.assertEqual(len(contract["attempted_candidates"]), 8)
        self.assertEqual(len(contract["valid_candidate_order"]), 7)
        self.assertEqual(len(contract["deployable_candidate_order"]), 8)
        self.assertFalse(contract["decision"]["raise_original_rss_gate"])
        self.assertFalse(contract["decision"]["silently_drop_q8"])
        self.assertNotIn(
            contract["resource_infeasible_candidate"],
            contract["deployable_candidate_order"],
        )

    def test_artifact_validation_binds_run_commit_and_all_candidates(self) -> None:
        contract = build_contract(Path("."))
        artifacts = []
        for index, candidate in enumerate(contract["attempted_candidates"], start=1):
            artifacts.append(
                {
                    "id": index,
                    "name": f"e11a-successor-{candidate}-30847559089-1",
                    "size_in_bytes": 1,
                    "digest": "sha256:" + f"{index:064x}",
                    "expired": False,
                    "workflow_run": {
                        "id": 30847559089,
                        "head_sha": contract["source_run"]["repository_commit"],
                    },
                }
            )
        self.assertEqual(len(validate_artifacts(contract, {"artifacts": artifacts})), 8)
        artifacts[0]["workflow_run"]["head_sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "identity"):
            validate_artifacts(contract, {"artifacts": artifacts})

    def test_freezer_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "contract.json"
            output.write_text(json.dumps(build_contract(Path("."))))
            self.assertEqual(json.loads(output.read_text())["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
