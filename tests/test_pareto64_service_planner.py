from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from pareto64.service_planner import build_service_plan


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "results/manifests/e5h-30672633366.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Pareto64ServicePlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load(MANIFEST_PATH)
        cls.throughput_policy_path = ROOT / "configs/service-throughput.json"
        cls.memory_policy_path = ROOT / "configs/service-memory.json"

    def test_throughput_policy_selects_repacked_profile(self) -> None:
        result = build_service_plan(
            self.manifest,
            load(self.throughput_policy_path),
            manifest_path=MANIFEST_PATH,
            constraints_path=self.throughput_policy_path,
        )
        self.assertEqual("selected", result["status"])
        self.assertEqual(["repack_on"], result["feasible_profiles"])
        self.assertEqual("repack_on", result["selected"]["name"])
        self.assertTrue(result["selected"]["runtime"]["weight_repack"])
        self.assertEqual([], result["selected"]["runtime"]["launch_arguments"])
        self.assertFalse(result["policy"]["weighted_score_used"])
        self.assertIsNotNone(result["inputs"]["manifest_sha256"])

    def test_memory_policy_selects_no_repack_profile(self) -> None:
        result = build_service_plan(
            self.manifest,
            load(self.memory_policy_path),
            manifest_path=MANIFEST_PATH,
            constraints_path=self.memory_policy_path,
        )
        self.assertEqual("selected", result["status"])
        self.assertEqual(["repack_off"], result["feasible_profiles"])
        self.assertEqual("repack_off", result["selected"]["name"])
        self.assertFalse(result["selected"]["runtime"]["weight_repack"])
        self.assertEqual(
            ["--no-weight-repack"],
            result["selected"]["runtime"]["launch_arguments"],
        )
        self.assertEqual([], result["evaluated"]["repack_off"]["rejections"])

    def test_broad_policy_preserves_both_pareto_profiles(self) -> None:
        policy = {
            "schema_version": 1,
            "requirements": {
                "requests_per_second_median": {"at_least": 0.4},
                "maximum_rss_kib": {"at_most": 8_388_608},
            },
            "selection_priority": [
                "requests_per_second_median",
                "maximum_rss_kib",
            ],
        }
        result = build_service_plan(self.manifest, policy)
        self.assertEqual(["repack_off", "repack_on"], result["feasible_profiles"])
        self.assertEqual(
            ["repack_off", "repack_on"],
            [profile["name"] for profile in result["pareto_frontier"]],
        )
        self.assertEqual("repack_on", result["selected"]["name"])

    def test_impossible_memory_policy_refuses_deployment(self) -> None:
        policy = copy.deepcopy(load(self.memory_policy_path))
        policy["requirements"]["maximum_rss_kib"]["at_most"] = 2_097_152
        result = build_service_plan(self.manifest, policy)
        self.assertEqual("no_feasible_profile", result["status"])
        self.assertIsNone(result["selected"])
        self.assertEqual([], result["pareto_frontier"])
        self.assertTrue(
            all(profile["rejections"] for profile in result["evaluated"].values())
        )

    def test_policy_and_mechanism_tampering_fail_closed(self) -> None:
        policy = copy.deepcopy(load(self.throughput_policy_path))
        policy["requirements"]["requests_per_second_median"] = {"at_most": 1.0}
        with self.assertRaisesRegex(ValueError, "must contain only at_least"):
            build_service_plan(self.manifest, policy)

        manifest = copy.deepcopy(self.manifest)
        manifest["performance"]["repack_off"]["mechanism"][
            "repack_buffer_mib"
        ] = 1.0
        with self.assertRaisesRegex(ValueError, "mechanism is inconsistent"):
            build_service_plan(manifest, load(self.memory_policy_path))


if __name__ == "__main__":
    unittest.main()
