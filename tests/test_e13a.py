import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from experiments.e13a_freeze import build_contract, derive_certificates
from experiments.e13a_ingest import count_output_mismatches, expected_trace
from experiments.e13a_probe import cache_decision, token_fingerprint
from experiments.e13a_retain import validate_inventory


class E13aFreezeTests(unittest.TestCase):
    def test_retained_calibration_freezes_complete_fail_closed_partition(self) -> None:
        root = Path(__file__).resolve().parents[1]
        contract = build_contract(root)
        self.assertEqual(len(contract["policy"]["certified_allowlist"]), 44)
        self.assertEqual(len(contract["policy"]["fallback_denylist"]), 4)
        self.assertEqual(
            contract["execution"]["expected_controller_requests_per_trace"],
            {
                "certified_cache": 149,
                "calibration_fallback": 16,
                "unknown_fallback": 0,
            },
        )

    def test_any_exact_response_difference_denies_fingerprint(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads(
            (root / "results/manifests/e9c-30770403695.json").read_text()
        )
        policy = derive_certificates(manifest)
        denied = {item["prompt_sha256"] for item in policy["fallback_denylist"]}
        self.assertIn(
            "98085bead66cacac19f2e731c7e3d6f27962aaaaeed44ce5426ebd929985dfdc",
            denied,
        )


class E13aPolicyTests(unittest.TestCase):
    def test_unknown_fingerprint_fails_closed(self) -> None:
        self.assertEqual(
            cache_decision("certificate", "unknown", {"safe"}, {"fragile"}),
            (False, "unknown_fallback"),
        )

    def test_certified_and_denied_routes_are_exact(self) -> None:
        self.assertEqual(
            cache_decision("certificate", "safe", {"safe"}, {"fragile"}),
            (True, "certified_cache"),
        )
        self.assertEqual(
            cache_decision("certificate", "fragile", {"safe"}, {"fragile"}),
            (False, "calibration_fallback"),
        )

    def test_token_fingerprint_is_compact_json_sha256(self) -> None:
        self.assertEqual(
            token_fingerprint([1, 2, 3]),
            "a615eeaee21de5179de080de8c3052c8da901138406ba71c38c032845f7d54f4",
        )


class E13aIngestTests(unittest.TestCase):
    def test_trace_is_exactly_165_requests(self) -> None:
        root = Path(__file__).resolve().parents[1]
        trace = expected_trace(build_contract(root))
        self.assertEqual(len(trace), 165)
        self.assertEqual(sum(item["phase"] == "measured" for item in trace), 144)

    def test_output_comparison_requires_prompt_identity(self) -> None:
        left = [{"global_index": 0, "prompt_sha256": "a", "response": "A"}]
        right = [{"global_index": 0, "prompt_sha256": "a", "response": "B"}]
        self.assertEqual(count_output_mismatches(left, right), 1)
        right[0]["prompt_sha256"] = "b"
        with self.assertRaises(ValueError):
            count_output_mismatches(left, right)

    def test_scripts_support_direct_workflow_entrypoints(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for script in (
            "e13a_probe.py",
            "e13a_ingest.py",
            "e13a_freeze.py",
            "e13a_retain.py",
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

    def test_freeze_round_trip_is_deterministic(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            for output in (first, second):
                subprocess.run(
                    [
                        sys.executable,
                        str(root / "experiments/e13a_freeze.py"),
                        "--root",
                        str(root),
                        "--output",
                        str(output),
                    ],
                    check=True,
                )
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_inventory_rejects_unlisted_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            (evidence / "kept.txt").write_text("kept\n")
            digest = hashlib.sha256(b"kept\n").hexdigest()
            (evidence / "file-inventory-sha256.txt").write_text(
                f"{digest}  /tmp/results/raw/e13a-cache-certificate-1-1/kept.txt\n"
            )
            self.assertEqual(validate_inventory(evidence)["file_count"], 1)
            (evidence / "extra.txt").write_text("extra\n")
            with self.assertRaises(ValueError):
                validate_inventory(evidence)


if __name__ == "__main__":
    unittest.main()
