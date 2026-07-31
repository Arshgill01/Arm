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
    "results/manifests/e6b-30640282768.json": (
        "e870ad9cf7b7d1f89f0fa745383f555d54f62b3caf2fc635cbcb76ca4ef7e210"
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

    local_assets = verify_demo()
    print("Pareto64 submission verification passed")
    print(f"selected candidate: {plan['selected']['name']}")
    print(f"selected accuracy: {plan['selected']['metrics']['minimum_accuracy']:.4f}")
    print(f"verified evidence files: {len(EXPECTED_HASHES)}")
    print(f"verified demo links/assets: {local_assets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
