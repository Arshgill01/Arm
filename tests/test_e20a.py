import json
import tempfile
import unittest
from pathlib import Path

from experiments.e20a_freeze import build_contract
from experiments.e20a_ingest import (
    choose_fusion,
    classify_projection,
    parse_node_timing,
)


class E20aTests(unittest.TestCase):
    def test_frozen_contract_matches_generator(self) -> None:
        path = Path("experiments/e20a_contract.json")
        if not path.exists():
            self.skipTest("E20a contract has not been frozen")
        frozen = json.loads(path.read_text())
        generated = build_contract(Path("."))
        for name in ("ingest", "test"):
            for suffix in ("path", "sha256"):
                key = f"{name}_{suffix}"
                generated["inputs"][key] = frozen["inputs"][key]
        self.assertEqual(frozen, generated)

    def test_contract_is_bounded_and_separates_control_from_timing(self) -> None:
        contract = build_contract(Path("."))
        cases = contract["benchmark"]["cases"]
        self.assertEqual(len(cases), 6)
        self.assertEqual(
            [(item["mode"], item["node_timing"]) for item in cases],
            [
                ("pp512", False),
                ("pp512", True),
                ("pp4096", False),
                ("pp4096", True),
                ("tg128", False),
                ("tg128", True),
            ],
        )
        self.assertFalse(contract["selection"]["automatic_source_optimization_allowed"])

    def test_projection_classification_is_exact(self) -> None:
        self.assertEqual(
            classify_projection("blk.25.attn_v.weight"),
            ("attention_qkv", 25, "v"),
        )
        self.assertEqual(
            classify_projection("blk.0.ffn_gate.weight"),
            ("ffn_gate_up", 0, "gate"),
        )
        self.assertIsNone(classify_projection("blk.0.ffn_down.weight"))

    def test_structured_timing_parser(self) -> None:
        line = (
            "ggml_cpu_node_timing\tgraph=7\tnode=8\top=MUL_MAT\tname=node"
            "\tsrc0=blk.0.attn_q.weight\tsrc1=attn_norm-0\tne=3072,4,1,1"
            "\tfused_nodes=0\telapsed_us=123\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timing.log"
            path.write_text(line)
            records = parse_node_timing(path)
        self.assertEqual(records[0]["elapsed_us"], 123)
        self.assertEqual(records[0]["ne"], [3072, 4, 1, 1])

    def test_structured_timing_parser_allows_zero_work_node(self) -> None:
        line = (
            "ggml_cpu_node_timing\tgraph=4\tnode=825\top=GET_ROWS\tname=node_825"
            "\tsrc0=attn_out-25\tsrc1=leaf_293\tne=3072,0,1,1"
            "\tfused_nodes=0\telapsed_us=0\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timing.log"
            path.write_text(line)
            records = parse_node_timing(path)
        self.assertEqual(records[0]["ne"], [3072, 0, 1, 1])
        self.assertEqual(records[0]["elapsed_us"], 0)

    def test_selection_rule_is_mechanical(self) -> None:
        contract = build_contract(Path("."))
        traces = {}
        for mode in ("pp512", "pp4096"):
            traces[mode] = {
                "family_share": {"attention_qkv": 0.20, "ffn_gate_up": 0.30},
                "shared_activation_layers": {"attention_qkv": 26, "ffn_gate_up": 26},
            }
        decision = choose_fusion(traces, contract)
        self.assertEqual(decision["selected_family"], "ffn_gate_up")
        traces["pp4096"]["family_share"]["ffn_gate_up"] = 0.09
        decision = choose_fusion(traces, contract)
        self.assertEqual(decision["selected_family"], "attention_qkv")


if __name__ == "__main__":
    unittest.main()
