from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .planner import build_plan, load_object
from .runtime import prepare_launch, server_version, write_recipe
from .server import DEFAULT_ACCEPT_BACKLOG, PlannerHTTPServer, PlannerState


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
        "--backlog",
        type=int,
        default=DEFAULT_ACCEPT_BACKLOG,
        help="TCP accept backlog for fresh concurrent connections",
    )
    serve.add_argument(
        "--max-requests",
        type=int,
        default=0,
        help="stop after this many requests; zero serves until interrupted",
    )
    launch = commands.add_parser(
        "launch", help="verify and launch the selected llama.cpp inference runtime"
    )
    launch.add_argument("--manifest", type=Path, required=True)
    launch.add_argument("--constraints", type=Path, required=True)
    launch.add_argument("--models", type=Path, required=True)
    launch.add_argument("--contract", type=Path, required=True)
    launch.add_argument("--model-root", type=Path, required=True)
    launch.add_argument("--llama-server", type=Path, required=True)
    launch.add_argument("--recipe-output", type=Path, required=True)
    launch.add_argument("--host", default="127.0.0.1")
    launch.add_argument("--port", type=int, default=8081)
    launch.add_argument("--parallel", type=int, default=1)
    launch.add_argument("--dry-run", action="store_true")
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
        if arguments.backlog <= 0 or arguments.backlog > 4096:
            raise ValueError("--backlog must be between 1 and 4096")
        state = PlannerState.from_paths(arguments.manifest, arguments.constraints)
        server = PlannerHTTPServer(
            (arguments.host, arguments.port),
            state,
            arguments.max_requests,
            arguments.backlog,
        )
        host, port = server.server_address
        print(
            f"Pareto64 listening on http://{host}:{port} backlog={arguments.backlog}",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if arguments.command == "launch":
        recipe = prepare_launch(
            manifest=load_object(arguments.manifest),
            constraints=load_object(arguments.constraints),
            models=load_object(arguments.models),
            contract=load_object(arguments.contract),
            manifest_path=arguments.manifest,
            constraints_path=arguments.constraints,
            models_path=arguments.models,
            contract_path=arguments.contract,
            model_root=arguments.model_root,
            server_path=arguments.llama_server,
            version_output=server_version(arguments.llama_server),
            host=arguments.host,
            port=arguments.port,
            parallel=arguments.parallel,
        )
        write_recipe(arguments.recipe_output, recipe)
        print(arguments.recipe_output, flush=True)
        if arguments.dry_run:
            return 0
        argv = recipe["runtime"]["argv"]
        os.execv(argv[0], argv)
        raise AssertionError("execv returned unexpectedly")
    raise AssertionError(f"unsupported command {arguments.command}")
