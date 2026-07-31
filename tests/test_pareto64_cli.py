from __future__ import annotations

import unittest
from unittest.mock import patch

from pareto64.cli import parse_args


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

    def test_prompt_cache_is_default_with_explicit_escape_hatch(self) -> None:
        with patch("sys.argv", self.launch_arguments()):
            arguments = parse_args()
            self.assertTrue(arguments.prompt_cache)
            self.assertEqual(256, arguments.context_per_slot)
            self.assertIsNone(arguments.batch_size)
            self.assertIsNone(arguments.micro_batch_size)
        with patch("sys.argv", self.launch_arguments() + ["--no-prompt-cache"]):
            self.assertFalse(parse_args().prompt_cache)

    def test_launch_accepts_bounded_context_and_kv_profile(self) -> None:
        with patch(
            "sys.argv",
            self.launch_arguments()
            + [
                "--context-per-slot",
                "256",
                "--kv-cache-type-k",
                "q8_0",
                "--kv-cache-type-v",
                "f16",
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
        self.assertEqual(128, arguments.batch_size)
        self.assertEqual(128, arguments.micro_batch_size)
        self.assertEqual("q8_0", arguments.kv_cache_type_k)
        self.assertEqual("f16", arguments.kv_cache_type_v)
        self.assertEqual(3, arguments.log_verbosity)


if __name__ == "__main__":
    unittest.main()
