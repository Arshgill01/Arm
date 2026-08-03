import json
import subprocess
import sys
import unittest
from pathlib import Path

from experiments.e14b_freeze import attention_tensor_names, build_contract
from experiments.e14b_ingest import (
    non_dominated_names,
    parse_excluded_tensors,
)


class E14bFreezeTests(unittest.TestCase):
    def test_tensor_groups_are_architecturally_complete(self) -> None:
        names = attention_tensor_names()
        self.assertEqual(len(names), 104)
        self.assertEqual(len(set(names)), 104)
        self.assertIn("blk.0.attn_q.weight", names)
        self.assertIn("blk.25.attn_output.weight", names)

    def test_contract_freezes_four_points_and_reverse_balance(self) -> None:
        root = Path(__file__).resolve().parents[1]
        contract = build_contract(root)
        self.assertEqual(len(contract["execution"]["configurations"]), 4)
        self.assertEqual(len(contract["execution"]["order"]), 8)
        self.assertEqual(
            len(
                contract["execution"]["configurations"]["attention_down_raw"][
                    "expected_excluded_tensors"
                ]
            ),
            130,
        )
        order = contract["execution"]["order"]
        names = [item["configuration"] for item in order]
        self.assertEqual(names, list(reversed(names)))
        self.assertEqual(
            [item["repetition"] for item in order],
            [1, 1, 1, 1, 2, 2, 2, 2],
        )
        e14a = json.loads((root / "experiments/e14a_contract.json").read_text())
        self.assertEqual(
            contract["execution"]["configurations"],
            e14a["execution"]["configurations"],
        )
        self.assertEqual(contract["execution"]["order"], e14a["execution"]["order"])
        self.assertEqual(contract["request"], e14a["request"])
        self.assertEqual(contract["acceptance"], e14a["acceptance"])
        self.assertEqual(contract["mechanism"]["proof_log_verbosity"], 4)
        integrity = contract["successor_integrity"]
        self.assertTrue(integrity["configurations_equal_e14a"])
        self.assertTrue(integrity["order_equal_e14a"])
        self.assertTrue(integrity["request_equal_e14a"])
        self.assertTrue(integrity["acceptance_equal_e14a"])
        self.assertFalse(integrity["results_used_to_change_groups_order_or_gates"])

    def test_frozen_contract_matches_generator(self) -> None:
        root = Path(__file__).resolve().parents[1]
        frozen = json.loads((root / "experiments/e14b_contract.json").read_text())
        self.assertEqual(frozen, build_contract(root))


class E14bIngestTests(unittest.TestCase):
    def test_exclusion_log_is_deduplicated_and_sorted(self) -> None:
        text = "\n".join(
            [
                "ggml_repack_tensor_is_excluded: excluded tensor blk.2.attn_q.weight",
                "ggml_repack_tensor_is_excluded: excluded tensor blk.1.attn_q.weight",
                "ggml_repack_tensor_is_excluded: excluded tensor blk.2.attn_q.weight",
            ]
        )
        self.assertEqual(
            parse_excluded_tensors(text),
            ["blk.1.attn_q.weight", "blk.2.attn_q.weight"],
        )

    def test_frontier_rejects_dominated_point(self) -> None:
        def point(rss: float, throughput: float) -> dict:
            return {
                "maximum_rss_kib": {"max": rss},
                "requests_per_second": {"median": throughput},
            }

        performance = {
            "small": point(2.0, 1.0),
            "dominated": point(3.0, 0.9),
            "fast": point(4.0, 2.0),
        }
        self.assertEqual(non_dominated_names(performance), ["fast", "small"])

    def test_entrypoints_are_directly_runnable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for script in (
            "e14b_freeze.py",
            "e14b_ingest.py",
            "e14b_retain.py",
        ):
            completed = subprocess.run(
                [sys.executable, str(root / "experiments" / script), "--help"],
                cwd=root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
