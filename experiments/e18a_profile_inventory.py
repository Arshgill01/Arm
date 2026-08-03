#!/usr/bin/env python3
"""Inventory exact GCC PGO data files for E18a."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from experiments.e5b_ingest import sha256_file
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    from e5b_ingest import sha256_file


def build_inventory(directory: Path) -> dict:
    if not directory.is_dir():
        raise ValueError("E18a profile directory does not exist")
    files = []
    total_bytes = 0
    for path in sorted(directory.rglob("*.gcda")):
        relative = path.relative_to(directory).as_posix()
        size = path.stat().st_size
        if size <= 0:
            raise ValueError(f"E18a profile file is empty: {relative}")
        files.append(
            {"path": relative, "size_bytes": size, "sha256": sha256_file(path)}
        )
        total_bytes += size
    if len(files) < 20:
        raise ValueError("E18a profile training produced too few GCC data files")
    return {
        "schema_version": 1,
        "format": "GCC gcda",
        "file_count": len(files),
        "total_size_bytes": total_bytes,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = build_inventory(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"file_count": inventory["file_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
