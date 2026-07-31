from __future__ import annotations

import argparse
import json
from pathlib import Path

from .planner import build_plan, load_object
from .server import PlannerHTTPServer, PlannerState


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pareto64")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser(
        "plan", help="select a quality/SLO-constrained deployment"
    )
    plan.add_argument("--manifest", type=Path, required=True)
    plan.add_argument("--constraints", type=Path, required=True)
    plan.add_argument("--output", type=Path)
    serve = commands.add_parser("serve", help="serve the bounded planning API")
    serve.add_argument("--manifest", type=Path, required=True)
    serve.add_argument("--constraints", type=Path, required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument(
        "--max-requests",
        type=int,
        default=0,
        help="stop after this many requests; zero serves until interrupted",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    if arguments.command == "plan":
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
    if arguments.command == "serve":
        if arguments.max_requests < 0:
            raise ValueError("--max-requests must be non-negative")
        state = PlannerState.from_paths(arguments.manifest, arguments.constraints)
        server = PlannerHTTPServer(
            (arguments.host, arguments.port), state, arguments.max_requests
        )
        host, port = server.server_address
        print(f"Pareto64 listening on http://{host}:{port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    raise AssertionError(f"unsupported command {arguments.command}")
