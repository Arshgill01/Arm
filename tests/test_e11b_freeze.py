import json
import tempfile
import unittest
from pathlib import Path

from experiments.e11b_freeze import build_contract
from experiments.e11b_ingest import dominates, probe_contract
from experiments.e5b_ingest import sha256_file


class E11bFreezeTests(unittest.TestCase):
    def test_probe_contract_binds_each_measured_model(self) -> None:
        contract = {
            "request": {"measured_tasks": 30},
            "sentinel": True,
        }
        adapted = probe_contract(contract, "candidate")
        self.assertEqual(adapted["selected"]["candidate"], "candidate")
        self.assertEqual(adapted["selected"]["reference_total"], 30)
        self.assertTrue(adapted["sentinel"])

    def test_frontier_dominance_requires_no_regression(self) -> None:
        point = {
            "quality_coordinates": {"a": 1.0, "b": 2.0},
            "throughput": 3.0,
            "model_size_bytes": 4.0,
            "median_http_ms": 5.0,
            "p95_http_ms": 6.0,
            "cpu_seconds_per_request": 7.0,
            "maximum_rss_kib": 8.0,
            "readiness_ms": 9.0,
        }
        better = {**point, "throughput": 3.1}
        tradeoff = {**point, "throughput": 3.1, "model_size_bytes": 4.1}
        self.assertTrue(dominates(better, point))
        self.assertFalse(dominates(tradeoff, point))

    def test_terminal_frontier_is_the_only_candidate_source(self) -> None:
        root = Path(".").resolve()
        stock = json.loads(
            (root / "experiments/e11a_successor_contract.json").read_text()
        )
        anchor = json.loads(
            (root / "results/manifests/e10f-30829237582.json").read_text()
        )["models"][0]
        resources = {"ministral3_3b_q6_k", "ministral3_3b_q8_0"}
        deployable = []
        for model in stock["models"]:
            if model["candidate"] in resources:
                continue
            deployable.append(
                {
                    "model": model,
                    "quality_coordinates": {
                        "e9b_arc_easy.acc_norm": 0.5,
                        "e9b_hellaswag.acc_norm": 0.5,
                        "e9b_winogrande.acc": 0.5,
                    },
                }
            )
        deployable.insert(
            stock["full_candidate_order"].index("ministral3_3b_q4_k_m"),
            {
                "model": anchor["model"],
                "quality_coordinates": {
                    "e9b_arc_easy.acc_norm": 0.59,
                    "e9b_hellaswag.acc_norm": 0.72,
                    "e9b_winogrande.acc": 0.57,
                },
            },
        )
        with tempfile.TemporaryDirectory(dir=root) as directory:
            scratch = Path(directory)
            recovery_path = scratch / "contract.json"
            recovery = {
                "experiment_id": "E11a-successor-actual-recovery",
                "prepared_sha256": anchor["prepared_sha256"],
                "resource_infeasible_candidate_order": sorted(resources),
            }
            recovery_path.write_text(json.dumps(recovery))
            summary_path = scratch / "summary.json"
            summary = {
                "status": "valid_stock_quant_ladder_with_two_resource_infeasible_points",
                "contract_sha256": sha256_file(recovery_path),
                "prepared_sha256": anchor["prepared_sha256"],
                "deployable_models": deployable,
                "deployable_quality_size_frontier": [
                    "ministral3_3b_iq4_xs",
                    "ministral3_3b_q4_k_m",
                ],
                "accounting": {
                    "new_candidates_attempted": 8,
                    "valid_deployable_cells": 6,
                    "resource_infeasible_cells_with_valid_scoring": 2,
                    "all_attempted_candidates_accounted_for": True,
                },
                "validation": {
                    name: True
                    for name in (
                        "native_arm64",
                        "same_frozen_workload",
                        "all_valid_source_cells_complete",
                        "two_complete_scoring_resource_failures_retained",
                        "resource_failures_excluded_from_deployable_frontier",
                        "exact_e10f_anchor_reused_without_rerun",
                        "zero_scoring_request_failures",
                        "per_sample_logs_retained_in_source_artifacts",
                    )
                },
            }
            summary_path.write_text(json.dumps(summary))
            contract = build_contract(
                root,
                e11a_contract_path=recovery_path,
                e11a_summary_path=summary_path,
                e11a_run_id="123",
                e11a_artifact="fixture",
            )
        self.assertEqual(contract["candidate_order"], ["ministral3_3b_iq4_xs"])
        self.assertEqual(contract["execution"]["total_fresh_processes"], 8)
        self.assertEqual(
            set(contract["models"]),
            {"ministral3_3b_q4_k_m", "ministral3_3b_iq4_xs"},
        )


if __name__ == "__main__":
    unittest.main()
