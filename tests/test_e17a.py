import unittest
from pathlib import Path

from experiments.e17a_kv_preflight_freeze import build_contract
from experiments.e17a_kv_preflight_ingest import validate_recipe


class E17aTests(unittest.TestCase):
    def test_freeze_is_bounded_and_quality_independent(self) -> None:
        contract = build_contract(Path("."))
        self.assertEqual(
            contract["execution"]["order"],
            ["f16_f16", "q8_0_q8_0", "q4_0_q4_0"],
        )
        self.assertEqual(contract["quality_preflight"]["task_ids"][-1], "systems-04")
        self.assertFalse(
            contract["quality_preflight"]["quality_or_performance_result_may_select_successor"]
        )
        self.assertFalse(contract["decision"]["preflight_makes_performance_claim"])

    def test_recipe_requires_quantized_v_and_flash_on(self) -> None:
        contract = {
            "selected": {
                "candidate": "model",
                "model_sha256": "abc",
                "model_size_bytes": 123,
            },
            "execution": {
                "configurations": {
                    "q8_0_q8_0": {
                        "context_size": 1024,
                        "kv_cache_type_k": "q8_0",
                        "kv_cache_type_v": "q8_0",
                        "flash_attention": "on",
                    }
                }
            },
        }
        recipe = {
            "experiment_id": "E17a",
            "configuration": "q8_0_q8_0",
            "server_path": "/runtime/runtime-files/bin/llama-server",
            "model": {"path": "/model.gguf", "sha256": "abc", "size_bytes": 123},
            "service": contract["execution"]["configurations"]["q8_0_q8_0"],
        }
        recipe["argv"] = [
            recipe["server_path"],
            "--model", "/model.gguf",
            "--alias", "model",
            "--threads", "4",
            "--threads-batch", "4",
            "--ctx-size", "1024",
            "--cache-type-k", "q8_0",
            "--cache-type-v", "q8_0",
            "--flash-attn", "on",
            "--parallel", "1",
            "--cont-batching",
            "--host", "127.0.0.1",
            "--port", "18081",
            "--no-webui",
            "--metrics",
            "--slots",
            "--jinja",
            "--temp", "0.0",
            "--seed", "424242",
            "--log-colors", "off",
            "--log-verbosity", "4",
            "--batch-size", "1024",
            "--ubatch-size", "512",
        ]
        validate_recipe(recipe, contract)
        recipe["argv"][recipe["argv"].index("--flash-attn") + 1] = "auto"
        with self.assertRaisesRegex(ValueError, "differs from the frozen contract"):
            validate_recipe(recipe, contract)


if __name__ == "__main__":
    unittest.main()
