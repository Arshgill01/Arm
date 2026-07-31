from __future__ import annotations

import json
from pathlib import Path
import unittest

from pareto64.planner import build_plan, finite_metric, pareto_front


ROOT = Path(__file__).resolve().parents[1]


def candidate(accuracy: float, latency: float, rss: float, size: float, load: float) -> dict:
    return {
        "minimum_accuracy": accuracy,
        "quality_eligible": True,
        "package_size_bytes": size,
        "model_load_ms": {"median": load},
        "same_text_total_ms": {"median": latency},
        "quality_process": {"maximum_rss_kib": {"max": rss}},
    }


def manifest() -> dict:
    application = {
        "fast": candidate(0.80, 400.0, 1200.0, 900.0, 300.0),
        "small": candidate(0.80, 500.0, 1000.0, 700.0, 250.0),
        "dominated": candidate(0.78, 600.0, 1300.0, 1000.0, 350.0),
    }
    quality = {
        name: {"framework": "test", "quality_eligible": True}
        for name in application
    }
    return {
        "schema_version": 1,
        "experiment_id": "E3",
        "status": "valid_frontier",
        "source": {"github_run_url": "https://example.invalid/run"},
        "validation": {
            "quality_policy_predeclared": True,
            "performance_comparison_allowed": True,
            "quality_eligible_variants": sorted(application),
        },
        "application": application,
        "quality": {"variants": quality},
    }


def constraints() -> dict:
    return {
        "schema_version": 1,
        "requirements": {"minimum_accuracy": {"at_least": 0.75}},
        "selection_priority": ["same_text_total_ms_median", "package_size_bytes"],
    }


class Pareto64PlannerTests(unittest.TestCase):
    def test_frontier_and_explicit_priority_select_fast(self) -> None:
        result = build_plan(manifest(), constraints())
        self.assertEqual("selected", result["status"])
        self.assertEqual("fast", result["selected"]["name"])
        self.assertEqual(
            ["fast", "small"],
            [item["name"] for item in result["pareto_frontier"]],
        )
        self.assertFalse(result["policy"]["weighted_score_used"])

    def test_quality_gate_fails_closed(self) -> None:
        data = manifest()
        data["application"]["fast"]["quality_eligible"] = False
        data["quality"]["variants"]["fast"]["quality_eligible"] = False
        data["validation"]["quality_eligible_variants"].remove("fast")
        result = build_plan(data, constraints())
        self.assertNotIn("fast", result["feasible_candidates"])
        self.assertEqual("quality_gate", result["evaluated"]["fast"]["rejections"][0]["kind"])

    def test_real_e3_manifest_returns_no_candidate(self) -> None:
        data = json.loads(
            (ROOT / "results/manifests/e3-30635472160.json").read_text()
        )
        policy = json.loads((ROOT / "configs/cloud-balanced.json").read_text())
        result = build_plan(data, policy)
        self.assertEqual("no_feasible_candidate", result["status"])
        self.assertEqual([], result["pareto_frontier"])
        self.assertTrue(
            all(item["rejections"][0]["detail"] == "quality_ineligible" for item in result["evaluated"].values())
        )

    def test_conflicting_quality_evidence_is_rejected(self) -> None:
        data = manifest()
        data["quality"]["variants"]["fast"]["quality_eligible"] = False
        with self.assertRaisesRegex(ValueError, "conflicting quality decisions"):
            build_plan(data, constraints())

    def test_nonfinite_metrics_and_unknown_directions_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            finite_metric(float("nan"), "latency")
        with self.assertRaisesRegex(ValueError, "unknown direction"):
            pareto_front(
                {"one": {"metric": 1.0}, "two": {"metric": 2.0}},
                {"metric": "sideways"},
            )


if __name__ == "__main__":
    unittest.main()
