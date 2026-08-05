#!/usr/bin/env python3
"""Fail-closed artifact-shape and native experiment-readiness checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any


class EvidenceShapeError(ValueError):
    """Raised when retained evidence does not match its frozen shape."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the repository's canonical, byte-stable JSON representation."""
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvidenceShapeError(f"{path.name} must contain a JSON object")
    return value


def load_slots_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(
        isinstance(slot, dict) for slot in value
    ):
        raise EvidenceShapeError(
            f"{path.name} must contain a JSON array of slot objects"
        )
    return value


def require_finite_number(record: Mapping[str, Any], field: str) -> float:
    if field not in record:
        raise EvidenceShapeError(f"timing.{field} is missing")
    value = record[field]
    if value is None:
        raise EvidenceShapeError(f"timing.{field} is null")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceShapeError(
            f"timing.{field} has unsupported type {type(value).__name__}"
        )
    result = float(value)
    if not math.isfinite(result):
        raise EvidenceShapeError(f"timing.{field} must be finite")
    return result


def validate_timing_record(
    record: Mapping[str, Any], required_fields: Iterable[str]
) -> dict[str, float]:
    return {field: require_finite_number(record, field) for field in required_fields}


def validate_sha256_inventory(
    root: Path, inventory_path: Path
) -> dict[str, Any]:
    root = root.resolve()
    entries: dict[str, str] = {}
    for line_number, line in enumerate(
        inventory_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        digest, separator, raw_relative = line.partition("  ")
        relative = PurePosixPath(raw_relative)
        if (
            separator != "  "
            or len(digest) != 64
            or digest != digest.lower()
            or any(character not in "0123456789abcdef" for character in digest)
            or not raw_relative
            or relative.is_absolute()
            or "." in relative.parts
            or ".." in relative.parts
            or relative.as_posix() != raw_relative
            or raw_relative in entries
        ):
            raise EvidenceShapeError(
                f"invalid inventory entry on line {line_number}"
            )
        path = (root / Path(*relative.parts)).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
            raise EvidenceShapeError(f"inventory path is unsafe or missing: {raw_relative}")
        if sha256_file(path) != digest:
            raise EvidenceShapeError(f"inventory hash differs: {raw_relative}")
        entries[raw_relative] = digest
    if not entries:
        raise EvidenceShapeError("inventory is empty")
    canonical = "".join(
        f"{digest}  {relative}\n" for relative, digest in sorted(entries.items())
    )
    return {
        "entries": entries,
        "file_count": len(entries),
        "inventory_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
    }


def validate_raw_request_layout(
    root: Path,
    expected_relative_paths: Iterable[str],
    inventory: Mapping[str, Any],
    required_keys: Iterable[str] = (),
) -> dict[str, Any]:
    paths = list(expected_relative_paths)
    if len(paths) != len(set(paths)) or not paths:
        raise EvidenceShapeError("raw request path set is empty or duplicated")
    entries = inventory.get("entries")
    if not isinstance(entries, dict):
        raise EvidenceShapeError("verified inventory entries are unavailable")
    records = []
    required = set(required_keys)
    for relative in paths:
        pure = PurePosixPath(relative)
        if (
            pure.is_absolute()
            or "." in pure.parts
            or ".." in pure.parts
            or pure.as_posix() != relative
            or relative not in entries
        ):
            raise EvidenceShapeError(f"raw request is not inventory-bound: {relative}")
        record = load_json_object(root / Path(*pure.parts))
        if not required.issubset(record):
            raise EvidenceShapeError(f"raw request keys differ: {relative}")
        records.append({"path": relative, "sha256": entries[relative]})
    return {
        "request_count": len(records),
        "paths": paths,
        "layout_sha256": hashlib.sha256(canonical_json_bytes(records)).hexdigest(),
        "all_requests_are_inventory_bound_json_objects": True,
    }


def classify_cells(
    cells: Iterable[Mapping[str, Any]], expected_cell_ids: Iterable[str]
) -> dict[str, Any]:
    expected = set(expected_cell_ids)
    observed: dict[str, Mapping[str, Any]] = {}
    for cell in cells:
        cell_id = cell.get("cell_id")
        if not isinstance(cell_id, str) or not cell_id or cell_id in observed:
            raise EvidenceShapeError("cell identity is missing or duplicated")
        observed[cell_id] = cell

    complete: list[str] = []
    failed: list[str] = []
    partial: list[str] = []
    for cell_id, cell in observed.items():
        return_code = cell.get("return_code")
        valid_return_code = isinstance(return_code, int) and not isinstance(
            return_code, bool
        )
        raw_requests = cell.get("raw_requests")
        if (
            valid_return_code
            and return_code == 0
            and isinstance(cell.get("probe"), dict)
            and isinstance(raw_requests, list)
            and bool(raw_requests)
            and all(isinstance(item, str) and item for item in raw_requests)
            and cell.get("inventory_verified") is True
        ):
            complete.append(cell_id)
        elif (
            valid_return_code
            and return_code != 0
            and isinstance(cell.get("failure"), str)
            and bool(cell["failure"].strip())
        ):
            failed.append(cell_id)
        else:
            partial.append(cell_id)

    missing = sorted(expected - observed.keys())
    unexpected = sorted(observed.keys() - expected)
    complete.sort()
    failed.sort()
    partial.sort()
    claim_ready = not failed and not partial and not missing and not unexpected
    return {
        "complete": complete,
        "failed": failed,
        "partial": partial,
        "missing": missing,
        "unexpected": unexpected,
        "claim_ready": claim_ready,
    }


def verify_byte_stable_replay(
    builder: Callable[[], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    first_value = builder()
    first_bytes = canonical_json_bytes(first_value)
    second_bytes = canonical_json_bytes(builder())
    if first_bytes != second_bytes:
        raise EvidenceShapeError("independent replay is not byte-stable")
    return first_value, {
        "independent_replays": 2,
        "byte_stable": True,
        "summary_bytes": len(first_bytes),
        "summary_sha256": hashlib.sha256(first_bytes).hexdigest(),
    }


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceShapeError(f"readiness.{name} must be an object")
    return value


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceShapeError(f"readiness.{name} must be a nonempty string")
    return value


def evaluate_readiness(
    plan: Mapping[str, Any], policy: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate a frozen lane plan without weakening any failed prerequisite."""
    if plan.get("schema_version") != 1 or policy.get("schema_version") != 1:
        raise EvidenceShapeError("readiness schema version differs")
    _nonempty_string(plan.get("experiment_id"), "experiment_id")
    target = _mapping(plan.get("target"), "target")
    required_target = _mapping(policy.get("required_target"), "required_target")
    if any(target.get(key) != value for key, value in required_target.items()):
        raise EvidenceShapeError("readiness target is not native ubuntu-24.04-arm")

    mechanism = _mapping(plan.get("mechanism_unit"), "mechanism_unit")
    synthetic = _mapping(plan.get("synthetic_replay"), "synthetic_replay")
    preflight = _mapping(plan.get("native_preflight"), "native_preflight")
    value = _mapping(plan.get("value_contract"), "value_contract")
    budget = _mapping(plan.get("budget"), "budget")
    for section_name, section in (
        ("mechanism_unit", mechanism),
        ("synthetic_replay", synthetic),
        ("native_preflight", preflight),
    ):
        _nonempty_string(section.get("command"), f"{section_name}.command")

    share = require_finite_number(mechanism, "affected_runtime_share")
    speedup = mechanism.get("component_speedup_ceiling")
    if not 0.0 <= share < 1.0:
        raise EvidenceShapeError("affected runtime share must be in [0, 1)")
    if speedup == "unbounded":
        denominator = 1.0 - share
    else:
        if (
            isinstance(speedup, bool)
            or not isinstance(speedup, (int, float))
            or not math.isfinite(float(speedup))
            or float(speedup) <= 1.0
        ):
            raise EvidenceShapeError("component speedup ceiling is invalid")
        denominator = 1.0 - share + share / float(speedup)
    computed_ceiling = 1.0 / denominator - 1.0
    frozen_ceiling = require_finite_number(
        mechanism, "system_throughput_gain_ceiling"
    )
    if not math.isclose(computed_ceiling, frozen_ceiling, abs_tol=1e-12):
        raise EvidenceShapeError("frozen Amdahl ceiling is inconsistent")

    if (
        synthetic.get("control_cells")
        != policy.get("synthetic_control_cells")
        or synthetic.get("candidate_cells")
        != policy.get("synthetic_candidate_cells")
    ):
        raise EvidenceShapeError("synthetic replay must contain one exact pair")
    if (
        preflight.get("control_cells") != policy.get("native_control_cells")
        or preflight.get("candidate_cells") != policy.get("native_candidate_cells")
        or preflight.get("runner") != required_target.get("runner")
        or preflight.get("architecture") != required_target.get("architecture")
    ):
        raise EvidenceShapeError("native preflight must contain one exact Arm64 pair")
    if preflight.get("status") not in {"planned", "passed", "failed"}:
        raise EvidenceShapeError("native preflight status is invalid")

    minimum = _mapping(value.get("minimum_product_result"), "minimum_product_result")
    _nonempty_string(minimum.get("metric"), "minimum_product_result.metric")
    minimum_delta = require_finite_number(minimum, "relative_delta")
    if minimum_delta <= 0.0:
        raise EvidenceShapeError("minimum product result must be positive")
    _nonempty_string(value.get("claim_unlocked"), "value_contract.claim_unlocked")
    alternatives = value.get("alternate_values")
    allowed_alternatives = set(policy.get("allowed_alternate_values", []))
    if (
        not isinstance(alternatives, list)
        or any(item not in allowed_alternatives for item in alternatives)
        or len(alternatives) != len(set(alternatives))
    ):
        raise EvidenceShapeError("alternate product value set differs")
    runtime_minutes = require_finite_number(budget, "maximum_runtime_minutes")
    storage_bytes = require_finite_number(budget, "maximum_storage_bytes")
    if runtime_minutes <= 0.0 or storage_bytes <= 0.0:
        raise EvidenceShapeError("runtime and storage budgets must be positive")

    floor = require_finite_number(policy, "minimum_system_gain_ceiling")
    economic_value = frozen_ceiling >= floor or bool(alternatives)
    mechanism_passed = mechanism.get("status") == "passed"
    synthetic_passed = (
        synthetic.get("status") == "passed"
        and synthetic.get("byte_stable") is True
    )
    native_passed = preflight.get("status") == "passed"
    if not mechanism_passed:
        decision = "stop_mechanism_unit_not_proved"
    elif not synthetic_passed:
        decision = "stop_synthetic_replay_not_proved"
    elif not economic_value:
        decision = "stop_below_amdahl_floor"
    elif preflight.get("status") == "planned":
        decision = "await_native_preflight"
    elif not native_passed:
        decision = "stop_native_preflight_failed"
    else:
        decision = "matrix_allowed"
    return {
        "decision": decision,
        "matrix_allowed": decision == "matrix_allowed",
        "mechanism_unit_passed": mechanism_passed,
        "synthetic_replay_passed": synthetic_passed,
        "native_preflight_passed": native_passed,
        "economic_value_present": economic_value,
        "affected_runtime_share": share,
        "computed_system_throughput_gain_ceiling": computed_ceiling,
        "minimum_system_gain_ceiling": floor,
        "alternate_values": alternatives,
        "budget": {
            "maximum_runtime_minutes": runtime_minutes,
            "maximum_storage_bytes": storage_bytes,
        },
    }


def _capture_timing_rejection(record: Mapping[str, Any]) -> str:
    try:
        validate_timing_record(record, ("http_ms", "encode_ms"))
    except EvidenceShapeError as error:
        return str(error)
    raise AssertionError("invalid timing fixture was unexpectedly accepted")


def _fixture_plan(*, share: float, speedup: float | str, status: str) -> dict[str, Any]:
    denominator = 1.0 - share
    if speedup != "unbounded":
        denominator += share / float(speedup)
    return {
        "schema_version": 1,
        "experiment_id": "readiness-fixture",
        "target": {"runner": "ubuntu-24.04-arm", "architecture": "aarch64"},
        "mechanism_unit": {
            "status": "passed",
            "command": "python3 -m unittest tests.test_evidence_readiness",
            "affected_runtime_share": share,
            "component_speedup_ceiling": speedup,
            "system_throughput_gain_ceiling": 1.0 / denominator - 1.0,
        },
        "synthetic_replay": {
            "status": "passed",
            "command": "python3 experiments/evidence_readiness.py --self-test",
            "control_cells": 1,
            "candidate_cells": 1,
            "byte_stable": True,
        },
        "native_preflight": {
            "status": status,
            "command": "gh workflow run bounded-native-preflight.yml",
            "runner": "ubuntu-24.04-arm",
            "architecture": "aarch64",
            "control_cells": 1,
            "candidate_cells": 1,
        },
        "value_contract": {
            "minimum_product_result": {
                "metric": "throughput",
                "relative_delta": 0.03,
            },
            "claim_unlocked": "one bounded native service claim",
            "alternate_values": [],
        },
        "budget": {
            "maximum_runtime_minutes": 90,
            "maximum_storage_bytes": 536870912,
        },
    }


def run_fixture_suite(policy_path: Path) -> dict[str, Any]:
    policy = load_json_object(policy_path)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "raw/requests").mkdir(parents=True)
        (root / "slots.json").write_text(
            json.dumps([{"id": 0, "is_processing": False}]), encoding="utf-8"
        )
        (root / "timing.json").write_text(
            json.dumps({"http_ms": 10.0, "encode_ms": 4.0}), encoding="utf-8"
        )
        (root / "cells.json").write_text(
            json.dumps(
                {
                    "cells": [
                        {
                            "cell_id": "control",
                            "return_code": 0,
                            "probe": {"status": "ok"},
                            "raw_requests": ["raw/requests/control.json"],
                            "inventory_verified": True,
                        },
                        {
                            "cell_id": "failed",
                            "return_code": 1,
                            "failure": "probe rejected timing schema",
                        },
                        {"cell_id": "partial", "return_code": 0},
                    ]
                }
            ),
            encoding="utf-8",
        )
        for name in ("control", "candidate"):
            (root / f"raw/requests/{name}.json").write_text(
                json.dumps({"request": {"id": name}, "response": {"ok": True}}),
                encoding="utf-8",
            )
        inventory_path = root / "file-inventory-sha256.txt"
        inventory_path.write_text(
            "".join(
                f"{sha256_file(root / path)}  {path}\n"
                for path in (
                    "raw/requests/candidate.json",
                    "raw/requests/control.json",
                )
            ),
            encoding="utf-8",
        )

        def build_summary() -> dict[str, Any]:
            inventory = validate_sha256_inventory(root, inventory_path)
            cell_document = load_json_object(root / "cells.json")
            return {
                "slots": load_slots_array(root / "slots.json"),
                "timing": validate_timing_record(
                    load_json_object(root / "timing.json"),
                    ("http_ms", "encode_ms"),
                ),
                "cells": classify_cells(
                    cell_document["cells"], ("control", "failed", "partial")
                ),
                "raw": validate_raw_request_layout(
                    root,
                    (
                        "raw/requests/control.json",
                        "raw/requests/candidate.json",
                    ),
                    inventory,
                    ("request", "response"),
                ),
                "inventory": {
                    key: value for key, value in inventory.items() if key != "entries"
                },
            }

        summary, replay = verify_byte_stable_replay(build_summary)

    planned = _fixture_plan(share=0.08, speedup=2.0, status="planned")
    passed = _fixture_plan(share=0.08, speedup=2.0, status="passed")
    below_floor = _fixture_plan(
        share=0.01, speedup="unbounded", status="passed"
    )
    return {
        "schema_version": 1,
        "experiment_id": "evidence-readiness-gate-v1",
        "status": "valid_local_artifact_shape_and_readiness_gate",
        "policy_sha256": sha256_file(policy_path),
        "artifact_shape_fixture": summary,
        "timing_rejections": {
            "missing": _capture_timing_rejection({"http_ms": 1.0}),
            "null": _capture_timing_rejection(
                {"http_ms": 1.0, "encode_ms": None}
            ),
            "unsupported": _capture_timing_rejection(
                {"http_ms": 1.0, "encode_ms": "4.0"}
            ),
            "nonfinite": _capture_timing_rejection(
                {"http_ms": 1.0, "encode_ms": float("nan")}
            ),
        },
        "independent_replay": replay,
        "readiness_decisions": {
            "planned": evaluate_readiness(planned, policy),
            "passed": evaluate_readiness(passed, policy),
            "below_floor": evaluate_readiness(below_floor, policy),
        },
        "claim_boundary": (
            "This local fixture validates parser shapes, fail-closed cell accounting, "
            "inventory binding, deterministic replay, and readiness decisions only. "
            "It is not native performance evidence."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("experiments/evidence_readiness_policy.json"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test and args.output is None:
        parser.error("--self-test or --output is required")
    result = run_fixture_suite(args.policy)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical_json_bytes(result))
    print(
        json.dumps(
            {
                "status": result["status"],
                "summary_sha256": result["independent_replay"]["summary_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
