import json
import unittest
from pathlib import Path

from experiments.e17b_failure_retain import (
    ALLOCATION_FAILURE,
    TIMEOUT_ERROR,
    artifact_inventory,
)


class E17bFailureRetainTests(unittest.TestCase):
    def test_failure_patterns_are_specific(self) -> None:
        self.assertEqual(
            TIMEOUT_ERROR.findall(
                "x\n20.20 W srv stop: cancel task, id_task = 21\n"
                "20.21 W srv stop: cancel task, id_task = 22\n"
            ),
            ["cancel task, id_task = 21", "cancel task, id_task = 22"],
        )
        self.assertEqual(
            ALLOCATION_FAILURE.findall(
                "ggml_aligned_malloc: insufficient memory "
                "(attempted to allocate 13312.00 MB)"
            ),
            ["13312.00"],
        )

    def test_real_artifact_inventory_is_complete_when_present(self) -> None:
        path = Path(".scratch/e17b-30857705994")
        if not path.exists():
            self.skipTest("downloaded E17b artifact is unavailable")
        inventory = artifact_inventory(path)
        self.assertGreaterEqual(inventory["file_count"], 100)
        self.assertEqual(len(inventory["inventory_sha256"]), 64)
        self.assertNotIn("run-metadata.json", inventory["entries"])

    def test_retained_failure_shape_when_present(self) -> None:
        path = Path("results/manifests/e17b-30857705994-failure.json")
        if not path.exists():
            self.skipTest("E17b failure has not been retained")
        manifest = json.loads(path.read_text())
        self.assertEqual(len(manifest["cells"]), 9)
        self.assertEqual(
            manifest["failure_summary"]["long_context_request_timeout_cells"], 8
        )
        self.assertFalse(
            manifest["failure_summary"]["valid_quality_or_performance_comparison_available"]
        )


if __name__ == "__main__":
    unittest.main()
