#!/usr/bin/env python3
"""Validate the frozen current-upstream Arm patch-series rebase evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e6b_ingest import (
        assembly_summary,
        load_object,
        paired_effect,
        parse_perf,
        read_exit_status,
        sha256_file,
    )
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e6b_ingest import (  # type: ignore[no-redef]
        assembly_summary,
        load_object,
        paired_effect,
        parse_perf,
        read_exit_status,
        sha256_file,
    )


def validate_contract(contract: dict[str, Any]) -> None:
    if (
        contract.get("schema_version") != 1
        or contract.get("experiment_id") != "E6d"
        or contract.get("selection", {}).get("weighted_score_used") is not False
    ):
        raise ValueError("invalid E6d contract")
    rounds = contract.get("quantizer", {}).get("rounds")
    if rounds != [
        ["baseline", "patched"],
        ["patched", "baseline"],
        ["baseline", "patched"],
        ["patched", "baseline"],
    ]:
        raise ValueError("E6d contract must use the frozen balanced order")


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
        or provenance.get("experiment_id") != "E6d"
        or provenance.get("llama_cpp_commit") != upstream["commit"]
        or provenance.get("llama_cpp_tag") != upstream["tag"]
        or provenance.get("contract_sha256") != sha256_file(contract_path)
    ):
        raise ValueError("E6d provenance differs from the frozen contract")
    observed_patches = provenance.get("patch_sha256")
    expected_patches = {}
    for patch in contract["patches"]:
        path = patch_root / patch["path"]
        digest = sha256_file(path)
        if digest != patch["sha256"]:
            raise ValueError(f"patch input differs: {path}")
        expected_patches[patch["name"]] = digest
    if observed_patches != expected_patches:
        raise ValueError("E6d patch provenance differs from the frozen inputs")
    return provenance


def validate_feature_reproduction(evidence_dir: Path) -> dict[str, Any]:
    directory = evidence_dir / "feature"
    baseline_status = read_exit_status(directory / "baseline-build-exit.txt")
    patched_status = read_exit_status(directory / "patched-build-exit.txt")
    baseline_configure = (directory / "baseline-configure.log").read_text(
        encoding="utf-8"
    )
    patched_configure = (directory / "patched-configure.log").read_text(
        encoding="utf-8"
    )
    baseline_build = (directory / "baseline-build.log").read_text(
        encoding="utf-8", errors="replace"
    )
    patched_build = (directory / "patched-build.log").read_text(
        encoding="utf-8", errors="replace"
    )
    baseline_cache = (directory / "baseline-CMakeCache.txt").read_text(
        encoding="utf-8"
    )
    patched_cache = (directory / "patched-CMakeCache.txt").read_text(
        encoding="utf-8"
    )
    return {
        "baseline_exit_status": baseline_status,
        "patched_exit_status": patched_status,
        "validated_sve_disabled": (
            "Performing Test HAVE_SVE - Failed" in baseline_configure
            and "Performing Test HAVE_SVE - Failed" in patched_configure
        ),
        "configuration_bound": all(
            value in cache
            for cache in (baseline_cache, patched_cache)
            for value in (
                "GGML_CPU_ARM_ARCH:STRING=armv8.6-a+sve2+nosve",
                "GGML_CPU_KLEIDIAI:BOOL=ON",
                "GGML_NATIVE:BOOL=OFF",
            )
        ),
        "baseline_invalid_sve_source_observed": (
            "sve_dotprod_asm.S" in baseline_build
            and "selected processor does not support" in baseline_build
        ),
        "patched_invalid_sve_source_absent": "sve_dotprod_asm.S"
        not in patched_build,
    }


def validate_targeted_tests(evidence_dir: Path) -> dict[str, Any]:
    variants: dict[str, Any] = {}
    for variant in ("baseline", "patched"):
        directory = evidence_dir / "variants" / variant
        cache = (directory / "CMakeCache.txt").read_text(encoding="utf-8")
        variants[variant] = {
            "build_exit_status": read_exit_status(directory / "build-exit.txt"),
            "quantize_exit_status": read_exit_status(
                directory / "quantize-test-exit.txt"
            ),
            "reasoning_exit_status": read_exit_status(
                directory / "reasoning-test-exit.txt"
            ),
            "assembly": assembly_summary(directory / "assembly.txt"),
            "configuration_bound": all(
                value in cache
                for value in (
                    "BUILD_SHARED_LIBS:BOOL=OFF",
                    "GGML_CPU_KLEIDIAI:BOOL=OFF",
                    "GGML_NATIVE:BOOL=ON",
                    "LLAMA_BUILD_TESTS:BOOL=ON",
                )
            ),
        }
    baseline_reasoning = (
        evidence_dir / "variants/baseline/reasoning-test.stderr.log"
    ).read_text(encoding="utf-8", errors="replace")
    patched_reasoning = (
        evidence_dir / "variants/patched/reasoning-test.stdout.log"
    ).read_text(encoding="utf-8", errors="replace")
    variants["baseline"]["reasoning_regression_reproduced"] = (
        "common_reasoning_budget_get_state(sampler) == REASONING_BUDGET_FORCING"
        in baseline_reasoning
    )
    variants["patched"]["reasoning_complete_suite_passed"] = (
        "OK (13 tests passed)" in patched_reasoning
    )
    return variants


def direct_benchmark(
    evidence_dir: Path, contract: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    sizes = contract["quantizer"]["sizes"]
    rounds = contract["quantizer"]["rounds"]
    values: dict[str, dict[int, dict[int, list[float]]]] = {
        variant: {size: {} for size in sizes}
        for variant in ("baseline", "patched")
    }
    for round_number, order in enumerate(rounds, start=1):
        for position, variant in enumerate(order, start=1):
            path = (
                evidence_dir
                / "rounds"
                / f"round-{round_number}-position-{position}-{variant}"
                / "perf.log"
            )
            parsed = parse_perf(path, sizes)
            for size in sizes:
                values[variant][size][round_number] = [parsed[size]]
    return {
        str(size): paired_effect(
            values["baseline"][size], values["patched"][size], "higher"
        )
        for size in sizes
    }


def evaluate(
    feature: dict[str, Any],
    tests: dict[str, Any],
    direct: dict[str, dict[str, Any]],
    acceptance: dict[str, Any],
) -> dict[str, bool]:
    baseline_assembly = tests["baseline"]["assembly"]
    patched_assembly = tests["patched"]["assembly"]
    criteria = {
        "unpatched_feature_failure_reproduced": (
            feature["baseline_exit_status"] != 0
            and feature["validated_sve_disabled"]
            and feature["configuration_bound"]
            and feature["baseline_invalid_sve_source_observed"]
        ),
        "patched_feature_build_passed": (
            feature["patched_exit_status"] == 0
            and feature["patched_invalid_sve_source_absent"]
        ),
        "baseline_targets_built": (
            tests["baseline"]["build_exit_status"] == 0
            and tests["baseline"]["configuration_bound"]
        ),
        "patched_targets_built": (
            tests["patched"]["build_exit_status"] == 0
            and tests["patched"]["configuration_bound"]
        ),
        "baseline_quantizer_passed": tests["baseline"]["quantize_exit_status"]
        == 0,
        "patched_quantizer_passed": tests["patched"]["quantize_exit_status"]
        == 0,
        "reasoning_regression_reproduced": (
            tests["baseline"]["reasoning_exit_status"] != 0
            and tests["baseline"]["reasoning_regression_reproduced"]
        ),
        "reasoning_patch_passed": (
            tests["patched"]["reasoning_exit_status"] == 0
            and tests["patched"]["reasoning_complete_suite_passed"]
        ),
        "baseline_scalar_store_mechanism": baseline_assembly["byte_stores"]
        >= acceptance["minimum_baseline_byte_stores"],
        "patched_vector_store_mechanism": (
            patched_assembly["byte_stores"]
            <= acceptance["maximum_patched_byte_stores"]
            and patched_assembly["vector_narrows"]
            >= acceptance["minimum_patched_vector_narrows"]
            and patched_assembly["vector_stores"]
            >= acceptance["minimum_patched_vector_stores"]
        ),
    }
    for size, result in direct.items():
        criteria[f"direct_ratio_{size}"] = (
            result["median_improvement_ratio"]
            >= acceptance["minimum_median_improvement_ratio_by_size"][size]
        )
        criteria[f"direct_rounds_{size}"] = (
            result["improved_rounds"]
            >= acceptance["minimum_improved_rounds_by_size"][size]
        )
    return criteria


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
        raise ValueError("E6d performance evidence is not from native aarch64")
    provenance = validate_provenance(
        evidence_dir, contract, contract_path, patch_root
    )
    feature = validate_feature_reproduction(evidence_dir)
    tests = validate_targeted_tests(evidence_dir)
    direct = direct_benchmark(evidence_dir, contract)
    criteria = evaluate(feature, tests, direct, contract["acceptance"])
    accepted = all(criteria.values())
    return {
        "schema_version": 1,
        "experiment_id": "E6d",
        "status": (
            "valid_current_upstream_rebase"
            if accepted
            else "valid_current_upstream_rebase_rejected"
        ),
        "source": provenance,
        "host": {"architecture": "aarch64", "native": True},
        "patches": contract["patches"],
        "feature_reproduction": feature,
        "targeted_tests": tests,
        "direct_benchmark": direct,
        "validation": {
            "criteria": criteria,
            "current_upstream_claim_allowed": accepted,
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
