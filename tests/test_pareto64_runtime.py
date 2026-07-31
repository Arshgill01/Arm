from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pareto64.planner import load_object
from pareto64.runtime import prepare_launch, validate_server_version


ROOT = Path(__file__).resolve().parents[1]


class Pareto64RuntimeTests(unittest.TestCase):
    def test_selected_package_produces_exact_launch_recipe(self) -> None:
        manifest = load_object(ROOT / "results/manifests/e3f-30656151957.json")
        constraints = load_object(ROOT / "configs/cloud-quality.json")
        models = load_object(ROOT / "experiments/e3f_models.json")
        contract = load_object(ROOT / "experiments/e3f_contract.json")
        selected = "ministral3_3b_q4_k_m"
        payload = b"test model"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "manifest.json"
            constraints_path = root / "constraints.json"
            models_path = root / "models.json"
            contract_path = root / "contract.json"
            server_path = root / "llama-server"
            model_root = root / "model-root"
            model_path = model_root / selected / "model.gguf"
            model_path.parent.mkdir(parents=True)
            model_path.write_bytes(payload)
            server_path.write_text("#!/bin/sh\nexit 0\n")
            server_path.chmod(0o755)
            models = copy.deepcopy(models)
            models["variants"][selected]["entrypoint"] = "model.gguf"
            models["variants"][selected]["files"] = [
                {
                    "path": "model.gguf",
                    "size_bytes": len(payload),
                    "sha256": digest,
                }
            ]
            manifest = copy.deepcopy(manifest)
            manifest["application"][selected]["package_size_bytes"] = len(payload)
            manifest_path.write_text(json.dumps(manifest))
            constraints_path.write_text(json.dumps(constraints))
            models_path.write_text(json.dumps(models))
            contract_path.write_text(json.dumps(contract))
            recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=manifest_path,
                constraints_path=constraints_path,
                models_path=models_path,
                contract_path=contract_path,
                model_root=model_root,
                server_path=server_path,
                version_output="version b10208 (9d9a6d29f)",
                host="127.0.0.1",
                port=18081,
                parallel=2,
            )
            self.assertEqual("ready_to_launch", recipe["status"])
            self.assertEqual(selected, recipe["selected_candidate"])
            self.assertEqual(digest, recipe["model"]["files"][0]["sha256"])
            self.assertEqual(4096, recipe["runtime"]["context_total"])
            self.assertIn("--cont-batching", recipe["runtime"]["argv"])
            self.assertIn("--cache-prompt", recipe["runtime"]["argv"])
            self.assertTrue(recipe["runtime"]["prompt_cache"])
            self.assertFalse(recipe["weighted_score_used"])

            uncached_recipe = prepare_launch(
                manifest=manifest,
                constraints=constraints,
                models=models,
                contract=contract,
                manifest_path=manifest_path,
                constraints_path=constraints_path,
                models_path=models_path,
                contract_path=contract_path,
                model_root=model_root,
                server_path=server_path,
                version_output="version b10208 (9d9a6d29f)",
                host="127.0.0.1",
                port=18081,
                parallel=1,
                prompt_cache=False,
            )
            self.assertIn("--no-cache-prompt", uncached_recipe["runtime"]["argv"])
            self.assertNotIn("--cache-prompt", uncached_recipe["runtime"]["argv"])
            self.assertFalse(uncached_recipe["runtime"]["prompt_cache"])

    def test_model_hash_mismatch_fails_closed(self) -> None:
        manifest = load_object(ROOT / "results/manifests/e3f-30656151957.json")
        constraints = load_object(ROOT / "configs/cloud-quality.json")
        models = load_object(ROOT / "experiments/e3f_models.json")
        contract = load_object(ROOT / "experiments/e3f_contract.json")
        selected = "ministral3_3b_q4_k_m"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model_root = root / "models"
            model_path = model_root / selected / "model.gguf"
            model_path.parent.mkdir(parents=True)
            model_path.write_bytes(b"wrong")
            models = copy.deepcopy(models)
            models["variants"][selected]["entrypoint"] = "model.gguf"
            models["variants"][selected]["files"] = [
                {"path": "model.gguf", "size_bytes": 5, "sha256": "0" * 64}
            ]
            manifest = copy.deepcopy(manifest)
            manifest["application"][selected]["package_size_bytes"] = 5
            paths = {}
            for name, value in (
                ("manifest", manifest),
                ("constraints", constraints),
                ("models", models),
                ("contract", contract),
            ):
                path = root / f"{name}.json"
                path.write_text(json.dumps(value))
                paths[name] = path
            server = root / "llama-server"
            server.write_text("")
            server.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=paths["manifest"],
                    constraints_path=paths["constraints"],
                    models_path=paths["models"],
                    contract_path=paths["contract"],
                    model_root=model_root,
                    server_path=server,
                    version_output="9d9a6d29f",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                )

    def test_runtime_commit_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "version differs"):
            validate_server_version("different build", "9d9a6d29f6b981cc7f41983d26e56485c6af1811")

    def test_model_symlink_cannot_escape_candidate_directory(self) -> None:
        manifest = load_object(ROOT / "results/manifests/e3f-30656151957.json")
        constraints = load_object(ROOT / "configs/cloud-quality.json")
        models = load_object(ROOT / "experiments/e3f_models.json")
        contract = load_object(ROOT / "experiments/e3f_contract.json")
        selected = "ministral3_3b_q4_k_m"
        payload = b"model outside the declared root"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.gguf"
            outside.write_bytes(payload)
            model_root = root / "models"
            candidate_root = model_root / selected
            candidate_root.mkdir(parents=True)
            (candidate_root / "model.gguf").symlink_to(outside)
            models = copy.deepcopy(models)
            models["variants"][selected]["entrypoint"] = "model.gguf"
            models["variants"][selected]["files"] = [
                {
                    "path": "model.gguf",
                    "size_bytes": len(payload),
                    "sha256": digest,
                }
            ]
            manifest = copy.deepcopy(manifest)
            manifest["application"][selected]["package_size_bytes"] = len(payload)
            paths = {}
            for name, value in (
                ("manifest", manifest),
                ("constraints", constraints),
                ("models", models),
                ("contract", contract),
            ):
                path = root / f"{name}.json"
                path.write_text(json.dumps(value))
                paths[name] = path
            with self.assertRaisesRegex(ValueError, "outside the candidate"):
                prepare_launch(
                    manifest=manifest,
                    constraints=constraints,
                    models=models,
                    contract=contract,
                    manifest_path=paths["manifest"],
                    constraints_path=paths["constraints"],
                    models_path=paths["models"],
                    contract_path=paths["contract"],
                    model_root=model_root,
                    server_path=root / "llama-server",
                    version_output="9d9a6d29f",
                    host="127.0.0.1",
                    port=18081,
                    parallel=1,
                )


if __name__ == "__main__":
    unittest.main()
