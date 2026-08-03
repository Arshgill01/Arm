import json
import tempfile
import unittest
from pathlib import Path

from experiments.e5b_ingest import sha256_file
from experiments.e11a_ingest import (
    aggregate_summary,
    dominates,
    pareto_frontier,
    quality_coordinates,
)


def cell(name: str, size: int, arc: float, hella: float, wino: float) -> dict:
    return {
        "model": {"candidate": name, "size_bytes": size},
        "quality_coordinates": {
            "e9b_arc_easy.acc_norm": arc,
            "e9b_hellaswag.acc_norm": hella,
            "e9b_winogrande.acc": wino,
        },
    }


class E11aFrontierTests(unittest.TestCase):
    def test_quality_coordinates_use_only_frozen_metrics(self) -> None:
        metrics = {
            "e9b_arc_easy": {"acc": 0.4, "acc_norm": 0.5},
            "e9b_hellaswag": {"acc": 0.3, "acc_norm": 0.6},
            "e9b_winogrande": {"acc": 0.7},
        }
        self.assertEqual(
            quality_coordinates(metrics),
            {
                "e9b_arc_easy.acc_norm": 0.5,
                "e9b_hellaswag.acc_norm": 0.6,
                "e9b_winogrande.acc": 0.7,
            },
        )

    def test_smaller_equal_quality_dominates(self) -> None:
        smaller = cell("smaller", 10, 0.5, 0.6, 0.7)
        larger = cell("larger", 20, 0.5, 0.6, 0.7)
        self.assertTrue(dominates(smaller, larger))
        self.assertFalse(dominates(larger, smaller))

    def test_tradeoffs_remain_on_frontier(self) -> None:
        small = cell("small", 10, 0.4, 0.5, 0.6)
        quality = cell("quality", 20, 0.6, 0.7, 0.8)
        dominated = cell("dominated", 30, 0.5, 0.6, 0.7)
        self.assertEqual(
            pareto_frontier([small, quality, dominated]), ["small", "quality"]
        )

    def test_aggregate_reuses_exact_anchor_and_preserves_full_ladder(self) -> None:
        contract_path = Path("experiments/e11a_contract.json")
        contract = json.loads(contract_path.read_text())
        contract_sha = sha256_file(contract_path)
        prepared_sha = "a" * 64
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cells = []
            for index, model in enumerate(contract["models"]):
                value = {
                    "status": "valid_stock_quant_quality_cell",
                    "contract_sha256": contract_sha,
                    "prepared_sha256": prepared_sha,
                    "model": model,
                    "quality_coordinates": {
                        "e9b_arc_easy.acc_norm": 0.5 + index / 100,
                        "e9b_hellaswag.acc_norm": 0.5 + index / 100,
                        "e9b_winogrande.acc": 0.5 + index / 100,
                    },
                    "request_failures": 0,
                }
                path = root / f"cell-{index}.json"
                path.write_text(json.dumps(value))
                cells.append(path)
            primary = {
                "model": contract["anchor_model"],
                "prepared_sha256": prepared_sha,
                "metrics": {
                    "e9b_arc_easy": {"acc_norm": 0.7},
                    "e9b_hellaswag": {"acc_norm": 0.7},
                    "e9b_winogrande": {"acc": 0.7},
                },
                "request_failures": 0,
            }
            control = {
                "model": {
                    "role": "control",
                    "candidate": "ministral3_3b_q4_0",
                    "quantization": "Q4_0",
                    "sha256": "bd1eef40a7fdb1ba9728ec977bd4aab40fb76993d6ec37377fd6522703dc88a5",
                    "size_bytes": 2046375200,
                },
                "request_failures": 0,
            }
            anchor = {
                "status": "valid_external_holdout",
                "contract_sha256": contract["inputs"]["adapter_contract_sha256"],
                "prepared_sha256": prepared_sha,
                "models": [primary, control],
            }
            anchor_path = root / "anchor.json"
            anchor_path.write_text(json.dumps(anchor))
            result = aggregate_summary(contract_path, cells, anchor_path)
        self.assertEqual(result["status"], "valid_stock_quant_quality_ladder")
        self.assertEqual(
            [item["model"]["candidate"] for item in result["models"]],
            contract["full_candidate_order"],
        )
        self.assertEqual(result["q4_0_diagnostic_control"], control)


if __name__ == "__main__":
    unittest.main()
