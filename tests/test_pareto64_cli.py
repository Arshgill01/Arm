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
            self.assertTrue(parse_args().prompt_cache)
        with patch("sys.argv", self.launch_arguments() + ["--no-prompt-cache"]):
            self.assertFalse(parse_args().prompt_cache)


if __name__ == "__main__":
    unittest.main()
