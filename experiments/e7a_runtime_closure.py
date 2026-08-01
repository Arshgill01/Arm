#!/usr/bin/env python3
"""Capture the transitive build-local runtime files used by llama-server."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_ldd_paths(output: str) -> list[Path]:
    paths: list[Path] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("linux-vdso"):
            continue
        if "=> not found" in line:
            raise ValueError(f"unresolved runtime dependency: {line}")
        if "=>" in line:
            value = line.split("=>", 1)[1].strip().split(" ", 1)[0]
        else:
            value = line.split(" ", 1)[0]
        if value.startswith("/"):
            paths.append(Path(value))
    return paths


def capture_runtime_closure(
    server_path: Path,
    build_root: Path,
    copy_dir: Path,
    output_path: Path,
    *,
    ldd_output: str | None = None,
) -> dict:
    server = server_path.resolve()
    build = build_root.resolve()
    output_parent = output_path.resolve().parent
    resolved_copy_dir = copy_dir.resolve()
    if (
        not build.is_dir()
        or not server.is_file()
        or not os.access(server, os.X_OK)
        or not server.is_relative_to(build)
        or not resolved_copy_dir.is_relative_to(output_parent)
    ):
        raise ValueError("runtime closure paths are not bound to the build/artifact")
    if ldd_output is None:
        result = subprocess.run(
            ["ldd", str(server)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "LC_ALL": "C"},
        )
        if result.returncode != 0:
            raise ValueError(f"ldd failed: {result.stderr.strip()}")
        ldd_output = result.stdout

    local_paths = {server}
    runtime_dependencies = []
    for dependency in parse_ldd_paths(ldd_output):
        resolved = dependency.resolve()
        build_local = resolved.is_relative_to(build)
        runtime_dependencies.append(
            {
                "ldd_path": os.fspath(dependency),
                "resolved_path": os.fspath(resolved),
                "build_local": build_local,
            }
        )
        if build_local:
            if not resolved.is_file():
                raise ValueError(f"build-local runtime dependency is missing: {resolved}")
            local_paths.add(resolved)

    files = []
    total_size = 0
    for source in sorted(local_paths, key=lambda path: path.relative_to(build).as_posix()):
        relative = source.relative_to(build)
        artifact_path = resolved_copy_dir / relative
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, artifact_path)
        size = source.stat().st_size
        digest = sha256_file(source)
        if artifact_path.stat().st_size != size or sha256_file(artifact_path) != digest:
            raise ValueError("copied runtime dependency differs from build output")
        total_size += size
        files.append(
            {
                "relative_path": relative.as_posix(),
                "artifact_relative_path": artifact_path.relative_to(
                    output_parent
                ).as_posix(),
                "size_bytes": size,
                "sha256": digest,
            }
        )
    if not files or server.relative_to(build).as_posix() not in {
        item["relative_path"] for item in files
    }:
        raise ValueError("runtime closure does not contain the selected server")
    return {
        "schema_version": 1,
        "build_root": os.fspath(build),
        "server_path": os.fspath(server),
        "server_relative_path": server.relative_to(build).as_posix(),
        "runtime_dependencies": runtime_dependencies,
        "files": files,
        "file_count": len(files),
        "total_size_bytes": total_size,
        "system_dependencies_excluded": True,
        "ldd_output": ldd_output,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--copy-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    closure = capture_runtime_closure(
        arguments.server,
        arguments.build_root,
        arguments.copy_dir,
        arguments.output,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(closure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
