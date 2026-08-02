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
    "results/manifests/e6h-30690331795.json": (
        "7b112b385729ef092f2026bf35b63926ac985251d70faea2cf03e4936253b27f"
    ),
    "results/manifests/e6i-30691254831.json": (
        "2bcbd7e1a7b727a763ca12c9664106a82d9ef8a70ec17ef1ac2fe9ed460c06d2"
    ),
    "results/manifests/e7a-30692292700.json": (
        "b48e6c129d1f3305c2b788b422bc5321cd415b2bc2b26460804063ebc3b46839"
    ),
    "results/manifests/e7b-30695349303.json": (
        "8dffd667e8517a1b628c147f22f5e74755ab7d7d693e8eff1e1704ae387ffd9b"
    ),
    "results/manifests/e7c-30696606993.json": (
        "f4e73971b0c6f2db25be52e365cf611848ec1bb1d738648bb43bdf4c2e1857cf"
    ),
    "results/manifests/e9a-30764802071.json": (
        "39424e7f3a43a3a05b4139609224584945c8da7c1de66a9f224e8c7184de012d"
    ),
    "results/manifests/e9b-preflight-30766707967.json": (
        "9f654a9fc5af6a02bcbb12d2cea84aa754d0c864ca83fd35943c627b38685162"
    ),
    "results/manifests/e9c-30770403695.json": (
        "29b075b605e5d84d6de66b07fb4ab3c1562236c9aa4e7fd43d51e0ff7932eed4"
    ),
    "patches/llama.cpp/pr-ready/b10216/0000-cover-letter.patch": (
        "9760fe1bd38d9e897ea98e4afc1c638bf1642869c710f3fc0f0a32ea9bdbdf3d"
    ),
    (
        "patches/llama.cpp/pr-ready/b10216/"
        "0001-ggml-cpu-select-KleidiAI-sources-from-feature-probes.patch"
    ): (
        "e079c30569b739cd6de0366439c6975a6c03e594d01740de8086a718fb94d50c"
    ),
    (
        "patches/llama.cpp/pr-ready/b10216/"
        "0002-ggml-cpu-use-vector-stores-in-quantize_row_q8_0.patch"
    ): (
        "8427338153baf91bec3cc29f285a3381f50b30c784c53e7f36dc5c1c2eee2140"
    ),
    (
        "patches/llama.cpp/pr-ready/b10216/"
        "0003-common-guard-forced-reasoning-token-acceptance.patch"
    ): (
        "da0eca74874f9738edcb4d66558057c9aca707353ef667fb6700ab734bf99598"
    ),
    "configs/runtime-b10216-selected-service.json": (
        "9d4750364878e4f5f4c95d6b09f619a85b16019791341ac12fe9b9b1e78672de"
    ),
    "configs/runtime-b10216-memory-service.json": (
        "a3d1e066700dfe4ea3ad9dff8f06fc0dfd508adae961b7e32c9f3d2574ebc008"
    ),
    "configs/runtime-b10216-http-service.json": (
        "95cb669b70de98851b8bb2f04d7be6650745e0fbd39aa4d3256b5bb9c2a2b928"
    ),
    "patches/llama.cpp/b10216/e6f-current-series.patch": (
        "e11cdd41091d5d76b973c67ffcc04429760fbef58c7a2bc971947b80900a9893"
    ),
    "experiments/e6g_contract.json": (
        "92ad60fbc5fdf74ac10566230efcdbaf2322f9d4f68f1ed3822c2b3904fab1e8"
    ),
    "experiments/e6h_contract.json": (
        "e1e3bd876fb724358c1d6ab62d0ef25cbcabeac2b1fb6a972975d8cb5863f31d"
    ),
    "experiments/e6i_contract.json": (
        "7b7f0b5dd2598bb89be4163ced702d1c27c34078232aa0a7926bc40426194265"
    ),
    "experiments/e7a_contract.json": (
        "2d57010a168a777cc5de2ed2a7d6e0f11900d14a30d44ded6db34ecd85b1aa12"
    ),
    "experiments/e7b_contract.json": (
        "2c5cd9f8d84ef5f77fdd14c66a7822189ec09ff6688743e26f7f2fd7c77abea9"
    ),
    "experiments/e7c_contract.json": (
        "2f6a96acb0fa7c877c7f42083cd85b728c5779a75173bdcca62d801b306344de"
    ),
    "experiments/e9a_contract.json": (
        "56c275b2f986991688dd97790fe9d9cfba9213db7b0cfe2614a3c81d0c65f928"
    ),
    "experiments/e9b_preflight_plan.json": (
        "ff492b46e512220abd2ea3135bd807881f5ac4e1f9c5ee8b9b77de31229f9cd0"
    ),
    "experiments/e9c_contract.json": (
        "a72ec175091e2e8b98adc12a795e5242cee49377f2683ddb2eefcbf564341c76"
    ),
    "experiments/e9d_contract.json": (
        "ed8226d2e81f95bbb3e3f5d99d1598619cb4cbfadfb6322a9daba2025433b8d1"
    ),
    "results/plans/e3f-cloud-quality.json": (
        "657188c8ae583e88c8f3907e3a8d16650a16a7b56c0ddfd5b467821b071866de"
    ),
}
REQUIRED_SUBMISSION_FILES = (
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "docs/final-device-evidence.md",
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
        or {
            name: profile.get("threads")
            for name, profile in thread_performance.items()
        }
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

    memory_upgrade = load_object(ROOT / "results/manifests/e6h-30690331795.json")
    memory_contract = memory_upgrade.get("contract", {})
    memory_service = memory_contract.get("service", {})
    memory_performance = memory_upgrade.get("performance", {})
    memory_hypothesis = memory_upgrade.get("hypothesis", {})
    memory_validation = memory_upgrade.get("validation", {})
    if (
        memory_upgrade.get("status")
        != "valid_current_runtime_memory_tier_upgrade_candidate"
        or memory_upgrade.get("provenance", {}).get("github_run_id")
        != "30690331795"
        or memory_upgrade.get("platform", {}).get("architecture") != "aarch64"
        or memory_upgrade.get("selection", {}).get("candidate")
        != "ministral3_3b_q4_k_m"
        or memory_upgrade.get("selection", {}).get("correct") != 23
        or memory_upgrade.get("selection", {}).get("selected_runtime")
        != "current_patched"
        or memory_upgrade.get("selection", {}).get("selected_commit")
        != runtime_record.get("selected_commit")
        or memory_service.get("weight_repack") is not False
        or memory_service.get("threads") != 4
        or memory_service.get("server_parallel_slots") != 1
        or memory_service.get("context_per_slot") != 256
        or memory_service.get("batch_size") != 64
        or memory_service.get("micro_batch_size") != 64
        or memory_hypothesis.get("passed") is not True
        or memory_hypothesis.get("throughput_retention_ratio", 0) < 0.95
        or memory_hypothesis.get("median_http_latency_ratio", 99) > 1.05
        or memory_hypothesis.get("p95_http_latency_ratio", 99) > 1.05
        or memory_hypothesis.get("cpu_seconds_per_request_ratio", 99) > 1.05
        or memory_hypothesis.get("ready_time_ratio", 99) > 1.1
        or memory_hypothesis.get("candidate_rss_increase_kib", 99_999) > 65_536
        or any(
            profile.get("quality", {}).get("exact_selected_predictions") is not True
            or profile.get("maximum_rss_kib", {}).get("max", 99_999_999)
            > 3_145_728
            for profile in memory_performance.values()
        )
        or memory_validation.get("memory_tier_upgrade_candidate_claim_allowed")
        is not True
        or memory_validation.get("runtime_buffer_proofs_observed") is not True
        or memory_validation.get("automatic_product_promotion_allowed") is not False
        or memory_validation.get("energy_claim_allowed") is not False
        or memory_validation.get("weighted_score_used") is not False
    ):
        raise ValueError("retained memory-tier upgrade differs from E6h evidence")

    memory_runtime_contract = load_object(
        ROOT / "configs/runtime-b10216-memory-service.json"
    )
    memory_runtime_record = memory_runtime_contract.get("runtime", {})
    memory_runtime_manifest = memory_runtime_contract.get("runtime_manifest", {})
    memory_model_manifest = memory_runtime_contract.get(
        "model_selection_manifest", {}
    )
    if (
        memory_runtime_contract.get("schema_version") != 1
        or memory_runtime_contract.get("promotion_mode")
        != "explicit_evidence_bound_upgrade"
        or memory_runtime_contract.get("selected_candidate")
        != memory_upgrade.get("selection", {}).get("candidate")
        or memory_runtime_manifest.get("experiment_id") != "E6h"
        or memory_runtime_manifest.get("sha256")
        != EXPECTED_HASHES["results/manifests/e6h-30690331795.json"]
        or memory_model_manifest.get("sha256")
        != EXPECTED_HASHES["results/manifests/e3f-30656151957.json"]
        or memory_runtime_record != runtime_record
        or memory_runtime_contract.get("service", {}).get("weight_repack")
        is not False
    ):
        raise ValueError("current-runtime memory launch contract differs from E6h")
    validate_runtime_upgrade_service(
        memory_upgrade,
        memory_runtime_contract,
        memory_runtime_contract["service"],
    )

    memory_launch_contract = load_object(ROOT / "experiments/e6i_contract.json")
    memory_launch_inputs = memory_launch_contract.get("inputs", {})
    memory_launch_service = dict(memory_launch_contract.get("service", {}))
    memory_launch_service.pop("client_concurrency", None)
    memory_launch_service.pop("explicit_batch_arguments", None)
    memory_launch_service.pop("warmup_slot_ids", None)
    memory_launch_service["parallel_slots"] = memory_launch_service.pop(
        "server_parallel_slots", None
    )
    if (
        memory_launch_contract.get("schema_version") != 1
        or memory_launch_contract.get("experiment_id") != "E6i"
        or memory_launch_inputs.get("runtime_manifest_sha256")
        != EXPECTED_HASHES["results/manifests/e6h-30690331795.json"]
        or memory_launch_inputs.get("runtime_contract_sha256")
        != EXPECTED_HASHES["configs/runtime-b10216-memory-service.json"]
        or memory_launch_service != memory_runtime_contract.get("service")
        or memory_launch_contract.get("acceptance", {}).get(
            "maximum_process_rss_kib"
        )
        != 3_145_728
        or memory_launch_contract.get("selection_policy", {}).get(
            "weighted_score_used"
        )
        is not False
    ):
        raise ValueError("frozen E6i launch integration differs from E6h")

    memory_launch = load_object(ROOT / "results/manifests/e6i-30691254831.json")
    memory_launch_quality = memory_launch.get("quality", {})
    memory_launch_performance = memory_launch.get("performance", {})
    memory_launch_runtime = memory_launch.get("runtime_provenance", {})
    memory_launch_validation = memory_launch.get("validation", {})
    memory_launch_selection = memory_launch.get("selection", {})
    if (
        memory_launch.get("status")
        != "valid_current_runtime_memory_launch_integration"
        or memory_launch.get("provenance", {}).get("github_run_id")
        != "30691254831"
        or memory_launch.get("platform", {}).get("architecture") != "aarch64"
        or memory_launch_selection.get("candidate")
        != memory_upgrade.get("selection", {}).get("candidate")
        or memory_launch_selection.get("runtime_commit")
        != runtime_record.get("selected_commit")
        or memory_launch_selection.get("service", {}).get("weight_repack")
        is not False
        or memory_launch_quality.get("correct") != 23
        or memory_launch_quality.get("total") != 30
        or memory_launch_quality.get("exact_selected_predictions") is not True
        or memory_launch_quality.get("reference_prediction_mismatches") != 0
        or memory_launch_quality.get("request_failures") != 0
        or memory_launch_quality.get(
            "cached_prefix_observed_in_every_measured_request"
        )
        is not True
        or memory_launch_performance.get("ready_ms", 99_999) > 15_000
        or memory_launch_performance.get("maximum_rss_kib", 99_999_999)
        > 3_145_728
        or memory_launch_runtime.get("runtime_manifest_sha256")
        != EXPECTED_HASHES["results/manifests/e6h-30690331795.json"]
        or memory_launch_runtime.get("runtime_contract_sha256")
        != EXPECTED_HASHES["configs/runtime-b10216-memory-service.json"]
        or memory_launch_runtime.get("source_diff_sha256")
        != EXPECTED_HASHES["patches/llama.cpp/b10216/e6f-current-series.patch"]
        or memory_launch_validation.get(
            "current_runtime_memory_launch_claim_allowed"
        )
        is not True
        or memory_launch_validation.get("live_server_executed_through_adapter")
        is not True
        or memory_launch_validation.get("source_build_binary_bound") is not True
        or memory_launch_validation.get("exact_service_recipe_verified") is not True
        or memory_launch_validation.get("automatic_other_profile_promotion_allowed")
        is not False
        or memory_launch_validation.get("energy_claim_allowed") is not False
        or memory_launch_validation.get("weighted_score_used") is not False
    ):
        raise ValueError("retained current-runtime memory launch differs from E6i")

    lto_contract = load_object(ROOT / "experiments/e7a_contract.json")
    lto_profiles = lto_contract.get("build", {}).get("profiles", {})
    lto_execution = lto_contract.get("execution", {})
    lto_acceptance = lto_contract.get("acceptance", {})
    if (
        lto_contract.get("schema_version") != 1
        or lto_contract.get("experiment_id") != "E7a"
        or lto_contract.get("runtime", {}).get("commit")
        != runtime_record.get("selected_commit")
        or lto_contract.get("runtime", {}).get("source_diff_sha256")
        != EXPECTED_HASHES["patches/llama.cpp/b10216/e6f-current-series.patch"]
        or lto_contract.get("service")
        != runtime_upgrade.get("contract", {}).get("service")
        or lto_profiles.get("lto_off", {}).get("ggml_lto") is not False
        or lto_profiles.get("lto_on", {}).get("ggml_lto") is not True
        or lto_execution.get("baseline_profile") != "lto_off"
        or lto_execution.get("candidate_profile") != "lto_on"
        or [item.get("profile") for item in lto_execution.get("order", [])]
        != ["lto_off", "lto_on", "lto_on", "lto_off"]
        or lto_acceptance.get("performance_branch_minimum_throughput_ratio")
        != 1.03
        or lto_acceptance.get("footprint_branch_minimum_throughput_ratio")
        != 0.98
        or lto_acceptance.get("footprint_branch_maximum_runtime_closure_ratio")
        != 0.95
        or lto_contract.get("selection_policy", {}).get("weighted_score_used")
        is not False
    ):
        raise ValueError("frozen E7a LTO ablation differs from selected service")

    lto_result = load_object(ROOT / "results/manifests/e7a-30692292700.json")
    lto_hypothesis = lto_result.get("hypothesis", {})
    lto_validation = lto_result.get("validation", {})
    lto_performance = lto_result.get("performance", {})
    lto_builds = lto_result.get("build_profiles", {})
    if (
        lto_result.get("status") != "valid_lto_no_win"
        or lto_result.get("provenance", {}).get("github_run_id") != "30692292700"
        or lto_result.get("platform", {}).get("architecture") != "aarch64"
        or lto_result.get("selection", {}).get("candidate")
        != "ministral3_3b_q4_k_m"
        or lto_result.get("selection", {}).get("selected_profile") != "lto_off"
        or lto_hypothesis.get("passed") is not False
        or lto_hypothesis.get("common_guardrails_passed") is not True
        or lto_hypothesis.get("performance_branch_passed") is not False
        or lto_hypothesis.get("footprint_branch_passed") is not False
        or lto_hypothesis.get("throughput_ratio", 99) >= 1.03
        or lto_hypothesis.get("runtime_closure_ratio", 0) <= 0.95
        or any(
            profile.get("quality", {}).get("exact_selected_predictions")
            is not True
            for profile in lto_performance.values()
        )
        or set(lto_builds) != {"lto_off", "lto_on"}
        or any(
            build.get("runtime_closure", {}).get("file_count") != 8
            for build in lto_builds.values()
        )
        or lto_validation.get("lto_build_mechanism_verified") is not True
        or lto_validation.get("transitive_runtime_closures_hashed") is not True
        or lto_validation.get("lto_optimization_claim_allowed") is not False
        or lto_validation.get("automatic_product_promotion_allowed") is not False
        or lto_validation.get("energy_claim_allowed") is not False
        or lto_validation.get("weighted_score_used") is not False
    ):
        raise ValueError("retained E7a result differs from the native no-win")

    openssl_contract = load_object(ROOT / "experiments/e7b_contract.json")
    openssl_profiles = openssl_contract.get("build", {}).get("profiles", {})
    openssl_execution = openssl_contract.get("execution", {})
    openssl_acceptance = openssl_contract.get("acceptance", {})
    if (
        openssl_contract.get("schema_version") != 1
        or openssl_contract.get("experiment_id") != "E7b"
        or openssl_contract.get("runtime", {}).get("commit")
        != runtime_record.get("selected_commit")
        or openssl_contract.get("runtime", {}).get("source_diff_sha256")
        != EXPECTED_HASHES["patches/llama.cpp/b10216/e6f-current-series.patch"]
        or openssl_contract.get("service")
        != runtime_upgrade.get("contract", {}).get("service")
        or openssl_profiles.get("openssl_on", {}).get("llama_openssl") is not True
        or openssl_profiles.get("openssl_off", {}).get("llama_openssl")
        is not False
        or "CPPHTTPLIB_OPENSSL_SUPPORT"
        not in openssl_profiles.get("openssl_on", {}).get(
            "required_command_patterns", []
        )
        or "CPPHTTPLIB_OPENSSL_SUPPORT"
        not in openssl_profiles.get("openssl_off", {}).get(
            "forbidden_command_patterns", []
        )
        or openssl_execution.get("baseline_profile") != "openssl_on"
        or openssl_execution.get("candidate_profile") != "openssl_off"
        or [item.get("profile") for item in openssl_execution.get("order", [])]
        != ["openssl_on", "openssl_off", "openssl_off", "openssl_on"]
        or openssl_acceptance.get("required_baseline_system_dependency_basenames")
        != ["libcrypto.so.3", "libssl.so.3"]
        or openssl_acceptance.get("forbidden_candidate_system_dependency_basenames")
        != ["libcrypto.so.3", "libssl.so.3"]
        or openssl_acceptance.get("maximum_new_candidate_dependency_count") != 0
        or openssl_acceptance.get("minimum_throughput_ratio") != 0.98
        or openssl_acceptance.get("maximum_runtime_closure_ratio") != 1.0
        or openssl_contract.get("selection_policy", {}).get("weighted_score_used")
        is not False
    ):
        raise ValueError(
            "frozen E7b OpenSSL ablation differs from the selected HTTP service"
        )

    openssl_result = load_object(ROOT / "results/manifests/e7b-30695349303.json")
    openssl_hypothesis = openssl_result.get("hypothesis", {})
    openssl_validation = openssl_result.get("validation", {})
    openssl_performance = openssl_result.get("performance", {})
    openssl_builds = openssl_result.get("build_profiles", {})
    baseline_build = openssl_builds.get("openssl_on", {})
    candidate_build = openssl_builds.get("openssl_off", {})
    if (
        openssl_result.get("status")
        != "valid_http_dependency_pruning_candidate"
        or openssl_result.get("provenance", {}).get("github_run_id")
        != "30695349303"
        or openssl_result.get("platform", {}).get("architecture") != "aarch64"
        or openssl_result.get("selection", {}).get("candidate")
        != "ministral3_3b_q4_k_m"
        or openssl_result.get("selection", {}).get("selected_profile")
        != "openssl_off"
        or openssl_hypothesis.get("passed") is not True
        or openssl_hypothesis.get("dependency_pruning_passed") is not True
        or openssl_hypothesis.get("removed_dependencies")
        != ["libcrypto.so.3", "libssl.so.3"]
        or openssl_hypothesis.get("new_candidate_dependencies") != []
        or openssl_hypothesis.get("throughput_ratio", 0) < 0.98
        or openssl_hypothesis.get("runtime_closure_ratio", 99) > 1.0
        or any(
            profile.get("quality", {}).get("exact_selected_predictions")
            is not True
            for profile in openssl_performance.values()
        )
        or set(openssl_builds) != {"openssl_on", "openssl_off"}
        or baseline_build.get("llama_openssl") is not True
        or candidate_build.get("llama_openssl") is not False
        or baseline_build.get("runtime_closure", {}).get("file_count") != 8
        or candidate_build.get("runtime_closure", {}).get("file_count") != 8
        or baseline_build.get("runtime_closure", {}).get("total_size_bytes")
        != 20_058_904
        or candidate_build.get("runtime_closure", {}).get("total_size_bytes")
        != 19_857_648
        or "libssl.so.3" not in baseline_build.get("dependency_basenames", [])
        or "libcrypto.so.3" not in baseline_build.get("dependency_basenames", [])
        or "libssl.so.3" in candidate_build.get("dependency_basenames", [])
        or "libcrypto.so.3" in candidate_build.get("dependency_basenames", [])
        or openssl_validation.get("openssl_build_mechanism_verified") is not True
        or openssl_validation.get("transitive_runtime_dependencies_inventoried")
        is not True
        or openssl_validation.get("http_dependency_pruning_claim_allowed")
        is not True
        or openssl_validation.get("https_deployment_supported_by_candidate")
        is not False
        or openssl_validation.get("automatic_product_promotion_allowed")
        is not False
        or openssl_validation.get("security_claim_allowed") is not False
        or openssl_validation.get("energy_claim_allowed") is not False
        or openssl_validation.get("weighted_score_used") is not False
    ):
        raise ValueError("retained E7b dependency-pruning result differs")

    http_runtime_contract = load_object(
        ROOT / "configs/runtime-b10216-http-service.json"
    )
    http_runtime_manifest = http_runtime_contract.get("runtime_manifest", {})
    http_model_manifest = http_runtime_contract.get(
        "model_selection_manifest", {}
    )
    http_runtime_build = http_runtime_contract.get("build", {})
    if (
        http_runtime_contract.get("schema_version") != 1
        or http_runtime_contract.get("promotion_mode")
        != "explicit_evidence_bound_upgrade"
        or http_runtime_contract.get("selected_candidate")
        != openssl_result.get("selection", {}).get("candidate")
        or http_runtime_manifest.get("experiment_id") != "E7b"
        or http_runtime_manifest.get("sha256")
        != EXPECTED_HASHES["results/manifests/e7b-30695349303.json"]
        or http_model_manifest.get("sha256")
        != EXPECTED_HASHES["results/manifests/e3f-30656151957.json"]
        or http_runtime_contract.get("runtime") != runtime_record
        or http_runtime_build.get("selected_profile") != "openssl_off"
        or "GGML_LTO:BOOL=OFF"
        not in http_runtime_build.get("cmake_cache_entries", [])
        or "LLAMA_OPENSSL:BOOL=OFF"
        not in http_runtime_build.get("cmake_cache_entries", [])
        or http_runtime_build.get("forbidden_dynamic_dependency_basenames")
        != ["libcrypto.so.3", "libssl.so.3"]
        or http_runtime_contract.get("service", {}).get("weight_repack")
        is not True
    ):
        raise ValueError("HTTP-only runtime launch contract differs from E7b")
    validate_runtime_upgrade_service(
        openssl_result,
        http_runtime_contract,
        http_runtime_contract["service"],
    )

    http_launch_contract = load_object(ROOT / "experiments/e7c_contract.json")
    fast_launch_contract = load_object(ROOT / "experiments/e6g_contract.json")
    http_launch_inputs = http_launch_contract.get("inputs", {})
    http_launch_service = dict(http_launch_contract.get("service", {}))
    http_launch_service.pop("client_concurrency", None)
    http_launch_service.pop("explicit_batch_arguments", None)
    http_launch_service.pop("warmup_slot_ids", None)
    http_launch_service["parallel_slots"] = http_launch_service.pop(
        "server_parallel_slots", None
    )
    if (
        http_launch_contract.get("schema_version") != 1
        or http_launch_contract.get("experiment_id") != "E7c"
        or http_launch_inputs.get("runtime_manifest_sha256")
        != EXPECTED_HASHES["results/manifests/e7b-30695349303.json"]
        or http_launch_inputs.get("runtime_contract_sha256")
        != EXPECTED_HASHES["configs/runtime-b10216-http-service.json"]
        or http_launch_contract.get("request") != fast_launch_contract.get("request")
        or http_launch_service != http_runtime_contract.get("service")
        or http_launch_contract.get("acceptance", {}).get(
            "forbidden_runtime_dependency_basenames"
        )
        != ["libcrypto.so.3", "libssl.so.3"]
        or http_launch_contract.get("selection_policy", {}).get(
            "weighted_score_used"
        )
        is not False
    ):
        raise ValueError("frozen E7c launch integration differs from E7b")

    http_launch = load_object(ROOT / "results/manifests/e7c-30696606993.json")
    http_launch_quality = http_launch.get("quality", {})
    http_launch_performance = http_launch.get("performance", {})
    http_launch_runtime = http_launch.get("runtime_provenance", {})
    http_launch_source = http_launch.get("source", {})
    http_launch_validation = http_launch.get("validation", {})
    http_launch_dependencies = http_launch_runtime.get(
        "dynamic_dependency_basenames", []
    )
    if (
        http_launch.get("status")
        != "valid_http_dependency_pruned_launch_integration"
        or http_launch.get("provenance", {}).get("github_run_id")
        != "30696606993"
        or http_launch.get("platform", {}).get("architecture") != "aarch64"
        or http_launch.get("selection", {}).get("candidate")
        != http_runtime_contract.get("selected_candidate")
        or http_launch.get("selection", {}).get("runtime_commit")
        != http_runtime_contract.get("runtime", {}).get("selected_commit")
        or http_launch_quality.get("correct") != 23
        or http_launch_quality.get("total") != 30
        or http_launch_quality.get("exact_selected_predictions") is not True
        or http_launch_quality.get("reference_prediction_mismatches") != 0
        or http_launch_quality.get("request_failures") != 0
        or http_launch_quality.get(
            "cached_prefix_observed_in_every_measured_request"
        )
        is not True
        or http_launch_performance.get("ready_ms", 99_999) > 15_000
        or http_launch_performance.get("maximum_rss_kib", 99_999_999)
        > 8_388_608
        or http_launch_runtime.get("runtime_manifest_sha256")
        != EXPECTED_HASHES["results/manifests/e7b-30695349303.json"]
        or http_launch_runtime.get("runtime_contract_sha256")
        != EXPECTED_HASHES["configs/runtime-b10216-http-service.json"]
        or http_launch_runtime.get("source_diff_sha256")
        != EXPECTED_HASHES["patches/llama.cpp/b10216/e6f-current-series.patch"]
        or http_launch_source.get("dynamic_dependency_basenames")
        != http_launch_dependencies
        or set(http_launch_dependencies).intersection(
            {"libcrypto.so.3", "libssl.so.3"}
        )
        or http_launch_validation.get(
            "http_dependency_pruned_launch_claim_allowed"
        )
        is not True
        or http_launch_validation.get("openssl_dependencies_absent") is not True
        or http_launch_validation.get("runtime_dependency_inventory_verified")
        is not True
        or http_launch_validation.get("live_server_executed_through_adapter")
        is not True
        or http_launch_validation.get("source_build_binary_bound") is not True
        or http_launch_validation.get("automatic_other_profile_promotion_allowed")
        is not False
        or http_launch_validation.get("energy_claim_allowed") is not False
        or http_launch_validation.get("weighted_score_used") is not False
    ):
        raise ValueError("retained HTTP-only launch differs from E7c evidence")

    final_comparison = load_object(
        ROOT / "results/manifests/e9a-30764802071.json"
    )
    final_contract = load_object(ROOT / "experiments/e9a_contract.json")
    final_hypothesis = final_comparison.get("hypothesis", {})
    final_performance = final_comparison.get("performance", {})
    earliest = final_performance.get("e5b_earliest", {})
    final = final_performance.get("e7c_final", {})
    earliest_dependencies = set(
        final_comparison.get("builds", {})
        .get("e5b_earliest", {})
        .get("dynamic_dependency_basenames", [])
    )
    final_dependencies = set(
        final_comparison.get("builds", {})
        .get("e7c_final", {})
        .get("dynamic_dependency_basenames", [])
    )
    if (
        final_comparison.get("status") != "valid_final_service_win"
        or final_comparison.get("contract") != final_contract
        or final_comparison.get("provenance", {}).get("github_run_id")
        != "30764802071"
        or final_comparison.get("platform", {}).get("architecture") != "aarch64"
        or final_comparison.get("platform", {}).get("logical_cpus") != 2
        or final_hypothesis.get("passed") is not True
        or final_hypothesis.get("throughput_ratio", 0) < 1.25
        or final_hypothesis.get("median_http_latency_ratio", 99) > 0.85
        or final_hypothesis.get("p95_http_latency_ratio", 99) > 0.85
        or final_hypothesis.get("cpu_seconds_per_request_ratio", 99) > 0.85
        or final_hypothesis.get("weighted_score_used") is not False
        or earliest.get("quality", {}).get("exact_selected_predictions") is not True
        or final.get("quality", {}).get("exact_selected_predictions") is not True
        or len(earliest.get("samples", [])) != 120
        or len(final.get("samples", [])) != 120
        or any(item.get("cached_tokens") != 0 for item in earliest.get("samples", []))
        or any(item.get("cached_tokens", 0) < 1 for item in final.get("samples", []))
        or not {"libcrypto.so.3", "libssl.so.3"}.issubset(earliest_dependencies)
        or {"libcrypto.so.3", "libssl.so.3"}.intersection(final_dependencies)
        or final_comparison.get("validation", {}).get(
            "single_mechanism_attribution_allowed"
        )
        is not False
        or final_comparison.get("validation", {}).get("energy_claim_allowed")
        is not False
    ):
        raise ValueError("retained final-service comparison differs from E9a")

    holdout_preflight = load_object(ROOT / "experiments/e9b_preflight_plan.json")
    holdout_tasks = holdout_preflight.get("planned_holdout", {}).get("tasks", [])
    if (
        holdout_preflight.get("state") != "planned_before_external_task_results"
        or holdout_preflight.get("harness", {}).get("commit")
        != "6d642546f4688648fced259eb3302efd36ece5af"
        or holdout_preflight.get("tokenizer", {}).get("revision")
        != "b35d4dfe56c142746f54dbd64f579faab2744308"
        or holdout_preflight.get("planned_holdout", {}).get("selected_before_results")
        is not True
        or holdout_preflight.get("planned_holdout", {}).get("samples_per_task") != 100
        or holdout_preflight.get("planned_holdout", {}).get(
            "admission_contract_rewrite_allowed"
        )
        is not False
        or holdout_preflight.get("planned_holdout", {}).get("minimum_accuracy_gate")
        is not None
        or [item.get("task") for item in holdout_tasks]
        != ["e9b_arc_easy", "e9b_hellaswag", "e9b_winogrande"]
        or [item.get("license") for item in holdout_tasks]
        != ["CC-BY-SA-4.0", "MIT", "Apache-2.0"]
        or holdout_preflight.get("acceptance", {}).get(
            "benchmark_task_results_allowed"
        )
        is not False
    ):
        raise ValueError("E9b task selection or preflight plan changed after freeze")

    holdout_blocker = load_object(
        ROOT / "results/manifests/e9b-preflight-30766707967.json"
    )
    if (
        holdout_blocker.get("status") != "blocked_api_prompt_logprobs"
        or holdout_blocker.get("provenance", {}).get("github_run_id")
        != "30766707967"
        or holdout_blocker.get("platform", {}).get("architecture") != "aarch64"
        or holdout_blocker.get("platform", {}).get("logical_cpus") != 2
        or holdout_blocker.get("frozen_plan", {}).get("sha256")
        != "ff492b46e512220abd2ea3135bd807881f5ac4e1f9c5ee8b9b77de31229f9cd0"
        or holdout_blocker.get("frozen_plan", {}).get(
            "external_task_results_observed"
        )
        is not False
        or holdout_blocker.get("completed_checks", {}).get(
            "tokenizer_probe_parity_reached_completion_stage"
        )
        is not True
        or holdout_blocker.get("blocker", {}).get("full_external_holdout_started")
        is not False
        or holdout_blocker.get("blocker", {}).get("exact_server_modification_allowed")
        is not False
        or holdout_blocker.get("decision", {}).get("e9b_full_evaluation")
        != "not_run"
        or holdout_blocker.get("decision", {}).get(
            "original_30_task_admission_contract_changed"
        )
        is not False
        or holdout_blocker.get("decision", {}).get("external_tasks_cherry_picked")
        is not False
    ):
        raise ValueError("retained E9b API blocker changed or gained task results")

    cache_generalization = load_object(ROOT / "experiments/e9c_contract.json")
    if (
        cache_generalization.get("experiment_id") != "E9c"
        or cache_generalization.get("service", {}).get("profile") != "e7c_final"
        or cache_generalization.get("service", {}).get("source_commit")
        != "876a4321163249c43ca4e986818fab5ab081f282"
        or cache_generalization.get("service", {}).get("openssl") is not False
        or cache_generalization.get("workload", {}).get("prefix_cardinalities")
        != [1, 2, 4]
        or cache_generalization.get("workload", {}).get("shared_prefix_tokens")
        != [16, 32, 64]
        or len(cache_generalization.get("workload", {}).get("measured_task_ids", []))
        != 16
        or cache_generalization.get("execution", {}).get(
            "total_fresh_process_cells"
        )
        != 36
        or cache_generalization.get("execution", {}).get(
            "total_measured_requests"
        )
        != 576
        or cache_generalization.get("validity", {}).get(
            "maximum_throughput_coefficient_of_variation"
        )
        != 0.05
        or cache_generalization.get("break_even", {}).get(
            "minimum_throughput_ratio"
        )
        != 1.05
        or cache_generalization.get("break_even", {}).get(
            "minimum_prompt_encode_speedup_ratio"
        )
        != 1.05
        or cache_generalization.get("break_even", {}).get("weighted_score_used")
        is not False
    ):
        raise ValueError("E9c bounded cache contract changed after freeze")

    cache_result = load_object(
        ROOT / "results/manifests/e9c-30770403695.json"
    )
    cache_validation = cache_result.get("validation", {})
    cache_points = cache_result.get("points", [])
    disabled_policy = {
        str(cardinality): {
            "eligible_shared_prefix_tokens": [],
            "mode": "disabled",
        }
        for cardinality in (1, 2, 4)
    }
    performance_gates = (
        "cache_mechanism_observed",
        "scheduler_dispersion_passed",
        "throughput_gate_passed",
        "prompt_encode_gate_passed",
        "p95_latency_gate_passed",
        "cpu_time_gate_passed",
        "zero_request_failures",
    )
    if (
        cache_result.get("status")
        != "valid_cache_generalization_output_regression"
        or cache_result.get("provenance", {}).get("github_run_id")
        != "30770403695"
        or cache_result.get("platform", {}).get("architecture") != "aarch64"
        or cache_result.get("platform", {}).get("logical_cpus") != 2
        or cache_validation.get("total_request_failures") != 0
        or cache_validation.get("total_invalid_prediction_responses") != 204
        or cache_validation.get("total_reference_prediction_mismatches") != 252
        or cache_validation.get("total_paired_cache_output_mismatches") != 12
        or cache_validation.get("exact_outputs") is not False
        or cache_validation.get("energy_claim_allowed") is not False
        or cache_result.get("any_cache_eligible_point") is not False
        or cache_result.get("cache_enablement_policy_by_prefix_cardinality")
        != disabled_policy
        or len(cache_points) != 9
        or any(point.get("eligible") is not False for point in cache_points)
        or any(
            point.get("gates", {}).get(gate) is not True
            for point in cache_points
            for gate in performance_gates
        )
        or any(
            point.get("gates", {}).get("exact_reference_outputs") is not False
            for point in cache_points
        )
    ):
        raise ValueError("retained E9c output-regression boundary changed")

    patch_contract = load_object(ROOT / "experiments/e9d_contract.json")
    patch_entries = patch_contract.get("mail_series", {}).get("patches", [])
    if (
        patch_contract.get("experiment_id") != "E9d"
        or patch_contract.get("upstream", {}).get("commit")
        != "876a4321163249c43ca4e986818fab5ab081f282"
        or patch_contract.get("mail_series", {}).get("aggregate_diff_sha256")
        != "e11cdd41091d5d76b973c67ffcc04429760fbef58c7a2bc971947b80900a9893"
        or len(patch_entries) != 3
        or any(
            "Signed-off-by: Arshdeep Singh <arshgill6120@gmail.com>"
            not in (ROOT / entry["path"]).read_text(encoding="utf-8")
            for entry in patch_entries
        )
        or patch_contract.get("toolchains", {}).get("gcc", {}).get("cc")
        != "/usr/bin/gcc-14"
        or patch_contract.get("toolchains", {}).get("clang", {}).get("cc")
        != "/usr/bin/clang-18"
        or patch_contract.get("sanitizers", {}).get("address") is not True
        or patch_contract.get("sanitizers", {}).get("undefined") is not True
        or patch_contract.get("claim_boundary", {}).get("upstream_pr_opened")
        is not False
        or patch_contract.get("claim_boundary", {}).get(
            "performance_claim_added"
        )
        is not False
    ):
        raise ValueError("E9d local patch-series contract changed after freeze")

    local_assets = verify_demo()
    print("Pareto64 submission verification passed")
    print(f"selected candidate: {plan['selected']['name']}")
    print(f"selected accuracy: {plan['selected']['metrics']['minimum_accuracy']:.4f}")
    print(f"verified evidence files: {len(EXPECTED_HASHES)}")
    print(f"verified demo links/assets: {local_assets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
