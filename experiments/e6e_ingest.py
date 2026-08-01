#!/usr/bin/env python3
"""Validate the frozen upstream-equivalent native Arm CPU CI evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

try:
    from experiments.e6b_ingest import (
        load_object,
        read_exit_status,
        sha256_file,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e6b_ingest import (  # type: ignore[no-redef]
        load_object,
        read_exit_status,
        sha256_file,
    )


def validate_contract(contract: dict[str, Any]) -> None:
    test = contract.get("test", {})
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E6e"
        or contract.get("selection", {}).get("weighted_score_used") is not False
        or contract.get("build", {}).get("target") != "all"
        or test.get("ctest_label") != "main"
        or test.get("minimum_tests") != 47
        or test.get("maximum_failures") != 0
        or test.get("maximum_errors") != 0
        or test.get("maximum_skipped") != 0
    ):
        raise ValueError("invalid E6e contract")


def validate_provenance(
    evidence_dir: Path,
    contract: dict[str, Any],
    contract_path: Path,
    patch_root: Path,
) -> dict[str, Any]:
    provenance = load_object(evidence_dir / "provenance.json")
    upstream = contract["upstream"]
    if (
        provenance.get("schema_version") != 1
        or provenance.get("experiment_id") != "E6e"
        or provenance.get("llama_cpp_commit") != upstream["commit"]
        or provenance.get("llama_cpp_tag") != upstream["tag"]
        or provenance.get("contract_sha256") != sha256_file(contract_path)
    ):
        raise ValueError("E6e provenance differs from the frozen contract")
    expected_patches = {}
    for patch in contract["patches"]:
        path = patch_root / patch["path"]
        digest = sha256_file(path)
        if digest != patch["sha256"]:
            raise ValueError(f"patch input differs: {path}")
        expected_patches[patch["name"]] = digest
    if provenance.get("patch_sha256") != expected_patches:
        raise ValueError("E6e patch provenance differs from the frozen inputs")
    return provenance


def parse_ctest_junit(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag.endswith("testsuite") else list(root)
    cases = [
        case
        for suite in suites
        for case in suite
        if case.tag.endswith("testcase")
    ]
    passed = []
    failures = 0
    errors = 0
    skipped = 0
    for case in cases:
        children = {child.tag.rsplit("}", 1)[-1] for child in case}
        failures += int("failure" in children)
        errors += int("error" in children)
        skipped += int("skipped" in children)
        if not children.intersection({"failure", "error", "skipped"}):
            passed.append(case.attrib.get("name", ""))
    return {
        "total": len(cases),
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "passed": len(passed),
        "passed_test_names": sorted(passed),
    }


def validate_build(evidence_dir: Path) -> dict[str, Any]:
    cache = (evidence_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    compiler = (evidence_dir / "compiler.txt").read_text(
        encoding="utf-8", errors="replace"
    )
    required_cache = (
        "CMAKE_BUILD_TYPE:STRING=Release",
        "CMAKE_C_COMPILER:FILEPATH=/usr/bin/gcc-14",
        "CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/g++-14",
        "GGML_CPU_KLEIDIAI:BOOL=ON",
        "GGML_NATIVE:BOOL=ON",
        "GGML_RPC:BOOL=ON",
        "LLAMA_BUILD_TESTS:BOOL=ON",
        "LLAMA_FATAL_WARNINGS:BOOL=ON",
    )
    return {
        "configure_exit_status": read_exit_status(
            evidence_dir / "configure-exit.txt"
        ),
        "build_exit_status": read_exit_status(evidence_dir / "build-exit.txt"),
        "configuration_bound": all(value in cache for value in required_cache),
        "compiler_bound": "g++-14" in compiler and "gcc-14" in compiler,
    }


def evaluate(
    build: dict[str, Any], tests: dict[str, Any], contract: dict[str, Any]
) -> dict[str, bool]:
    requirements = contract["test"]
    passed_names = set(tests["passed_test_names"])
    return {
        "configuration_bound": build["configuration_bound"],
        "compiler_bound": build["compiler_bound"],
        "configure_passed": build["configure_exit_status"] == 0,
        "full_build_passed": build["build_exit_status"] == 0,
        "ctest_passed": tests["exit_status"] == 0,
        "minimum_main_tests_passed": tests["total"]
        >= requirements["minimum_tests"],
        "zero_failures": tests["failures"] <= requirements["maximum_failures"],
        "zero_errors": tests["errors"] <= requirements["maximum_errors"],
        "zero_skipped": tests["skipped"] <= requirements["maximum_skipped"],
        "required_tests_passed": set(requirements["required_tests"])
        <= passed_names,
    }


def build_summary(
    evidence_dir: Path,
    contract: dict[str, Any],
    contract_path: Path,
    patch_root: Path,
) -> dict[str, Any]:
    validate_contract(contract)
    uname = (evidence_dir / "uname.txt").read_text(encoding="utf-8")
    lscpu = (evidence_dir / "lscpu.txt").read_text(encoding="utf-8")
    if "aarch64" not in uname or "Architecture:" not in lscpu or "aarch64" not in lscpu:
        raise ValueError("E6e evidence is not from native aarch64")
    provenance = validate_provenance(
        evidence_dir, contract, contract_path, patch_root
    )
    build = validate_build(evidence_dir)
    tests = parse_ctest_junit(evidence_dir / "ctest.xml")
    tests["exit_status"] = read_exit_status(evidence_dir / "ctest-exit.txt")
    criteria = evaluate(build, tests, contract)
    accepted = all(criteria.values())
    return {
        "schema_version": 1,
        "experiment_id": "E6e",
        "status": (
            "valid_upstream_arm_cpu_lane"
            if accepted
            else "valid_upstream_arm_cpu_lane_rejected"
        ),
        "source": provenance,
        "host": {"architecture": "aarch64", "native": True},
        "patches": contract["patches"],
        "build": build,
        "tests": tests,
        "validation": {
            "criteria": criteria,
            "upstream_arm_cpu_lane_claim_allowed": accepted,
            "weighted_score_used": False,
            "claim_scope": contract["selection"]["claim_scope"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--patch-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    summary = build_summary(
        arguments.evidence_dir,
        load_object(arguments.contract),
        arguments.contract,
        arguments.patch_root,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
