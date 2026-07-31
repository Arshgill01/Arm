from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .planner import build_plan, load_object
from .runtime import prepare_launch, server_version, write_recipe
from .server import DEFAULT_ACCEPT_BACKLOG, PlannerHTTPServer, PlannerState


def resolve_batch_profile(
    batch_size: int | None,
    micro_batch_size: int | None,
) -> tuple[int | None, int | None]:
    if batch_size is None and micro_batch_size is None:
        return 64, 64
    return batch_size, micro_batch_size


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
    launch.add_argument(
        "--context-per-slot",
        type=int,
        default=256,
        help="per-slot context (default: 256, selected by native E5e evidence)",
    )
    launch.add_argument(
        "--kv-cache-type-k",
        choices=("f16", "q8_0", "q4_0"),
        default="f16",
    )
    launch.add_argument(
        "--kv-cache-type-v",
        choices=("f16",),
        default="f16",
    )
    launch.add_argument(
        "--flash-attention",
        choices=("auto", "on", "off"),
        default="auto",
        help="flash-attention mode (default: auto)",
    )
    launch.add_argument(
        "--batch-size",
        type=int,
        help="logical prompt batch size (default: 64, selected by native E5f)",
    )
    launch.add_argument(
        "--micro-batch-size",
        type=int,
        help="physical prompt batch size (default: 64; set both sizes together)",
    )
    launch.add_argument("--log-verbosity", type=int)
    launch.add_argument(
        "--prompt-cache",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="reuse a shared prompt prefix; validated and enabled by default",
    )
    launch.add_argument(
        "--weight-repack",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="use Arm-optimized repacked weights; enabled by default",
    )
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
        batch_size, micro_batch_size = resolve_batch_profile(
            arguments.batch_size,
            arguments.micro_batch_size,
        )
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
            prompt_cache=arguments.prompt_cache,
            context_per_slot=arguments.context_per_slot,
            kv_cache_type_k=arguments.kv_cache_type_k,
            kv_cache_type_v=arguments.kv_cache_type_v,
            batch_size=batch_size,
            micro_batch_size=micro_batch_size,
            flash_attention=arguments.flash_attention,
            weight_repack=arguments.weight_repack,
            log_verbosity=arguments.log_verbosity,
        )
        write_recipe(arguments.recipe_output, recipe)
        print(arguments.recipe_output, flush=True)
        if arguments.dry_run:
            return 0
        argv = recipe["runtime"]["argv"]
        os.execv(argv[0], argv)
        raise AssertionError("execv returned unexpectedly")
    raise AssertionError(f"unsupported command {arguments.command}")
