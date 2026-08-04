import json
import unittest
from pathlib import Path

from experiments.e20b_freeze import build_contract
from experiments.e20b_ingest import validate_ffn_records


class E20bTests(unittest.TestCase):
    def test_frozen_contract_matches_generator(self) -> None:
        path = Path("experiments/e20b_contract.json")
        if not path.exists():
            self.skipTest("E20b contract has not been frozen")
        self.assertEqual(json.loads(path.read_text()), build_contract(Path(".")))

    def test_contract_freezes_exact_execution_path_and_order(self) -> None:
        contract = build_contract(Path("."))
        path = contract["prerequisites"]["execution_path"]
        self.assertEqual(
            path,
            {
                "layers": 26,
                "projections_per_layer": ["gate", "up"],
                "weight_type": "q4_K",
                "activation_parameter_type": "q8_K",
                "input_width": 3072,
                "output_width": 9216,
            },
        )
        order = contract["execution"]["order"]
        self.assertEqual(len(order), 12)
        self.assertEqual(
            [item["profile"] for item in order],
            ["reuse_off", "reuse_on", "reuse_on", "reuse_off"] * 3,
        )
        self.assertEqual(
            {(item["profile"], item["repetition"]) for item in order},
            {
                (profile, repetition)
                for profile in ("reuse_off", "reuse_on")
                for repetition in range(1, 7)
            },
        )

    def test_profiles_use_one_binary_with_timing_disabled(self) -> None:
        contract = build_contract(Path("."))
        profiles = contract["build"]["profiles"]
        self.assertTrue(contract["build"]["single_binary_for_both_profiles"])
        self.assertEqual(
            profiles["reuse_off"]["environment"],
            {
                "GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION": "0",
                "GGML_CPU_NODE_TIMING": "0",
            },
        )
        self.assertEqual(
            profiles["reuse_on"]["environment"],
            {
                "GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION": "1",
                "GGML_CPU_NODE_TIMING": "0",
            },
        )
        self.assertTrue(contract["decision"]["pair_fusion_default_remains_off"])

    def test_mechanism_counts_are_exact(self) -> None:
        contract = build_contract(Path("."))
        preflight = contract["mechanism_preflight"]
        self.assertEqual(preflight["control_expected_separate_ffn_nodes"], 52)
        self.assertEqual(preflight["candidate_expected_fused_ffn_pairs"], 26)
        self.assertTrue(preflight["diagnostic_timing_not_performance_evidence"])

    def test_mechanism_record_validator_accepts_only_expected_shapes(self) -> None:
        contract = build_contract(Path("."))

        def record(layer: int, role: str, fused: int) -> dict[str, object]:
            return {
                "graph": 4,
                "node": layer * 32 + (28 if role == "gate" else 29),
                "op": "MUL_MAT",
                "name": f"ffn_{role}-{layer}",
                "src0": f"blk.{layer}.ffn_{role}.weight",
                "src1": f"ffn_norm-{layer}",
                "ne": [9216, 512, 1, 1],
                "fused_nodes": fused,
                "elapsed_us": 1,
            }

        control = [
            record(layer, role, 0)
            for layer in range(26)
            for role in ("gate", "up")
        ]
        candidate = [record(layer, "gate", 1) for layer in range(26)]
        self.assertEqual(
            len(validate_ffn_records(control, "reuse_off", contract)), 26
        )
        self.assertEqual(
            len(validate_ffn_records(candidate, "reuse_on", contract)), 26
        )
        candidate[0]["fused_nodes"] = 0
        with self.assertRaises(ValueError):
            validate_ffn_records(candidate, "reuse_on", contract)

    def test_promotion_gates_match_frozen_hypothesis(self) -> None:
        acceptance = build_contract(Path("."))["acceptance"]
        self.assertEqual(acceptance["minimum_throughput_ratio"], 1.02)
        self.assertEqual(acceptance["maximum_median_http_latency_ratio"], 0.99)
        self.assertEqual(acceptance["maximum_p95_http_latency_ratio"], 1.02)
        self.assertEqual(acceptance["maximum_cpu_seconds_per_request_ratio"], 0.99)
        self.assertEqual(acceptance["maximum_ready_time_ratio"], 1.10)
        self.assertEqual(acceptance["maximum_candidate_rss_ratio"], 1.02)
        self.assertEqual(acceptance["maximum_runtime_closure_ratio"], 1.0)
        self.assertEqual(acceptance["maximum_candidate_throughput_cv"], 0.02)

    def test_patch_is_narrow_and_fail_closed(self) -> None:
        path = Path(
            "patches/llama.cpp/b10216/0009-reuse-repack-pair-activation.patch"
        )
        patch = path.read_text()
        changed = [
            line.removeprefix("diff --git a/").split(" b/", 1)[0]
            for line in patch.splitlines()
            if line.startswith("diff --git a/")
        ]
        self.assertEqual(
            changed,
            [
                "ggml/src/ggml-cpu/ggml-cpu.c",
                "ggml/src/ggml-cpu/repack.cpp",
                "ggml/src/ggml-cpu/traits.cpp",
                "ggml/src/ggml-cpu/traits.h",
            ],
        )
        for token in (
            "GGML_CPU_REPACK_MUL_MAT_PAIR_FUSION",
            "node->src[1] == next->src[1]",
            "traits0 == traits1",
            "compute_forward_pair",
            "ggml_barrier(params->threadpool)",
            "bool convert_src1 = true",
            "forward_mul_mat(params, op1, false)",
        ):
            self.assertIn(token, patch)


if __name__ == "__main__":
    unittest.main()
