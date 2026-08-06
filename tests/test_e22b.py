from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.e22a_freeze import sha256_file
from experiments.e22b_freeze import build_contract
from experiments.e22b_ingest import validate_nonvalid_cell
from experiments.e22b_probe import PERF_EVENTS, parse_perf


class E22bFixedMemoryTests(unittest.TestCase):
    @property
    def root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_frozen_contract_matches_stable_host_generator(self) -> None:
        contract_path = self.root / "experiments/e22b_contract.json"
        frozen = json.loads(contract_path.read_text())
        recomputed = build_contract(
            self.root,
            self.root / "results/hosts/e22b-axion-20260806",
            self.root / "results/hosts/e22b-axion-20260806/cloud-instance.json",
        )
        self.assertEqual(frozen, recomputed)
        self.assertEqual(
            "d87b746aca548af9d5fcf605dc93f85f4a4ecd28e72974f66cd1156c6463b808",
            sha256_file(contract_path),
        )

    def test_physical_cap_pmu_and_cost_ceiling_are_frozen(self) -> None:
        contract = json.loads(
            (self.root / "experiments/e22b_contract.json").read_text()
        )
        self.assertEqual(16_723_460_096, contract["fixed_memory"]["cap_bytes"])
        self.assertEqual(0, contract["fixed_memory"]["swap_total_bytes"])
        self.assertEqual(8, contract["host"]["logical_cpus"])
        self.assertTrue(contract["host"]["pmu"]["perf_stat_available"])
        self.assertLess(
            contract["cost_control"]["estimated_maximum_compute_usd"],
            contract["cost_control"]["authorized_maximum_usd"],
        )
        self.assertEqual(
            "DELETE", contract["cost_control"]["instance_termination_action"]
        )

    def test_matrix_measures_common_curve_and_conditional_boundary(self) -> None:
        contract = build_contract(
            self.root,
            self.root / "results/hosts/e22b-axion-20260806",
            self.root / "results/hosts/e22b-axion-20260806/cloud-instance.json",
        )
        order = contract["matrix"]["order"]
        self.assertEqual(list(range(1, 13)), [cell["position"] for cell in order])
        self.assertEqual(
            {
                (mode, count)
                for mode in ("normal", "shared")
                for count in (1, 2, 4, 5, 6)
            },
            {(cell["mode"], cell["workers"]) for cell in order if cell["workers"] != 8},
        )
        self.assertIn(
            ("shared", 8), {(cell["mode"], cell["workers"]) for cell in order}
        )
        self.assertTrue(contract["matrix"]["clean_final_rerun_required_if_promoted"])

    def test_pmu_parser_requires_every_frozen_counted_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "perf.csv"
            raw.write_text(
                "\n".join(f"100,,{event},100,100.00,," for event in PERF_EVENTS) + "\n"
            )
            self.assertEqual(set(PERF_EVENTS), set(parse_perf(raw)))
            raw.write_text("<not counted>,,cpu_cycles,0,0.00,,\n")
            with self.assertRaisesRegex(ValueError, "not counted"):
                parse_perf(raw)

    def test_only_resource_evidence_can_bound_a_failed_cell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cell_dir = Path(directory)
            (cell_dir / "cell-status.json").write_text(
                json.dumps(
                    {
                        "status": "failed_fixed_memory_admission_cell",
                        "mode": "normal",
                        "workers": 6,
                        "position": 9,
                        "exit_status": 1,
                        "deployment_status": "failed_pareto64_deployment_lifecycle",
                    }
                )
            )
            (cell_dir / "kernel-since-start.txt").write_text(
                "oom-kill: Killed process llama-server\n"
            )
            result = validate_nonvalid_cell(
                cell_dir, {"mode": "normal", "workers": 6, "position": 9}
            )
            self.assertTrue(result["resource_boundary_evidence"])

    def test_campaign_retains_normal_eight_stop_instead_of_posthoc_search(self) -> None:
        campaign = (self.root / "experiments/e22b_campaign.sh").read_text()
        self.assertIn("skipped_by_frozen_normal_six_stop_rule", campaign)
        self.assertIn("minimum_mem_available_bytes", campaign)
        self.assertIn("oom_kills", campaign)


if __name__ == "__main__":
    unittest.main()
