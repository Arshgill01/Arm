from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.e7a_ingest import validate_runtime_closure
from experiments.e7a_runtime_closure import (
    capture_runtime_closure,
    parse_ldd_paths,
    sha256_file,
)


class E7aRuntimeClosureTests(unittest.TestCase):
    def test_ldd_parser_rejects_missing_dependencies(self) -> None:
        self.assertEqual(
            [Path("/tmp/liblocal.so"), Path("/lib/ld-linux-aarch64.so.1")],
            parse_ldd_paths(
                "liblocal.so => /tmp/liblocal.so (0x1)\n"
                "/lib/ld-linux-aarch64.so.1 (0x2)\n"
            ),
        )
        with self.assertRaisesRegex(ValueError, "unresolved runtime dependency"):
            parse_ldd_paths("libmissing.so => not found\n")

    def test_closure_copies_and_hashes_only_build_local_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            server = build / "bin/llama-server"
            library = build / "bin/libllama.so"
            system = root / "system/libc.so"
            for path, payload in (
                (server, b"server"),
                (library, b"library"),
                (system, b"system"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            server.chmod(0o755)
            output = root / "evidence/runtime-closure.json"
            copy_dir = output.parent / "runtime-files"
            closure = capture_runtime_closure(
                server,
                build,
                copy_dir,
                output,
                ldd_output=(
                    f"libllama.so => {library} (0x1)\n"
                    f"libc.so.6 => {system} (0x2)\n"
                ),
            )
            self.assertEqual(2, closure["file_count"])
            self.assertEqual(13, closure["total_size_bytes"])
            self.assertEqual(build.resolve().as_posix(), closure["build_root"])
            self.assertEqual(server.resolve().as_posix(), closure["server_path"])
            self.assertEqual(
                [True, False],
                [item["build_local"] for item in closure["runtime_dependencies"]],
            )
            self.assertEqual(
                ["bin/libllama.so", "bin/llama-server"],
                [item["relative_path"] for item in closure["files"]],
            )
            for item in closure["files"]:
                copied = output.parent / item["artifact_relative_path"]
                self.assertEqual(item["sha256"], sha256_file(copied))
            output.write_text(json.dumps(closure))
            self.assertEqual(closure, validate_runtime_closure(output))

            closure["runtime_dependencies"][0]["build_local"] = False
            output.write_text(json.dumps(closure))
            with self.assertRaisesRegex(ValueError, "dependency record differs"):
                validate_runtime_closure(output)


if __name__ == "__main__":
    unittest.main()
