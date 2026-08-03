import unittest

from experiments.e11a_ingest import pareto_frontier, quality_coordinates


class E11aSuccessorTests(unittest.TestCase):
    def test_quality_coordinates_remain_independent(self) -> None:
        metrics = {
            "e9b_arc_easy": {"acc_norm": 0.6},
            "e9b_hellaswag": {"acc_norm": 0.7},
            "e9b_winogrande": {"acc": 0.5},
        }
        self.assertEqual(
            quality_coordinates(metrics),
            {
                "e9b_arc_easy.acc_norm": 0.6,
                "e9b_hellaswag.acc_norm": 0.7,
                "e9b_winogrande.acc": 0.5,
            },
        )

    def test_frontier_does_not_weight_mixed_task_results(self) -> None:
        cells = [
            {
                "model": {"candidate": "small", "size_bytes": 10},
                "quality_coordinates": {"a": 0.6, "b": 0.4, "c": 0.5},
            },
            {
                "model": {"candidate": "large", "size_bytes": 20},
                "quality_coordinates": {"a": 0.5, "b": 0.7, "c": 0.5},
            },
            {
                "model": {"candidate": "dominated", "size_bytes": 30},
                "quality_coordinates": {"a": 0.5, "b": 0.3, "c": 0.4},
            },
        ]
        self.assertEqual(pareto_frontier(cells), ["small", "large"])


if __name__ == "__main__":
    unittest.main()
