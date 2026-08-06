from __future__ import annotations

import unittest
from unittest.mock import patch

from pareto64.cli import parse_args, resolve_batch_profile


class Pareto64CLITests(unittest.TestCase):
    def launch_arguments(self) -> list[str]:
        return [
            "pareto64",
            "launch",
            "--manifest",
            "manifest.json",
            "--constraints",
            "policy.json",
            "--models",
            "models.json",
            "--contract",
            "contract.json",
            "--model-root",
            "models",
            "--llama-server",
            "llama-server",
            "--recipe-output",
            "recipe.json",
        ]

    def test_prompt_cache_and_repack_have_bounded_controls(self) -> None:
        with patch("sys.argv", self.launch_arguments()):
            arguments = parse_args()
            self.assertTrue(arguments.prompt_cache)
            self.assertEqual(256, arguments.context_per_slot)
            self.assertIsNone(arguments.batch_size)
            self.assertIsNone(arguments.micro_batch_size)
            self.assertEqual("auto", arguments.flash_attention)
            self.assertIsNone(arguments.weight_repack)
            self.assertIsNone(arguments.threads)
        with patch("sys.argv", self.launch_arguments() + ["--no-prompt-cache"]):
            self.assertFalse(parse_args().prompt_cache)
        with patch("sys.argv", self.launch_arguments() + ["--no-weight-repack"]):
            self.assertFalse(parse_args().weight_repack)
        with patch("sys.argv", self.launch_arguments() + ["--weight-repack"]):
            self.assertTrue(parse_args().weight_repack)

    def test_launch_accepts_measured_service_policy_paths(self) -> None:
        with patch(
            "sys.argv",
            self.launch_arguments()
            + [
                "--service-manifest",
                "e5h.json",
                "--service-constraints",
                "service-memory.json",
            ],
        ):
            arguments = parse_args()
        self.assertEqual("e5h.json", str(arguments.service_manifest))
        self.assertEqual("service-memory.json", str(arguments.service_constraints))

    def test_launch_accepts_explicit_runtime_upgrade_paths(self) -> None:
        with patch(
            "sys.argv",
            self.launch_arguments()
            + [
                "--runtime-manifest",
                "e6f.json",
                "--runtime-contract",
                "runtime.json",
                "--llama-source-root",
                "llama.cpp",
                "--llama-build-root",
                "llama.cpp-build",
            ],
        ):
            arguments = parse_args()
        self.assertEqual("e6f.json", str(arguments.runtime_manifest))
        self.assertEqual("runtime.json", str(arguments.runtime_contract))
        self.assertEqual("llama.cpp", str(arguments.llama_source_root))
        self.assertEqual("llama.cpp-build", str(arguments.llama_build_root))

    def test_launch_accepts_bounded_context_and_kv_profile(self) -> None:
        with patch(
            "sys.argv",
            self.launch_arguments()
            + [
                "--context-per-slot",
                "256",
                "--threads",
                "3",
                "--kv-cache-type-k",
                "q8_0",
                "--kv-cache-type-v",
                "f16",
                "--flash-attention",
                "off",
                "--batch-size",
                "128",
                "--micro-batch-size",
                "128",
                "--log-verbosity",
                "3",
            ],
        ):
            arguments = parse_args()
        self.assertEqual(256, arguments.context_per_slot)
        self.assertEqual(3, arguments.threads)
        self.assertEqual(128, arguments.batch_size)
        self.assertEqual(128, arguments.micro_batch_size)
        self.assertEqual("q8_0", arguments.kv_cache_type_k)
        self.assertEqual("f16", arguments.kv_cache_type_v)
        self.assertEqual("off", arguments.flash_attention)
        self.assertEqual(3, arguments.log_verbosity)

    def test_unflagged_launch_resolves_selected_batch_pair(self) -> None:
        self.assertEqual((64, 64), resolve_batch_profile(None, None))
        self.assertEqual((128, None), resolve_batch_profile(128, None))

    def test_service_plan_accepts_evidence_and_policy_paths(self) -> None:
        with patch(
            "sys.argv",
            [
                "pareto64",
                "service-plan",
                "--manifest",
                "e5h.json",
                "--constraints",
                "service-memory.json",
                "--output",
                "service-plan.json",
            ],
        ):
            arguments = parse_args()
        self.assertEqual("service-plan", arguments.command)
        self.assertEqual("e5h.json", str(arguments.manifest))
        self.assertEqual("service-memory.json", str(arguments.constraints))
        self.assertEqual("service-plan.json", str(arguments.output))

    def test_sidecar_product_commands_are_explicit_and_bounded(self) -> None:
        common = [
            "--contract",
            "e16c.json",
            "--evidence",
            "e16c-result.json",
            "--model",
            "model.gguf",
            "--llama-server",
            "runtime/bin/llama-server",
            "--sidecar",
            "weights.sidecar",
            "--index",
            "weights.index.json",
        ]
        with patch(
            "sys.argv",
            [
                "pareto64",
                "sidecar-prepack",
                *common,
                "--receipt",
                "receipt.json",
                "--lifecycle-dir",
                "lifecycle",
                "--scratch-root",
                "scratch",
            ],
        ):
            prepack = parse_args()
        self.assertEqual("sidecar-prepack", prepack.command)
        self.assertEqual(18081, prepack.port)
        self.assertEqual(120.0, prepack.readiness_timeout)
        with patch(
            "sys.argv",
            [
                "pareto64",
                "sidecar-launch",
                *common,
                "--receipt",
                "receipt.json",
                "--plan-output",
                "plan.json",
                "--dry-run",
            ],
        ):
            launch = parse_args()
        self.assertEqual("sidecar-launch", launch.command)
        self.assertEqual(2, launch.workers)
        self.assertEqual(120.0, launch.readiness_timeout)
        self.assertTrue(launch.dry_run)

    def test_unified_deploy_command_exposes_gateway_and_lifecycle_controls(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "pareto64",
                "deploy",
                "--contract",
                "e16c.json",
                "--evidence",
                "e16c-result.json",
                "--model",
                "model.gguf",
                "--llama-server",
                "runtime/bin/llama-server",
                "--sidecar",
                "weights.sidecar",
                "--index",
                "weights.index.json",
                "--sidecar-receipt",
                "sidecar-receipt.json",
                "--registry",
                "certificates.json",
                "--plan-output",
                "deployment-plan.json",
                "--deployment-receipt",
                "deployment-receipt.json",
                "--workers",
                "4",
                "--revalidate-every",
                "16",
                "--dry-run",
            ],
        ):
            arguments = parse_args()
        self.assertEqual("deploy", arguments.command)
        self.assertEqual(4, arguments.workers)
        self.assertEqual("shared", arguments.mode)
        self.assertEqual(16, arguments.revalidate_every)
        self.assertEqual(18080, arguments.gateway_port)
        self.assertTrue(arguments.dry_run)

    def test_unified_deploy_accepts_a_normal_control_without_sidecar_paths(
        self,
    ) -> None:
        with patch(
            "sys.argv",
            [
                "pareto64",
                "deploy",
                "--mode",
                "normal",
                "--contract",
                "e16c.json",
                "--evidence",
                "e16c-result.json",
                "--model",
                "model.gguf",
                "--llama-server",
                "runtime/bin/llama-server",
                "--registry",
                "certificates.json",
                "--plan-output",
                "deployment-plan.json",
                "--deployment-receipt",
                "deployment-receipt.json",
            ],
        ):
            arguments = parse_args()
        self.assertEqual("normal", arguments.mode)
        self.assertIsNone(arguments.sidecar)

    def test_gateway_command_requires_identity_workers_and_registry(self) -> None:
        with patch(
            "sys.argv",
            [
                "pareto64",
                "gateway",
                "--identity",
                "identity.json",
                "--worker-origin",
                "http://127.0.0.1:18081",
                "--registry",
                "certificates.json",
            ],
        ):
            arguments = parse_args()
        self.assertEqual("gateway", arguments.command)
        self.assertEqual(["http://127.0.0.1:18081"], arguments.worker_origin)
        self.assertEqual(32, arguments.revalidate_every)


if __name__ == "__main__":
    unittest.main()
