#!/usr/bin/env python3
"""Validate the local PR-ready llama.cpp patch series on native Arm."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from experiments.e1_ingest import parse_lscpu
    from experiments.e5b_ingest import load_object, sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e1_ingest import parse_lscpu  # type: ignore[no-redef]
    from e5b_ingest import load_object, sha256_file  # type: ignore[no-redef]


def read_status(path: Path) -> int:
    return int(path.read_text(encoding="utf-8").strip())


def validate_contract(contract: dict[str, Any]) -> None:
    if (
        contract.get("schema_version") != 1
        or contract.get("contract_revision") != 2
        or contract.get("experiment_id") != "E9d"
        or len(contract.get("mail_series", {}).get("patches", [])) != 3
        or contract.get("acceptance", {}).get("all_required") is not True
        or contract.get("claim_boundary", {}).get("upstream_pr_opened") is not False
    ):
        raise ValueError("invalid E9d contract")


def validate_inputs(
    evidence_dir: Path,
    contract: dict[str, Any],
    contract_path: Path,
    root: Path,
) -> dict[str, Any]:
    if load_object(evidence_dir / "contract.json") != contract:
        raise ValueError("artifact E9d contract differs from frozen input")
    provenance = load_object(evidence_dir / "provenance.json")
    upstream = contract["upstream"]
    if (
        provenance.get("schema_version") != 1
        or provenance.get("experiment_id") != "E9d"
        or provenance.get("contract_sha256") != sha256_file(contract_path)
        or provenance.get("llama_cpp_commit") != upstream["commit"]
        or provenance.get("llama_cpp_tag") != upstream["tag"]
    ):
        raise ValueError("E9d provenance differs from frozen inputs")

    expected_hashes: dict[str, str] = {}
    entries = [contract["mail_series"]["cover_letter"]]
    entries.extend(contract["mail_series"]["patches"])
    for entry in entries:
        path = root / entry["path"]
        digest = sha256_file(path)
        if digest != entry["sha256"]:
            raise ValueError(f"E9d mail input differs: {path}")
        artifact = evidence_dir / "mail" / path.name
        if sha256_file(artifact) != digest:
            raise ValueError(f"E9d artifact mail input differs: {artifact}")
        expected_hashes[path.name] = digest
    if provenance.get("mail_sha256") != expected_hashes:
        raise ValueError("E9d mail provenance differs")
    return provenance


def validate_series(evidence_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    series_dir = evidence_dir / "series"
    observed = json.loads((series_dir / "commits.json").read_text(encoding="utf-8"))
    if not isinstance(observed, list) or not all(
        isinstance(entry, dict) for entry in observed
    ):
        raise ValueError("E9d applied commits must be a JSON array of objects")
    expected_patches = contract["mail_series"]["patches"]
    expected_subjects = [entry["subject"] for entry in expected_patches]
    if (
        (series_dir / "base.txt").read_text().strip()
        != contract["upstream"]["commit"]
        or [entry.get("subject") for entry in observed] != expected_subjects
        or len(observed) != 3
        or any(entry.get("signed_off_by") is not True for entry in observed)
        or any(not isinstance(entry.get("commit"), str) for entry in observed)
    ):
        raise ValueError("E9d applied commit series differs")
    changed = (series_dir / "patched-files.txt").read_text().splitlines()
    if changed != contract["mail_series"]["expected_changed_files"]:
        raise ValueError("E9d applied file set differs")
    aggregate = sha256_file(series_dir / "applied-series.patch")
    if aggregate != contract["mail_series"]["aggregate_diff_sha256"]:
        raise ValueError("E9d applied series differs from retained source diff")
    cover = (evidence_dir / "mail" / "0000-cover-letter.patch").read_text()
    if (
        f"base-commit: {contract['upstream']['commit']}" not in cover
        or "*** SUBJECT HERE ***" in cover
        or "*** BLURB HERE ***" in cover
    ):
        raise ValueError("E9d cover letter is incomplete or unbound")
    return {
        "base_commit": contract["upstream"]["commit"],
        "tip_commit": (series_dir / "tip.txt").read_text().strip(),
        "commits": observed,
        "changed_files": changed,
        "aggregate_diff_sha256": aggregate,
        "cover_letter_complete": True,
        "git_am_three_way_passed": True,
    }


def compiler_lane(
    evidence_dir: Path, contract: dict[str, Any], name: str
) -> dict[str, Any]:
    lane = evidence_dir / "toolchains" / name
    compiler = (lane / "compiler.txt").read_text(errors="replace")
    native = lane / "native"
    feature = lane / "feature"
    native_cache = (native / "CMakeCache.txt").read_text(errors="replace")
    feature_cache = (feature / "CMakeCache.txt").read_text(errors="replace")
    expected = contract["toolchains"][name]
    compiler_bound = all(token in compiler for token in expected["version_tokens"])
    native_configuration_bound = all(
        value in native_cache
        for value in (
            expected["c_cache_entry"],
            expected["cxx_cache_entry"],
            "BUILD_SHARED_LIBS:BOOL=OFF",
            "GGML_CPU_KLEIDIAI:BOOL=OFF",
            "GGML_NATIVE:BOOL=ON",
            "LLAMA_BUILD_TESTS:BOOL=ON",
        )
    )
    feature_configuration_bound = all(
        value in feature_cache
        for value in (
            expected["c_cache_entry"],
            expected["cxx_cache_entry"],
            "GGML_CPU_ARM_ARCH:STRING=armv8.6-a+sve2+nosve",
            "GGML_CPU_KLEIDIAI:BOOL=ON",
            "GGML_NATIVE:BOOL=OFF",
        )
    )
    quantize_log = (native / "quantize.stdout.log").read_text(errors="replace")
    reasoning_log = (native / "reasoning.stdout.log").read_text(errors="replace")
    feature_build = (feature / "build.log").read_text(errors="replace")
    return {
        "compiler": compiler.strip(),
        "compiler_bound": compiler_bound,
        "native_configuration_bound": native_configuration_bound,
        "native_build_exit_status": read_status(native / "build-exit.txt"),
        "quantize_exit_status": read_status(native / "quantize-exit.txt"),
        "quantize_output_present": bool(quantize_log.strip()),
        "reasoning_exit_status": read_status(native / "reasoning-exit.txt"),
        "reasoning_suite_passed": "OK (13 tests passed)" in reasoning_log,
        "feature_configuration_bound": feature_configuration_bound,
        "feature_build_exit_status": read_status(feature / "build-exit.txt"),
        "invalid_sve_source_absent": "sve_dotprod_asm.S" not in feature_build,
    }


def sanitizer_lane(evidence_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    lane = evidence_dir / "sanitizers"
    cache = (lane / "CMakeCache.txt").read_text(errors="replace")
    compiler = (lane / "compiler.txt").read_text(errors="replace")
    quantize_stdout = (lane / "quantize.stdout.log").read_text(errors="replace")
    quantize_stderr = (lane / "quantize.stderr.log").read_text(errors="replace")
    reasoning_stdout = (lane / "reasoning.stdout.log").read_text(errors="replace")
    reasoning_stderr = (lane / "reasoning.stderr.log").read_text(errors="replace")
    combined = "\n".join(
        (quantize_stdout, quantize_stderr, reasoning_stdout, reasoning_stderr)
    )
    config_values = tuple(contract["sanitizers"]["required_cache_entries"])
    return {
        "compiler": compiler.strip(),
        "compiler_bound": all(
            token in compiler for token in contract["sanitizers"]["version_tokens"]
        ),
        "configuration_bound": all(value in cache for value in config_values),
        "build_exit_status": read_status(lane / "build-exit.txt"),
        "quantize_exit_status": read_status(lane / "quantize-exit.txt"),
        "reasoning_exit_status": read_status(lane / "reasoning-exit.txt"),
        "reasoning_suite_passed": "OK (13 tests passed)" in reasoning_stdout,
        "address_sanitizer_clean": "ERROR: AddressSanitizer" not in combined,
        "undefined_sanitizer_clean": "runtime error:" not in combined,
        "leak_sanitizer_clean": "ERROR: LeakSanitizer" not in combined,
        "function_type_diagnostic": (
            "call to function ggml_vec_dot_f32 through pointer to incorrect "
            "function type" in combined
        ),
    }


def diagnostic_lane(path: Path, *, require_reasoning: bool) -> dict[str, Any]:
    quantize_stdout = (path / "quantize.stdout.log").read_text(errors="replace")
    quantize_stderr = (path / "quantize.stderr.log").read_text(errors="replace")
    reasoning_stdout = ""
    reasoning_stderr = ""
    reasoning_status: int | None = None
    if require_reasoning:
        reasoning_stdout = (path / "reasoning.stdout.log").read_text(
            errors="replace"
        )
        reasoning_stderr = (path / "reasoning.stderr.log").read_text(
            errors="replace"
        )
        reasoning_status = read_status(path / "reasoning-exit.txt")
    combined = "\n".join(
        (quantize_stdout, quantize_stderr, reasoning_stdout, reasoning_stderr)
    )
    return {
        "build_exit_status": read_status(path / "build-exit.txt"),
        "quantize_exit_status": read_status(path / "quantize-exit.txt"),
        "reasoning_exit_status": reasoning_status,
        "reasoning_suite_passed": (
            "OK (13 tests passed)" in reasoning_stdout
            if require_reasoning
            else None
        ),
        "address_sanitizer_clean": "ERROR: AddressSanitizer" not in combined,
        "undefined_sanitizer_clean": "runtime error:" not in combined,
        "leak_sanitizer_clean": "ERROR: LeakSanitizer" not in combined,
        "function_type_diagnostic": (
            "call to function ggml_vec_dot_f32 through pointer to incorrect "
            "function type" in combined
        ),
    }


def sanitizer_diagnostics(
    evidence_dir: Path,
    contract: dict[str, Any],
    strict: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any]:
    baseline = diagnostic_lane(
        evidence_dir / "baseline-sanitizers", require_reasoning=False
    )
    supplemental = diagnostic_lane(
        evidence_dir / "supplemental-sanitizers", require_reasoning=True
    )
    token = contract["diagnostic_controls"]["strict_pristine_base"][
        "diagnostic_token"
    ]
    baseline_stderr = (
        evidence_dir / "baseline-sanitizers" / "quantize.stderr.log"
    ).read_text(errors="replace")
    inherited = (
        strict["quantize_exit_status"] != 0
        and strict["undefined_sanitizer_clean"] is False
        and strict["function_type_diagnostic"] is True
        and baseline["quantize_exit_status"] != 0
        and baseline["undefined_sanitizer_clean"] is False
        and token in baseline_stderr
        and "tests/test-quantize-fns.cpp" not in changed_files
    )
    supplemental_passed = (
        supplemental["build_exit_status"] == 0
        and supplemental["quantize_exit_status"] == 0
        and supplemental["reasoning_exit_status"] == 0
        and supplemental["reasoning_suite_passed"] is True
        and supplemental["address_sanitizer_clean"]
        and supplemental["undefined_sanitizer_clean"]
        and supplemental["leak_sanitizer_clean"]
    )
    return {
        "strict_pristine_base": baseline,
        "supplemental_scoped_patch": {
            **supplemental,
            "excluded_ubsan_check": "function",
            "passed": supplemental_passed,
            "acceptance_gate": False,
        },
        "strict_failure_attribution": (
            "inherited_pristine_b10216_test_function_type_ub"
            if inherited
            else "not_attributed_to_pristine_control"
        ),
        "strict_gate_unchanged": True,
    }


def evaluate(
    series: dict[str, Any],
    compilers: dict[str, dict[str, Any]],
    sanitizers: dict[str, Any],
) -> dict[str, bool]:
    criteria = {
        "mail_series_applied": series["git_am_three_way_passed"],
        "cover_letter_complete": series["cover_letter_complete"],
        "aggregate_diff_exact": bool(series["aggregate_diff_sha256"]),
    }
    for name, lane in compilers.items():
        criteria[f"{name}_compiler_bound"] = lane["compiler_bound"]
        criteria[f"{name}_native_configuration_bound"] = lane[
            "native_configuration_bound"
        ]
        criteria[f"{name}_native_build_passed"] = (
            lane["native_build_exit_status"] == 0
        )
        criteria[f"{name}_quantize_passed"] = (
            lane["quantize_exit_status"] == 0
            and lane["quantize_output_present"]
        )
        criteria[f"{name}_reasoning_passed"] = (
            lane["reasoning_exit_status"] == 0
            and lane["reasoning_suite_passed"]
        )
        criteria[f"{name}_feature_stress_passed"] = (
            lane["feature_configuration_bound"]
            and lane["feature_build_exit_status"] == 0
            and lane["invalid_sve_source_absent"]
        )
    criteria.update(
        {
            "sanitizer_compiler_bound": sanitizers["compiler_bound"],
            "sanitizer_configuration_bound": sanitizers["configuration_bound"],
            "sanitizer_build_passed": sanitizers["build_exit_status"] == 0,
            "sanitizer_quantize_passed": sanitizers["quantize_exit_status"] == 0,
            "sanitizer_reasoning_passed": (
                sanitizers["reasoning_exit_status"] == 0
                and sanitizers["reasoning_suite_passed"]
            ),
            "address_sanitizer_clean": sanitizers["address_sanitizer_clean"],
            "undefined_sanitizer_clean": sanitizers[
                "undefined_sanitizer_clean"
            ],
            "leak_sanitizer_clean": sanitizers["leak_sanitizer_clean"],
        }
    )
    return criteria


def build_manifest(
    evidence_dir: Path, contract_path: Path, root: Path
) -> dict[str, Any]:
    contract = load_object(contract_path)
    validate_contract(contract)
    provenance = validate_inputs(evidence_dir, contract, contract_path, root)
    series = validate_series(evidence_dir, contract)
    platform = {
        **parse_lscpu((evidence_dir / "lscpu.txt").read_text()),
        "uname": (evidence_dir / "uname.txt").read_text().strip(),
    }
    if platform["architecture"] != contract["host"]["architecture"]:
        raise ValueError("E9d did not run on native Arm64")
    compilers = {
        name: compiler_lane(evidence_dir, contract, name)
        for name in ("gcc", "clang")
    }
    sanitizers = sanitizer_lane(evidence_dir, contract)
    diagnostics = sanitizer_diagnostics(
        evidence_dir, contract, sanitizers, series["changed_files"]
    )
    criteria = evaluate(series, compilers, sanitizers)
    status = (
        "valid_pr_ready_patch_series"
        if all(criteria.values())
        else "invalid_pr_ready_patch_series"
    )
    run_id = str(provenance["github_run_id"])
    return {
        "schema_version": 1,
        "experiment_id": "E9d",
        "status": status,
        "source": {
            "github_run_url": (
                f"https://github.com/Arshgill01/Arm/actions/runs/{run_id}"
            ),
            "artifact_name": (
                f"e9d-pr-ready-patches-{run_id}-"
                f"{provenance['github_run_attempt']}"
            ),
            "artifact_retention_days": 90,
        },
        "provenance": provenance,
        "platform": platform,
        "series": series,
        "compiler_lanes": compilers,
        "sanitizers": sanitizers,
        "sanitizer_diagnostics": diagnostics,
        "validation": {
            **criteria,
            "all_acceptance_criteria_passed": all(criteria.values()),
            "upstream_pr_opened": False,
            "performance_claim_added": False,
            "claim_scope": contract["claim_boundary"]["scope"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_manifest(args.evidence_dir, args.contract, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
