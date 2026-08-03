import json
import unittest
from pathlib import Path

from experiments.e12b_freeze import enrich_candidates
from experiments.e12b_ingest import candidate_from_contract, frontier


class E12bPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(Path("experiments/e12b_plan.json").read_text())
        cls.candidates = {item["candidate"]: item for item in cls.plan["candidates"]}

    def test_candidate_names_and_recipes_are_unique(self) -> None:
        self.assertEqual(len(self.candidates), 9)
        recipes = [
            tuple(item["argv_after_binary"]) for item in self.candidates.values()
        ]
        self.assertEqual(len(set(recipes)), len(recipes))

    def test_matched_pairs_bind_controls_to_imatrix_equivalents(self) -> None:
        for control_name, imatrix_name in self.plan["matched_pairs"]:
            control = self.candidates[control_name]
            imatrix = self.candidates[imatrix_name]
            self.assertEqual(control["base_quantization"], imatrix["base_quantization"])
            self.assertFalse(control["uses_imatrix"])
            self.assertTrue(imatrix["uses_imatrix"])
            self.assertNotIn("--imatrix", control["argv_after_binary"])
            self.assertIn("--imatrix", imatrix["argv_after_binary"])

    def test_mixed_recipes_retain_explicit_overrides(self) -> None:
        mixed = [
            item
            for item in self.candidates.values()
            if item["role"] == "predefined mixed-tensor candidate"
        ]
        self.assertEqual(len(mixed), 3)
        self.assertTrue(
            all(
                "--tensor-type" in item["argv_after_binary"]
                or "--output-tensor-type" in item["argv_after_binary"]
                for item in mixed
            )
        )

    def test_prerequisites_bind_exact_unobserved_runs(self) -> None:
        self.assertEqual(self.plan["prerequisites"]["e10d"]["run_id"], "30818303255")
        self.assertEqual(self.plan["prerequisites"]["e12a"]["run_id"], "30822632328")
        self.assertIn("do not silently substitute", self.plan["prerequisites"]["failure_rule"])

    def test_candidate_lookup_is_fail_closed(self) -> None:
        selected = candidate_from_contract(self.plan, "e12b_iq4_xs_imatrix")
        self.assertEqual(selected["base_quantization"], "IQ4_XS")
        with self.assertRaises(ValueError):
            candidate_from_contract(self.plan, "not-frozen")

    def test_frontier_uses_every_quality_coordinate_and_bytes(self) -> None:
        def point(name: str, size: int, scores: tuple[float, float, float]):
            return {
                "model": {"candidate": name, "size_bytes": size},
                "quality_coordinates": dict(
                    zip(
                        (
                            "e9b_arc_easy.acc_norm",
                            "e9b_hellaswag.acc_norm",
                            "e9b_winogrande.acc",
                        ),
                        scores,
                        strict=True,
                    )
                ),
            }

        cells = [
            point("small", 100, (0.5, 0.5, 0.5)),
            point("dominated", 110, (0.5, 0.5, 0.5)),
            point("quality", 120, (0.6, 0.5, 0.5)),
            point("tradeoff", 90, (0.4, 0.7, 0.5)),
        ]
        self.assertEqual(frontier(cells), ["small", "quality", "tradeoff"])

    def test_mixed_override_proof_is_mechanical(self) -> None:
        candidates = {
            item["candidate"]: item for item in enrich_candidates(self.plan)
        }
        embedding = candidates["e12b_q3_k_m_output_embed_q6"][
            "override_validation"
        ]
        self.assertEqual(
            embedding["exact_tensor_types"], {"token_embd.weight": "Q6_K"}
        )
        self.assertIn("no output.weight", embedding["structural_note"])
        attention = candidates["e12b_iq4_xs_v_down_q5"]["override_validation"]
        self.assertEqual(attention["minimum_manual_override_lines"], 52)
        self.assertEqual(
            sum(item["expected_tensors"] for item in attention["tensor_type_patterns"]),
            52,
        )
        edges = candidates["e12b_q4_k_s_edge_layers_q6"]["override_validation"]
        self.assertEqual(edges["tensor_type_patterns"][0]["expected_tensors"], 28)


if __name__ == "__main__":
    unittest.main()
