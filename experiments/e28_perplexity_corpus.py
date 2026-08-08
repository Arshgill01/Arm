#!/usr/bin/env python3
"""Build the frozen E28 perplexity corpus from two exact E3 task-file copies."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = args.source.read_bytes()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload + payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
