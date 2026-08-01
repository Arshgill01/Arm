#!/usr/bin/env python3
"""Verify the compact Pareto64 submission package from a clean checkout."""

from __future__ import annotations

import hashlib
import json
import sys
from html.parser import HTMLParser
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
build_plan = import_module("pareto64.planner").build_plan
resolve_batch_profile = import_module("pareto64.cli").resolve_batch_profile
build_service_plan = import_module("pareto64.service_planner").build_service_plan
validate_runtime_upgrade_service = import_module(
    "pareto64.runtime"
).validate_runtime_upgrade_service


EXPECTED_HASHES = {
    "results/manifests/e3f-30656151957.json": (
        "54adb3d4317e7a33c08c3bc59a4d534c5b5c6952a1dcc9a01b93e87a445aff9c"
    ),
    "results/manifests/e5b-30659829983.json": (
        "aa529b16094ab398bf1d7c6aa698b452eeea6217f8016c280a5f2b6f947bf66c"
    ),
    "results/manifests/e5c-30662037235.json": (
        "27a426dd9ed0ed8e4b9ef513a5ced7418f7a722b91e94ca1bc10f8f76d84bfa7"
    ),
    "results/manifests/e5d-30664666945.json": (
        "a844e58ea3f89e8fd9d9e8697ad6c680865a6719d2f6b34298af0d56be7d76e5"
    ),
    "results/manifests/e5e-30667019678.json": (
        "6312dc789eefad276b20d3204d9a5144251d49e3f04b9a767d9125dceaa5ed2c"
    ),
    "results/manifests/e5f-30669700602.json": (
        "396222dd2ec0d66c0985392b0c2b65e4fa1b8a3100f57c4d1d30d50a41f92d4b"
    ),
    "results/manifests/e5g-30671733556.json": (
        "374e5af3d8af8c022d76ff51f614c50e1dd25f8948fcc727fe3f983afad984b6"
    ),
    "results/manifests/e5h-30672633366.json": (
        "e048f3e25d513430b49fd2ee0a140e8a0f82fe31d79b5fb0aafb36b470190faa"
    ),
    "configs/service-throughput.json": (
        "17f80ba9734731f04a65b4c29e693977234c308c9065c95668e32254fdcc7ebd"
    ),
    "configs/service-memory.json": (
        "7f5239f0991f80c130599d4630ebbfdec51bed2316f62b4a90c7b49dcbd135b4"
    ),
    "results/plans/e5h-service-throughput.json": (
        "6e00839f8add70d9097263b67fad686984d8ad459adb7c12b0e229802d93e4b4"
    ),
    "results/plans/e5h-service-memory.json": (
        "15a6fac8710338e545afc1ab828ca532535c58c6ae4c682070cb9def2a97a27d"
    ),
    "results/manifests/e5i-30674023380.json": (
        "ca41dd4c8ce7eaec196ac4d6a1320f689755ae4fb9e5d13bb4061f3c24a46ba2"
    ),
    "results/manifests/e5j-30677332825.json": (
        "747b6795d42be691c07cf5aac38237095477d06149e787cc313ec2b9558c4ff7"
    ),
    "results/manifests/e6b-30640282768.json": (
        "e870ad9cf7b7d1f89f0fa745383f555d54f62b3caf2fc635cbcb76ca4ef7e210"
    ),
    "results/manifests/e6d-30675654688.json": (
        "32e01c0baf21de4679ace516a1ef61f7520dbbbc641d218aa454380e0c9767fa"
    ),
    "results/manifests/e6e-30676413765.json": (
        "63c0e450d967208e3eb81d21571c73354e8520940933434914920db5d63c27f1"
    ),
    "results/manifests/e6f-30678703184.json": (
        "da95b831a0cccf3b16dd45e93e11855a6e0322c5aa163d145c24243b42470ace"
    ),
    "results/manifests/e6g-30679814341.json": (
        "13496b5e62e50bc3e617e6a80631c87ac6bc29015ea83499cb2ff885ec404ac9"
    ),
    "configs/runtime-b10216-selected-service.json": (
        "9d4750364878e4f5f4c95d6b09f619a85b16019791341ac12fe9b9b1e78672de"
    ),
    "patches/llama.cpp/b10216/e6f-current-series.patch": (
        "e11cdd41091d5d76b973c67ffcc04429760fbef58c7a2bc971947b80900a9893"
    ),
    "experiments/e6g_contract.json": (
        "92ad60fbc5fdf74ac10566230efcdbaf2322f9d4f68f1ed3822c2b3904fab1e8"
    ),
    "results/plans/e3f-cloud-quality.json": (
        "657188c8ae583e88c8f3907e3a8d16650a16a7b56c0ddfd5b467821b071866de"
    ),
}
REQUIRED_SUBMISSION_FILES = (
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "submission/README.md",
    "demo/index.html",
    "demo/styles.css",
    "demo/app.js",
    "demo/favicon.svg",
    "output/playwright/pareto64-overview.png",
    "output/playwright/pareto64-policy-lab.png",
    "output/playwright/pareto64-serving-boundary.png",
    "submission/devpost.md",
    "submission/evidence.md",
    "submission/demo-script.md",
    "submission/compliance.md",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


class LocalAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        attribute = (
            "href" if tag in {"a", "link"} else "src" if tag == "script" else None
        )
        if attribute is None:
            return
        value = attributes.get(attribute)
        if value and not value.startswith(
            ("#", "http://", "https://", "mailto:", "data:")
        ):
            self.assets.add(value)


def verify_demo() -> int:
    index = ROOT / "demo/index.html"
    parser = LocalAssetParser()
    parser.feed(index.read_text(encoding="utf-8"))
    missing = []
    for asset in parser.assets:
        candidate = (index.parent / asset).resolve()
        if not candidate.is_relative_to(ROOT) or not candidate.is_file():
            missing.append(asset)
    if missing:
        raise ValueError(f"demo references missing local assets: {missing}")
    if "<h1" not in index.read_text(encoding="utf-8"):
        raise ValueError("demo lacks a primary heading")
    return len(parser.assets)


def main() -> int:
    missing = [
        path for path in REQUIRED_SUBMISSION_FILES if not (ROOT / path).is_file()
    ]
    if missing:
        raise ValueError(f"submission package is missing files: {missing}")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    if "Apache License" not in license_text or "Version 2.0" not in license_text:
        raise ValueError("repository-level Apache-2.0 license is missing")

    for relative, expected in EXPECTED_HASHES.items():
        observed = sha256_file(ROOT / relative)
        if observed != expected:
            raise ValueError(f"retained evidence hash differs for {relative}")

    manifest_path = ROOT / "results/manifests/e3f-30656151957.json"
    policy_path = ROOT / "configs/cloud-quality.json"
    plan = build_plan(
        load_object(manifest_path),
        load_object(policy_path),
        manifest_path=manifest_path.relative_to(ROOT),
        constraints_path=policy_path.relative_to(ROOT),
    )
    retained_plan = load_object(ROOT / "results/plans/e3f-cloud-quality.json")
    if plan != retained_plan:
        raise ValueError("recomputed selected plan differs from the retained plan")
    if (
        plan.get("status") != "selected"
        or plan.get("selected", {}).get("name") != "ministral3_3b_q4_k_m"
        or plan.get("policy", {}).get("weighted_score_used") is not False
    ):
        raise ValueError("submission plan does not select the frozen Ministral package")

    serving = load_object(ROOT / "results/manifests/e5b-30659829983.json")
    if (
        serving.get("status") != "valid_selected_inference_no_concurrency_win"
        or serving.get("validation", {}).get("inference_server_claim_allowed")
        is not True
        or serving.get("validation", {}).get("two_slot_optimization_claim_allowed")
        is not False
        or serving.get("selection", {}).get("correct") != 23
    ):
        raise ValueError("retained serving decision differs from E5b evidence")

    prompt_cache = load_object(ROOT / "results/manifests/e5c-30662037235.json")
    if (
        prompt_cache.get("status") != "valid_selected_inference_prompt_cache"
        or prompt_cache.get("validation", {}).get(
            "prompt_cache_optimization_claim_allowed"
        )
        is not True
        or prompt_cache.get("selection", {}).get("correct") != 23
        or prompt_cache.get("throughput_improvement_ratio", 0) < 1.1
        or prompt_cache.get("prompt_encode_improvement_ratio", 0) < 1.1
    ):
        raise ValueError("retained prompt-cache decision differs from E5c evidence")

    cached_concurrency = load_object(ROOT / "results/manifests/e5d-30664666945.json")
    if (
        cached_concurrency.get("status")
        != "valid_selected_inference_no_cached_concurrency_win"
        or cached_concurrency.get("validation", {}).get(
            "cached_two_slot_optimization_claim_allowed"
        )
        is not False
        or cached_concurrency.get("validation", {}).get(
            "all_responses_match_selected_e3f_predictions"
        )
        is not True
        or cached_concurrency.get("selection", {}).get("correct") != 23
        or cached_concurrency.get("throughput_improvement_ratio", 0) >= 1.1
    ):
        raise ValueError(
            "retained cached-concurrency decision differs from E5d evidence"
        )

    memory_profile = load_object(ROOT / "results/manifests/e5e-30667019678.json")
    selected_profile = memory_profile.get("performance", {}).get("ctx256_k_f16", {})
    q4_profile = memory_profile.get("performance", {}).get("ctx256_k_q4_0", {})
    if (
        memory_profile.get("status") != "valid_selected_inference_memory_profile"
        or memory_profile.get("validation", {}).get("memory_profile_claim_allowed")
        is not True
        or memory_profile.get("selection", {}).get("configuration") != "ctx256_k_f16"
        or memory_profile.get("maximum_required_context") != 135
        or selected_profile.get("quality", {}).get("exact_selected_predictions")
        is not True
        or selected_profile.get("gates", {}).get("eligible") is not True
        or selected_profile.get("gates", {}).get("rss_reduction_kib", 0) < 131072
        or selected_profile.get("gates", {}).get("throughput_retention_ratio", 0) < 0.95
        or q4_profile.get("quality", {}).get("exact_selected_predictions") is not False
        or q4_profile.get("gates", {}).get("eligible") is not False
    ):
        raise ValueError("retained context/KV decision differs from E5e evidence")

    batch_profile = load_object(ROOT / "results/manifests/e5f-30669700602.json")
    selected_batch = batch_profile.get("performance", {}).get("batch64", {})
    batch128 = batch_profile.get("performance", {}).get("batch128", {})
    if (
        batch_profile.get("status") != "valid_selected_inference_batch_profile"
        or batch_profile.get("validation", {}).get("batch_profile_claim_allowed")
        is not True
        or batch_profile.get("validation", {}).get(
            "compute_buffer_sizes_microbatch_monotonic"
        )
        is not True
        or batch_profile.get("selection", {}).get("configuration") != "batch64"
        or selected_batch.get("quality", {}).get("exact_selected_predictions")
        is not True
        or selected_batch.get("gates", {}).get("eligible") is not True
        or selected_batch.get("gates", {}).get("compute_buffer_reduction_mib", 0) < 8
        or selected_batch.get("gates", {}).get("process_rss_reduction_kib", 0) < 8192
        or selected_batch.get("gates", {}).get("throughput_retention_ratio", 0) < 0.98
        or batch128.get("gates", {}).get("eligible") is not False
        or batch128.get("gates", {}).get("process_rss_reduction_passed") is not False
    ):
        raise ValueError("retained prompt-batch decision differs from E5f evidence")
    if resolve_batch_profile(None, None) != (64, 64):
        raise ValueError("launcher default differs from the E5f batch selection")

    batch_floor = load_object(ROOT / "results/manifests/e5g-30671733556.json")
    batch32 = batch_floor.get("performance", {}).get("batch32", {})
    if (
        batch_floor.get("status") != "valid_selected_inference_no_batch_profile_win"
        or batch_floor.get("validation", {}).get("batch_profile_claim_allowed")
        is not False
        or batch_floor.get("selection", {}).get("configuration") is not None
        or batch32.get("quality", {}).get("exact_selected_predictions") is not True
        or batch32.get("gates", {}).get("compute_buffer_reduction_passed") is not True
        or batch32.get("gates", {}).get("throughput_retention_passed") is not True
        or batch32.get("gates", {}).get("latency_retention_passed") is not True
        or batch32.get("gates", {}).get("process_rss_reduction_passed") is not False
        or batch32.get("gates", {}).get("eligible") is not False
    ):
        raise ValueError("retained marginal batch boundary differs from E5g evidence")

    repack_boundary = load_object(ROOT / "results/manifests/e5h-30672633366.json")
    repack_on = repack_boundary.get("performance", {}).get("repack_on", {})
    repack_off = repack_boundary.get("performance", {}).get("repack_off", {})
    hypothesis = repack_boundary.get("hypothesis", {})
    if (
        repack_boundary.get("status") != "valid_selected_inference_memory_tier"
        or repack_boundary.get("validation", {}).get("memory_tier_claim_allowed")
        is not True
        or repack_boundary.get("selection", {}).get("default_configuration")
        != "repack_on"
        or repack_boundary.get("selection", {}).get("memory_tier_configuration")
        != "repack_off"
        or hypothesis.get("passed") is not True
        or hypothesis.get("quality_passed") is not True
        or hypothesis.get("process_rss_reduction_passed") is not True
        or hypothesis.get("memory_tier_rss_ceiling_passed") is not True
        or hypothesis.get("throughput_retention_passed") is not True
        or hypothesis.get("latency_ceilings_passed") is not True
        or hypothesis.get("weighted_score_used") is not False
        or hypothesis.get("process_rss_reduction_kib", 0) < 1_572_864
        or hypothesis.get("throughput_retention_ratio", 0) < 0.3
        or repack_off.get("maximum_rss_kib", {}).get("max", 0) > 3_145_728
        or repack_on.get("weight_repack") is not True
        or repack_off.get("weight_repack") is not False
        or repack_on.get("quality", {}).get("exact_selected_predictions")
        is not True
        or repack_off.get("quality", {}).get("exact_selected_predictions")
        is not True
        or repack_on.get("mechanism", {}).get("repack_buffer_mib", 0) <= 0
        or repack_off.get("mechanism", {}).get("repack_buffer_mib") != 0
    ):
        raise ValueError("retained weight-repack boundary differs from E5h evidence")

    service_plans = (
        (
            "throughput",
            ROOT / "configs/service-throughput.json",
            ROOT / "results/plans/e5h-service-throughput.json",
            "repack_on",
            [],
        ),
        (
            "memory",
            ROOT / "configs/service-memory.json",
            ROOT / "results/plans/e5h-service-memory.json",
            "repack_off",
            ["--no-weight-repack"],
        ),
    )
    repack_path = ROOT / "results/manifests/e5h-30672633366.json"
    for (
        label,
        policy_path,
        retained_path,
        selected_name,
        launch_arguments,
    ) in service_plans:
        recomputed = build_service_plan(
            repack_boundary,
            load_object(policy_path),
            manifest_path=repack_path.relative_to(ROOT),
            constraints_path=policy_path.relative_to(ROOT),
        )
        if recomputed != load_object(retained_path):
            raise ValueError(f"recomputed {label} service plan differs")
        selected_service = recomputed.get("selected", {})
        if (
            recomputed.get("status") != "selected"
            or recomputed.get("policy", {}).get("weighted_score_used") is not False
            or selected_service.get("name") != selected_name
            or selected_service.get("runtime", {}).get("launch_arguments")
            != launch_arguments
        ):
            raise ValueError(f"retained {label} service decision differs")

    flash_ablation = load_object(ROOT / "results/manifests/e5i-30674023380.json")
    flash_auto = flash_ablation.get("performance", {}).get("flash_auto", {})
    flash_off = flash_ablation.get("performance", {}).get("flash_off", {})
    flash_hypothesis = flash_ablation.get("hypothesis", {})
    if (
        flash_ablation.get("status")
        != "valid_selected_inference_no_flash_attention_win"
        or flash_ablation.get("validation", {}).get("flash_attention_claim_allowed")
        is not False
        or flash_ablation.get("selection", {}).get("default_configuration")
        != "flash_auto"
        or flash_ablation.get("selection", {}).get(
            "validated_default_configuration"
        )
        is not None
        or flash_hypothesis.get("passed") is not False
        or flash_hypothesis.get("quality_passed") is not True
        or flash_hypothesis.get("throughput_improvement_passed") is not False
        or flash_hypothesis.get("median_latency_passed") is not True
        or flash_hypothesis.get("p95_latency_passed") is not False
        or flash_hypothesis.get("process_rss_overhead_passed") is not True
        or flash_hypothesis.get("weighted_score_used") is not False
        or flash_auto.get("mechanism", {}).get("resolved_enabled") is not True
        or flash_off.get("mechanism", {}).get("resolved_enabled") is not False
        or flash_auto.get("quality", {}).get("exact_selected_predictions")
        is not True
        or flash_off.get("quality", {}).get("exact_selected_predictions") is not True
    ):
        raise ValueError("retained Flash Attention ablation differs from E5i evidence")

    thread_profile = load_object(ROOT / "results/manifests/e5j-30677332825.json")
    thread_performance = thread_profile.get("performance", {})
    thread_hypothesis = thread_profile.get("hypothesis", {})
    thread_gates = thread_hypothesis.get("profile_gates", {})
    if (
        thread_profile.get("status")
        != "valid_selected_inference_no_thread_efficiency_win"
        or thread_profile.get("selection", {}).get("selected_configuration")
        != "threads4"
        or thread_profile.get("selection", {}).get("selected_threads") != 4
        or thread_profile.get("validation", {}).get(
            "thread_efficiency_claim_allowed"
        )
        is not False
        or thread_profile.get("validation", {}).get("energy_claim_allowed")
        is not False
        or thread_hypothesis.get("passed") is not False
        or thread_hypothesis.get("eligible_configurations") != []
        or thread_hypothesis.get("weighted_score_used") is not False
        or thread_hypothesis.get("metric_boundary")
        != "server process CPU time; not energy or power"
        or {name: profile.get("threads") for name, profile in thread_performance.items()}
        != {"threads2": 2, "threads3": 3, "threads4": 4}
        or any(
            profile.get("quality", {}).get("exact_selected_predictions") is not True
            for profile in thread_performance.values()
        )
        or any(thread_gates[name].get("eligible") is not False for name in thread_gates)
        or thread_gates.get("threads2", {}).get("cpu_time_reduction_passed")
        is not False
        or thread_gates.get("threads3", {}).get("cpu_time_reduction_passed")
        is not False
        or thread_gates.get("threads2", {}).get("throughput_retention_passed")
        is not False
        or thread_gates.get("threads3", {}).get("throughput_retention_passed")
        is not False
        or thread_gates.get("threads2", {}).get("latency_retention_passed")
        is not False
        or thread_gates.get("threads3", {}).get("latency_retention_passed")
        is not False
    ):
        raise ValueError("retained thread profile differs from E5j evidence")

    current_patches = load_object(ROOT / "results/manifests/e6d-30675654688.json")
    current_source = current_patches.get("source", {})
    feature = current_patches.get("feature_reproduction", {})
    baseline_tests = current_patches.get("targeted_tests", {}).get("baseline", {})
    patched_tests = current_patches.get("targeted_tests", {}).get("patched", {})
    current_validation = current_patches.get("validation", {})
    current_criteria = current_validation.get("criteria", {})
    direct = current_patches.get("direct_benchmark", {})
    if (
        current_patches.get("status") != "valid_current_upstream_rebase"
        or current_patches.get("host") != {"architecture": "aarch64", "native": True}
        or current_source.get("github_run_id") != "30675654688"
        or current_source.get("llama_cpp_tag") != "b10216"
        or current_source.get("llama_cpp_commit")
        != "876a4321163249c43ca4e986818fab5ab081f282"
        or feature.get("baseline_exit_status") != 1
        or feature.get("baseline_invalid_sve_source_observed") is not True
        or feature.get("validated_sve_disabled") is not True
        or feature.get("patched_exit_status") != 0
        or feature.get("patched_invalid_sve_source_absent") is not True
        or baseline_tests.get("reasoning_exit_status") != 134
        or baseline_tests.get("reasoning_regression_reproduced") is not True
        or baseline_tests.get("quantize_exit_status") != 0
        or baseline_tests.get("assembly")
        != {
            "byte_stores": 31,
            "static_instructions": 157,
            "vector_narrows": 0,
            "vector_stores": 0,
        }
        or patched_tests.get("reasoning_exit_status") != 0
        or patched_tests.get("reasoning_complete_suite_passed") is not True
        or patched_tests.get("quantize_exit_status") != 0
        or patched_tests.get("assembly")
        != {
            "byte_stores": 0,
            "static_instructions": 100,
            "vector_narrows": 6,
            "vector_stores": 2,
        }
        or set(current_criteria.values()) != {True}
        or len(current_criteria) != 16
        or current_validation.get("current_upstream_claim_allowed") is not True
        or current_validation.get("weighted_score_used") is not False
        or current_validation.get("claim_scope")
        != (
            "current-upstream patch applicability, targeted correctness, and "
            "direct Q8 hot-path performance only"
        )
        or direct.get("4096", {}).get("median_improvement_ratio", 0) < 1.25
        or direct.get("65536", {}).get("median_improvement_ratio", 0) < 1.15
        or direct.get("655360", {}).get("median_improvement_ratio", 0) < 0.98
        or any(
            direct.get(size, {}).get("improved_rounds") != 4
            or direct.get(size, {}).get("total_rounds") != 4
            for size in ("4096", "65536", "655360")
        )
    ):
        raise ValueError("retained current-upstream patch evidence differs from E6d")

    upstream_lane = load_object(
        ROOT / "results/manifests/e6e-30676413765.json"
    )
    upstream_source = upstream_lane.get("source", {})
    upstream_build = upstream_lane.get("build", {})
    upstream_tests = upstream_lane.get("tests", {})
    upstream_validation = upstream_lane.get("validation", {})
    upstream_criteria = upstream_validation.get("criteria", {})
    upstream_passed = set(upstream_tests.get("passed_test_names", []))
    if (
        upstream_lane.get("status") != "valid_upstream_arm_cpu_lane"
        or upstream_lane.get("host")
        != {"architecture": "aarch64", "native": True}
        or upstream_source.get("github_run_id") != "30676413765"
        or upstream_source.get("llama_cpp_tag") != "b10216"
        or upstream_source.get("llama_cpp_commit")
        != "876a4321163249c43ca4e986818fab5ab081f282"
        or upstream_build
        != {
            "build_exit_status": 0,
            "compiler_bound": True,
            "configuration_bound": True,
            "configure_exit_status": 0,
        }
        or upstream_tests.get("exit_status") != 0
        or upstream_tests.get("total") != 47
        or upstream_tests.get("passed") != 47
        or upstream_tests.get("failures") != 0
        or upstream_tests.get("errors") != 0
        or upstream_tests.get("skipped") != 0
        or not {
            "test-reasoning-budget",
            "test-quantize-fns",
            "test-quantize-perf",
        }
        <= upstream_passed
        or set(upstream_criteria.values()) != {True}
        or len(upstream_criteria) != 10
        or upstream_validation.get("upstream_arm_cpu_lane_claim_allowed")
        is not True
        or upstream_validation.get("weighted_score_used") is not False
        or upstream_validation.get("claim_scope")
        != (
            "one upstream-equivalent native Arm CPU build and main CTest lane "
            "for the frozen three-patch series only"
        )
    ):
        raise ValueError("retained upstream Arm CPU lane differs from E6e evidence")

    runtime_upgrade = load_object(ROOT / "results/manifests/e6f-30678703184.json")
    upgrade_contract = runtime_upgrade.get("contract", {})
    upgrade_service = upgrade_contract.get("service", {})
    upgrade_source = runtime_upgrade.get("source", {}).get("runtime_proof", {})
    upgrade_selection = runtime_upgrade.get("selection", {})
    upgrade_validation = runtime_upgrade.get("validation", {})
    upgrade_hypothesis = runtime_upgrade.get("hypothesis", {})
    upgrade_performance = runtime_upgrade.get("performance", {})
    if (
        runtime_upgrade.get("status") != "valid_current_runtime_upgrade_candidate"
        or runtime_upgrade.get("provenance", {}).get("github_run_id")
        != "30678703184"
        or upgrade_source.get("baseline", {}).get("commit")
        != "9d9a6d29f6b981cc7f41983d26e56485c6af1811"
        or upgrade_source.get("current_patched", {}).get("commit")
        != "876a4321163249c43ca4e986818fab5ab081f282"
        or len(
            upgrade_contract.get("runtimes", {})
            .get("current_patched", {})
            .get("patches", [])
        )
        != 3
        or upgrade_selection.get("candidate") != "ministral3_3b_q4_k_m"
        or upgrade_selection.get("selected_runtime") != "current_patched"
        or upgrade_selection.get("selected_commit")
        != "876a4321163249c43ca4e986818fab5ab081f282"
        or upgrade_service
        != {
            "batch_size": 64,
            "client_concurrency": 1,
            "context_per_slot": 256,
            "flash_attention": "auto",
            "kv_cache_type_k": "f16",
            "kv_cache_type_v": "f16",
            "micro_batch_size": 64,
            "prompt_cache": True,
            "server_parallel_slots": 1,
            "threads": 4,
            "warmup_slot_ids": [0, 0],
            "weight_repack": True,
        }
        or upgrade_hypothesis.get("passed") is not True
        or upgrade_hypothesis.get("throughput_retention_ratio", 0) < 0.95
        or upgrade_hypothesis.get("median_http_latency_ratio", 99) > 1.05
        or upgrade_hypothesis.get("p95_http_latency_ratio", 99) > 1.05
        or upgrade_hypothesis.get("cpu_seconds_per_request_ratio", 99) > 1.05
        or upgrade_hypothesis.get("ready_time_ratio", 99) > 1.1
        or upgrade_hypothesis.get("candidate_rss_increase_kib", 99_999) > 65_536
        or any(
            profile.get("quality", {}).get("exact_selected_predictions") is not True
            for profile in upgrade_performance.values()
        )
        or upgrade_validation.get("upgrade_candidate_claim_allowed") is not True
        or upgrade_validation.get("automatic_product_promotion_allowed") is not False
        or upgrade_validation.get("energy_claim_allowed") is not False
        or upgrade_validation.get("weighted_score_used") is not False
    ):
        raise ValueError("retained selected-service upgrade differs from E6f evidence")

    runtime_contract_path = ROOT / "configs/runtime-b10216-selected-service.json"
    runtime_contract = load_object(runtime_contract_path)
    runtime_record = runtime_contract.get("runtime", {})
    runtime_manifest_record = runtime_contract.get("runtime_manifest", {})
    model_manifest_record = runtime_contract.get("model_selection_manifest", {})
    source_diff_path = ROOT / runtime_record.get("source_diff_path", "")
    if (
        runtime_contract.get("schema_version") != 1
        or runtime_contract.get("promotion_mode")
        != "explicit_evidence_bound_upgrade"
        or runtime_contract.get("selected_candidate")
        != upgrade_selection.get("candidate")
        or runtime_manifest_record.get("sha256")
        != sha256_file(ROOT / runtime_manifest_record.get("path", ""))
        or model_manifest_record.get("sha256")
        != sha256_file(ROOT / model_manifest_record.get("path", ""))
        or runtime_record.get("baseline_commit")
        != upgrade_source.get("baseline", {}).get("commit")
        or runtime_record.get("selected_commit")
        != upgrade_source.get("current_patched", {}).get("commit")
        or runtime_record.get("source_diff_sha256") != sha256_file(source_diff_path)
        or runtime_record.get("patches")
        != [
            {"name": patch.get("name"), "sha256": patch.get("sha256")}
            for patch in upgrade_contract.get("runtimes", {})
            .get("current_patched", {})
            .get("patches", [])
        ]
    ):
        raise ValueError("current-runtime launch contract differs from E6f")
    validate_runtime_upgrade_service(
        runtime_upgrade,
        runtime_contract,
        runtime_contract["service"],
    )

    launch_integration = load_object(
        ROOT / "results/manifests/e6g-30679814341.json"
    )
    launch_quality = launch_integration.get("quality", {})
    launch_performance = launch_integration.get("performance", {})
    launch_runtime = launch_integration.get("runtime_provenance", {})
    launch_validation = launch_integration.get("validation", {})
    if (
        launch_integration.get("status")
        != "valid_current_runtime_launch_integration"
        or launch_integration.get("provenance", {}).get("github_run_id")
        != "30679814341"
        or launch_integration.get("platform", {}).get("architecture") != "aarch64"
        or launch_quality.get("correct") != 23
        or launch_quality.get("total") != 30
        or launch_quality.get("exact_selected_predictions") is not True
        or launch_quality.get("reference_prediction_mismatches") != 0
        or launch_quality.get("request_failures") != 0
        or launch_quality.get(
            "cached_prefix_observed_in_every_measured_request"
        )
        is not True
        or launch_performance.get("ready_ms", 99_999) > 15_000
        or launch_performance.get("maximum_rss_kib", 99_999_999) > 8_388_608
        or launch_runtime.get("selected_commit")
        != runtime_record.get("selected_commit")
        or launch_runtime.get("runtime_manifest_sha256")
        != EXPECTED_HASHES["results/manifests/e6f-30678703184.json"]
        or launch_runtime.get("runtime_contract_sha256")
        != EXPECTED_HASHES["configs/runtime-b10216-selected-service.json"]
        or launch_runtime.get("source_diff_sha256")
        != EXPECTED_HASHES["patches/llama.cpp/b10216/e6f-current-series.patch"]
        or launch_runtime.get("changed_files") != runtime_record.get("changed_files")
        or launch_validation.get("current_runtime_launch_claim_allowed") is not True
        or launch_validation.get("live_server_executed_through_adapter") is not True
        or launch_validation.get("source_build_binary_bound") is not True
        or launch_validation.get("exact_service_recipe_verified") is not True
        or launch_validation.get("automatic_other_profile_promotion_allowed")
        is not False
        or launch_validation.get("energy_claim_allowed") is not False
        or launch_validation.get("weighted_score_used") is not False
    ):
        raise ValueError("retained current-runtime launch differs from E6g evidence")

    local_assets = verify_demo()
    print("Pareto64 submission verification passed")
    print(f"selected candidate: {plan['selected']['name']}")
    print(f"selected accuracy: {plan['selected']['metrics']['minimum_accuracy']:.4f}")
    print(f"verified evidence files: {len(EXPECTED_HASHES)}")
    print(f"verified demo links/assets: {local_assets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
