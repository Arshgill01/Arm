from __future__ import annotations

import argparse
import json
from pathlib import Path

from .planner import build_plan, load_object


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pareto64")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser(
        "plan", help="select a quality/SLO-constrained deployment"
    )
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--constraints", type=Path, required=True)
    plan.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    if arguments.command != "plan":
        raise AssertionError(f"unsupported command {arguments.command}")
    result = build_plan(
        load_object(arguments.manifest),
        load_object(arguments.constraints),
        manifest_path=arguments.manifest,
        constraints_path=arguments.constraints,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
        print(arguments.output)
    else:
        print(rendered, end="")
    return 0
