import json
import tempfile
import unittest
from pathlib import Path

from experiments.evidence_readiness import (
    EvidenceShapeError,
    _fixture_plan,
    canonical_json_bytes,
    classify_cells,
    evaluate_readiness,
    load_slots_array,
    run_fixture_suite,
    validate_timing_record,
    verify_byte_stable_replay,
)


POLICY_PATH = Path("experiments/evidence_readiness_policy.json")


class EvidenceReadinessTests(unittest.TestCase):
    def test_slots_endpoint_requires_array_of_objects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.json"
            path.write_text(json.dumps([{"id": 0}]))
            self.assertEqual(load_slots_array(path), [{"id": 0}])
            path.write_text(json.dumps({"slots": []}))
            with self.assertRaisesRegex(EvidenceShapeError, "array of slot objects"):
                load_slots_array(path)

    def test_timings_fail_closed_by_failure_class(self) -> None:
        self.assertEqual(
            validate_timing_record(
                {"http_ms": 5, "encode_ms": 2.5}, ("http_ms", "encode_ms")
            ),
            {"http_ms": 5.0, "encode_ms": 2.5},
        )
        cases = (
            ({"http_ms": 5}, "missing"),
            ({"http_ms": 5, "encode_ms": None}, "null"),
            ({"http_ms": 5, "encode_ms": "2.5"}, "unsupported type"),
            ({"http_ms": 5, "encode_ms": float("inf")}, "finite"),
        )
        for record, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(EvidenceShapeError, message):
                    validate_timing_record(record, ("http_ms", "encode_ms"))

    def test_complete_failed_and_partial_cells_are_distinct(self) -> None:
        result = classify_cells(
            (
                {
                    "cell_id": "complete",
                    "return_code": 0,
                    "probe": {},
                    "raw_requests": ["raw/one.json"],
                    "inventory_verified": True,
                },
                {"cell_id": "failed", "return_code": 1, "failure": "boom"},
                {"cell_id": "partial", "return_code": 0},
            ),
            ("complete", "failed", "partial", "missing"),
        )
        self.assertEqual(result["complete"], ["complete"])
        self.assertEqual(result["failed"], ["failed"])
        self.assertEqual(result["partial"], ["partial"])
        self.assertEqual(result["missing"], ["missing"])
        self.assertFalse(result["claim_ready"])

    def test_independent_replay_must_be_byte_stable(self) -> None:
        value, replay = verify_byte_stable_replay(lambda: {"b": 2, "a": 1})
        self.assertEqual(value, {"a": 1, "b": 2})
        self.assertTrue(replay["byte_stable"])
        counter = iter((1, 2))
        with self.assertRaisesRegex(EvidenceShapeError, "not byte-stable"):
            verify_byte_stable_replay(lambda: {"value": next(counter)})

    def test_matrix_waits_for_exact_native_pair(self) -> None:
        policy = json.loads(POLICY_PATH.read_text())
        planned = evaluate_readiness(
            _fixture_plan(share=0.08, speedup=2.0, status="planned"), policy
        )
        passed = evaluate_readiness(
            _fixture_plan(share=0.08, speedup=2.0, status="passed"), policy
        )
        self.assertEqual(planned["decision"], "await_native_preflight")
        self.assertFalse(planned["matrix_allowed"])
        self.assertEqual(passed["decision"], "matrix_allowed")
        self.assertTrue(passed["matrix_allowed"])

    def test_sub_three_percent_lane_stops_without_alternate_value(self) -> None:
        policy = json.loads(POLICY_PATH.read_text())
        plan = _fixture_plan(share=0.01, speedup="unbounded", status="passed")
        result = evaluate_readiness(plan, policy)
        self.assertEqual(result["decision"], "stop_below_amdahl_floor")
        self.assertFalse(result["matrix_allowed"])
        plan["value_contract"]["alternate_values"] = ["memory"]
        result = evaluate_readiness(plan, policy)
        self.assertEqual(result["decision"], "matrix_allowed")

    def test_fixture_suite_is_byte_stable_and_covers_raw_inventory(self) -> None:
        first = run_fixture_suite(POLICY_PATH)
        second = run_fixture_suite(POLICY_PATH)
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
        self.assertEqual(first["artifact_shape_fixture"]["raw"]["request_count"], 2)
        self.assertEqual(
            first["artifact_shape_fixture"]["inventory"]["file_count"], 2
        )
        self.assertEqual(
            first["readiness_decisions"]["below_floor"]["decision"],
            "stop_below_amdahl_floor",
        )


if __name__ == "__main__":
    unittest.main()
