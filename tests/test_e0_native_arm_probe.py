from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "experiments" / "e0_native_arm_probe.py"
)
SPEC = importlib.util.spec_from_file_location("e0_native_arm_probe", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class NativeArmProbeTests(unittest.TestCase):
    def test_percentile_uses_nearest_rank(self) -> None:
        self.assertEqual(PROBE.percentile([10, 20, 30, 40, 50], 0.95), 50)
        self.assertEqual(PROBE.percentile([50, 10, 30, 20, 40], 0.50), 30)

    def test_microbenchmark_is_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            binary_path = Path(temporary_directory) / "microbench"
            compilation = PROBE.compile_microbench(binary_path)
            self.assertEqual(compilation["returncode"], 0)
            result = PROBE.run_microbench(binary_path, samples=5, iterations=10_000)

        self.assertEqual(result["samples"], 5)
        self.assertEqual(len(result["elapsed_ns"]), 5)
        self.assertGreater(result["summary"]["median"], 0)
        self.assertRegex(result["checksum"], r"^[0-9a-f]{16}$")


if __name__ == "__main__":
    unittest.main()
