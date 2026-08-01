from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "e6d_ingest", ROOT / "experiments/e6d_ingest.py"
)
assert SPEC and SPEC.loader
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


class E6dIngestTests(unittest.TestCase):
    def test_acceptance_requires_all_three_current_patch_proofs(self) -> None:
        feature = {
            "baseline_exit_status": 1,
            "patched_exit_status": 0,
            "validated_sve_disabled": True,
            "configuration_bound": True,
            "baseline_invalid_sve_source_observed": True,
            "patched_invalid_sve_source_absent": True,
        }
        tests = {
            "baseline": {
                "build_exit_status": 0,
                "quantize_exit_status": 0,
                "reasoning_exit_status": 134,
                "reasoning_regression_reproduced": True,
                "configuration_bound": True,
                "assembly": {
                    "byte_stores": 32,
                    "vector_narrows": 0,
                    "vector_stores": 0,
                },
            },
            "patched": {
                "build_exit_status": 0,
                "quantize_exit_status": 0,
                "reasoning_exit_status": 0,
                "reasoning_complete_suite_passed": True,
                "configuration_bound": True,
                "assembly": {
                    "byte_stores": 0,
                    "vector_narrows": 6,
                    "vector_stores": 2,
                },
            },
        }
        direct = {
            "4096": {"median_improvement_ratio": 2.0, "improved_rounds": 4},
            "65536": {"median_improvement_ratio": 1.8, "improved_rounds": 4},
        }
        acceptance = {
            "minimum_median_improvement_ratio_by_size": {
                "4096": 1.25,
                "65536": 1.15,
            },
            "minimum_improved_rounds_by_size": {"4096": 3, "65536": 3},
            "minimum_baseline_byte_stores": 16,
            "maximum_patched_byte_stores": 4,
            "minimum_patched_vector_narrows": 2,
            "minimum_patched_vector_stores": 2,
        }
        criteria = INGEST.evaluate(feature, tests, direct, acceptance)
        self.assertTrue(all(criteria.values()))

        feature["patched_invalid_sve_source_absent"] = False
        self.assertFalse(
            INGEST.evaluate(feature, tests, direct, acceptance)[
                "patched_feature_build_passed"
            ]
        )
        feature["patched_invalid_sve_source_absent"] = True
        tests["patched"]["reasoning_complete_suite_passed"] = False
        self.assertFalse(
            INGEST.evaluate(feature, tests, direct, acceptance)[
                "reasoning_patch_passed"
            ]
        )

    def test_contract_rejects_post_observation_order_changes(self) -> None:
        contract = INGEST.load_object(ROOT / "experiments/e6d_contract.json")
        INGEST.validate_contract(contract)
        contract["quantizer"]["rounds"].reverse()
        with self.assertRaisesRegex(ValueError, "frozen balanced order"):
            INGEST.validate_contract(contract)


if __name__ == "__main__":
    unittest.main()
