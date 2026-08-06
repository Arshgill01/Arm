from __future__ import annotations

import json
import unittest
from pathlib import Path

from experiments.e22a_freeze import build_contract
from experiments.e22a_ingest import evaluate_pairs


class E22aPreflightTests(unittest.TestCase):
    @property
    def root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_frozen_contract_matches_generator(self) -> None:
        frozen = json.loads((self.root / "experiments/e22a_contract.json").read_text())
        self.assertEqual(frozen, build_contract(self.root))

    def test_matrix_pairs_every_mode_at_1_2_4_workers(self) -> None:
        contract = build_contract(self.root)
        cells = contract["matrix"]["order"]
        self.assertEqual([1, 2, 4], contract["matrix"]["worker_counts"])
        self.assertEqual(
            {(mode, workers) for mode in ("normal", "shared") for workers in (1, 2, 4)},
            {(cell["mode"], cell["workers"]) for cell in cells},
        )
        self.assertEqual(list(range(1, 7)), [cell["position"] for cell in cells])

    def test_preflight_cannot_become_a_final_claim(self) -> None:
        contract = build_contract(self.root)
        boundary = contract["scientific_boundary"]
        self.assertTrue(boundary["preflight_only"])
        self.assertFalse(boundary["final_performance_claim_permitted"])
        self.assertFalse(boundary["host_is_stable_performance_authority"])
        self.assertFalse(boundary["fixed_memory_cap_frozen_after_preflight"])
        self.assertFalse(contract["advance"]["post_result_gate_change_permitted"])

    def test_workflow_runs_product_modes_on_native_arm_and_always_retains(self) -> None:
        workflow = (
            self.root / ".github/workflows/sidecar-scaling-preflight.yml"
        ).read_text()
        self.assertIn("runs-on: ubuntu-24.04-arm", workflow)
        self.assertIn("experiments/e22a_cell.sh", workflow)
        self.assertIn("python3 -m pareto64 sidecar-prepack", workflow)
        self.assertIn(
            "if: always()\n        uses: actions/upload-artifact@v7", workflow
        )
        self.assertIn(
            "CONTRACT_SHA256: "
            "23b4cd7d49eb09ae685713bf19b08676cdf75fc600701fb3c35c7313733c4c86",
            workflow,
        )

    def test_pair_evaluation_uses_predeclared_quality_speed_latency_and_pss_gates(
        self,
    ) -> None:
        contract = build_contract(self.root)
        cells = []
        responses = {"task": "A"}
        for workers in (1, 2, 4):
            for mode in ("normal", "shared"):
                normal_pss = workers * 3_500_000
                shared_pss = normal_pss - (0 if workers == 1 else workers * 600_000)
                pss = normal_pss if mode == "normal" else shared_pss
                cells.append(
                    {
                        "mode": mode,
                        "worker_count": workers,
                        "request_failures": 0,
                        "reference_prediction_mismatches": 0,
                        "responses_stable_across_workers": True,
                        "response_map": responses,
                        "requests_per_second": 1.0 if mode == "normal" else 0.98,
                        "p95_http_ms": 100.0 if mode == "normal" else 102.0,
                        "summed_pss_kib": pss,
                        "throughput_per_gib_pss": (1.0 if mode == "normal" else 0.98)
                        / pss,
                        "all_workers_ready_seconds": 10.0,
                        "shared_mapping_count": workers if mode == "shared" else 0,
                        "gateway_route": "unknown_shadow_then_oracle",
                        "gateway_served_source": "uncached_oracle",
                    }
                )
        pairs, gates = evaluate_pairs(cells, contract["advance"])
        self.assertEqual([1, 2, 4], [pair["worker_count"] for pair in pairs])
        self.assertTrue(all(gates.values()), gates)
        cells[-1]["response_map"] = {"task": "B"}
        _, gates = evaluate_pairs(cells, contract["advance"])
        self.assertFalse(gates["exact_responses_between_modes"])


if __name__ == "__main__":
    unittest.main()
