from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "e5_ingest.py"
SPEC = importlib.util.spec_from_file_location("e5_ingest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


def contract() -> dict:
    return {
        "probe": {
            "warmups": 1,
            "measured_requests": 2,
            "concurrency": 2,
            "timeout_seconds": 5.0,
            "method_mix": "alternating GET and POST",
        },
        "acceptance": {
            "http_status": 200,
            "minimum_requests_per_second": 10.0,
            "maximum_p95_latency_ms": 50.0,
        },
    }


def probe() -> dict:
    requests = [
        {
            "index": 0,
            "method": "GET",
            "status": 200,
            "latency_ms": 2.0,
            "valid": True,
            "error": None,
        },
        {
            "index": 1,
            "method": "POST",
            "status": 200,
            "latency_ms": 4.0,
            "valid": True,
            "error": None,
        },
    ]
    return {
        "experiment_id": "E5a",
        "parameters": {
            "warmups": 1,
            "requests": 2,
            "concurrency": 2,
            "timeout_seconds": 5.0,
            "method_mix": "alternating GET and POST",
        },
        "result": {
            "valid_responses": 2,
            "failures": 0,
            "elapsed_seconds": 0.01,
            "requests_per_second": 200.0,
            "latency_ms": INGEST.summarize([2.0, 4.0]),
            "status_counts": {"200": 2},
        },
        "requests": requests,
    }


class E5IngestTests(unittest.TestCase):
    def test_valid_probe_is_recomputed_from_requests(self) -> None:
        result = INGEST.validate_probe(probe(), contract())
        self.assertEqual(3.0, result["latency_ms"]["median"])
        self.assertEqual(200.0, result["requests_per_second"])

    def test_invalid_response_and_latency_slo_fail_closed(self) -> None:
        evidence = probe()
        evidence["requests"][0]["valid"] = False
        with self.assertRaisesRegex(ValueError, "invalid measured HTTP request"):
            INGEST.validate_probe(evidence, contract())
        evidence = probe()
        evidence["requests"][1]["latency_ms"] = 51.0
        evidence["result"]["latency_ms"] = INGEST.summarize([2.0, 51.0])
        with self.assertRaisesRegex(ValueError, "p95 latency"):
            INGEST.validate_probe(evidence, contract())


if __name__ == "__main__":
    unittest.main()
