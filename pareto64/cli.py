from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .certificate import CertificateStore
from .deploy import execute_deployment, prepare_deployment
from .gateway import GatewayHTTPServer, GatewayState
from .planner import build_plan, load_object
from .runtime import prepare_launch, server_version, write_recipe
from .server import DEFAULT_ACCEPT_BACKLOG, PlannerHTTPServer, PlannerState
from .service_planner import build_service_plan
from .sidecar import (
    cleanup_sidecar,
    execute_sidecar_group,
    prepack_sidecar,
    prepare_normal_launch,
    prepare_sidecar_launch,
    verify_product_sidecar,
    write_object,
)


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
    service_plan = commands.add_parser(
        "service-plan", help="select a measured quality-valid serving profile"
    )
    service_plan.add_argument("--manifest", type=Path, required=True)
    service_plan.add_argument("--constraints", type=Path, required=True)
    service_plan.add_argument("--output", type=Path)
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
    launch.add_argument(
        "--service-manifest",
        type=Path,
        help="measured service evidence; requires --service-constraints",
    )
    launch.add_argument(
        "--service-constraints",
        type=Path,
        help="service SLO policy; requires --service-manifest",
    )
    launch.add_argument("--model-root", type=Path, required=True)
    launch.add_argument("--llama-server", type=Path, required=True)
    launch.add_argument(
        "--runtime-manifest",
        type=Path,
        help="accepted current-runtime evidence; requires the runtime contract/source/build",
    )
    launch.add_argument(
        "--runtime-contract",
        type=Path,
        help="opt-in current-runtime launch contract",
    )
    launch.add_argument(
        "--llama-source-root",
        type=Path,
        help="exact locally patched llama.cpp source tree",
    )
    launch.add_argument(
        "--llama-build-root",
        type=Path,
        help="CMake build directory containing the selected llama-server",
    )
    launch.add_argument("--recipe-output", type=Path, required=True)
    launch.add_argument("--host", default="127.0.0.1")
    launch.add_argument("--port", type=int, default=8081)
    launch.add_argument("--parallel", type=int, default=1)
    launch.add_argument(
        "--threads",
        type=int,
        help="inference threads (default: frozen runtime contract; cannot exceed it)",
    )
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
        default=None,
        help="confirm a repack mode or override the default when no service plan is used",
    )
    launch.add_argument("--dry-run", action="store_true")
    prepack = commands.add_parser(
        "sidecar-prepack",
        help="construct and fully verify an identity-bound Arm repack sidecar",
    )
    prepack.add_argument("--contract", type=Path, required=True)
    prepack.add_argument("--evidence", type=Path, required=True)
    prepack.add_argument("--model", type=Path, required=True)
    prepack.add_argument("--llama-server", type=Path, required=True)
    prepack.add_argument("--sidecar", type=Path, required=True)
    prepack.add_argument("--index", type=Path, required=True)
    prepack.add_argument("--receipt", type=Path, required=True)
    prepack.add_argument("--lifecycle-dir", type=Path, required=True)
    prepack.add_argument("--scratch-root", type=Path, required=True)
    prepack.add_argument("--host", default="127.0.0.1")
    prepack.add_argument("--port", type=int, default=18081)
    prepack.add_argument("--readiness-timeout", type=float, default=120.0)
    verify = commands.add_parser(
        "sidecar-verify",
        help="fully hash and verify a sidecar against model/runtime/CPU identity",
    )
    verify.add_argument("--contract", type=Path, required=True)
    verify.add_argument("--evidence", type=Path, required=True)
    verify.add_argument("--model", type=Path, required=True)
    verify.add_argument("--llama-server", type=Path, required=True)
    verify.add_argument("--sidecar", type=Path, required=True)
    verify.add_argument("--index", type=Path, required=True)
    verify.add_argument("--receipt", type=Path)
    verify.add_argument("--output", type=Path, required=True)
    sidecar_launch = commands.add_parser(
        "sidecar-launch",
        help="verify and launch multiple workers on one shared read-only sidecar",
    )
    sidecar_launch.add_argument("--contract", type=Path, required=True)
    sidecar_launch.add_argument("--evidence", type=Path, required=True)
    sidecar_launch.add_argument("--model", type=Path, required=True)
    sidecar_launch.add_argument("--llama-server", type=Path, required=True)
    sidecar_launch.add_argument("--sidecar", type=Path, required=True)
    sidecar_launch.add_argument("--index", type=Path, required=True)
    sidecar_launch.add_argument("--receipt", type=Path, required=True)
    sidecar_launch.add_argument("--workers", type=int, default=2)
    sidecar_launch.add_argument("--threads", type=int, default=4)
    sidecar_launch.add_argument("--host", default="127.0.0.1")
    sidecar_launch.add_argument("--base-port", type=int, default=18081)
    sidecar_launch.add_argument("--plan-output", type=Path, required=True)
    sidecar_launch.add_argument("--log-dir", type=Path)
    sidecar_launch.add_argument("--readiness-timeout", type=float, default=120.0)
    sidecar_launch.add_argument("--ready-output", type=Path)
    sidecar_launch.add_argument("--outcome-output", type=Path)
    sidecar_launch.add_argument("--stop-file", type=Path)
    sidecar_launch.add_argument("--dry-run", action="store_true")
    cleanup = commands.add_parser(
        "sidecar-cleanup", help="remove only receipt-bound sidecar artifacts"
    )
    cleanup.add_argument("--receipt", type=Path, required=True)
    cleanup.add_argument("--output", type=Path, required=True)
    cleanup.add_argument("--execute", action="store_true")
    gateway = commands.add_parser(
        "gateway", help="serve the certificate-aware OpenAI worker gateway"
    )
    gateway.add_argument("--identity", type=Path, required=True)
    gateway.add_argument("--worker-origin", action="append", required=True)
    gateway.add_argument("--registry", type=Path, required=True)
    gateway.add_argument("--host", default="127.0.0.1")
    gateway.add_argument("--port", type=int, default=18080)
    gateway.add_argument("--minimum-cached-tokens", type=int, default=8)
    gateway.add_argument("--revalidate-every", type=int, default=32)
    gateway.add_argument("--upstream-timeout", type=float, default=120.0)
    deploy = commands.add_parser(
        "deploy", help="verify or prepack, launch workers, and serve one gateway"
    )
    deploy.add_argument("--contract", type=Path, required=True)
    deploy.add_argument("--evidence", type=Path, required=True)
    deploy.add_argument("--model", type=Path, required=True)
    deploy.add_argument("--llama-server", type=Path, required=True)
    deploy.add_argument("--mode", choices=("normal", "shared"), default="shared")
    deploy.add_argument("--sidecar", type=Path)
    deploy.add_argument("--index", type=Path)
    deploy.add_argument("--sidecar-receipt", type=Path)
    deploy.add_argument("--prepack", action="store_true")
    deploy.add_argument("--lifecycle-dir", type=Path)
    deploy.add_argument("--scratch-root", type=Path)
    deploy.add_argument("--workers", type=int, default=2)
    deploy.add_argument("--threads", type=int, default=4)
    deploy.add_argument("--worker-host", default="127.0.0.1")
    deploy.add_argument("--worker-base-port", type=int, default=18081)
    deploy.add_argument("--gateway-host", default="127.0.0.1")
    deploy.add_argument("--gateway-port", type=int, default=18080)
    deploy.add_argument("--registry", type=Path, required=True)
    deploy.add_argument("--minimum-cached-tokens", type=int, default=8)
    deploy.add_argument("--revalidate-every", type=int, default=32)
    deploy.add_argument("--plan-output", type=Path, required=True)
    deploy.add_argument("--deployment-receipt", type=Path, required=True)
    deploy.add_argument("--ready-output", type=Path)
    deploy.add_argument("--log-dir", type=Path)
    deploy.add_argument("--stop-file", type=Path)
    deploy.add_argument("--readiness-timeout", type=float, default=120.0)
    deploy.add_argument("--upstream-timeout", type=float, default=120.0)
    deploy.add_argument("--dry-run", action="store_true")
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
    if arguments.command == "service-plan":
        result = build_service_plan(
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
    if arguments.command == "sidecar-prepack":
        prepack_sidecar(
            contract_path=arguments.contract,
            evidence_path=arguments.evidence,
            model_path=arguments.model,
            server_path=arguments.llama_server,
            sidecar_path=arguments.sidecar,
            index_path=arguments.index,
            receipt_path=arguments.receipt,
            lifecycle_dir=arguments.lifecycle_dir,
            scratch_root=arguments.scratch_root,
            host=arguments.host,
            port=arguments.port,
            readiness_timeout=arguments.readiness_timeout,
        )
        print(arguments.receipt, flush=True)
        return 0
    if arguments.command == "sidecar-verify":
        result = verify_product_sidecar(
            contract_path=arguments.contract,
            evidence_path=arguments.evidence,
            model_path=arguments.model,
            server_path=arguments.llama_server,
            sidecar_path=arguments.sidecar,
            index_path=arguments.index,
            receipt_path=arguments.receipt,
        )
        write_object(arguments.output, result)
        print(arguments.output, flush=True)
        return 0
    if arguments.command == "sidecar-launch":
        plan = prepare_sidecar_launch(
            contract_path=arguments.contract,
            evidence_path=arguments.evidence,
            model_path=arguments.model,
            server_path=arguments.llama_server,
            sidecar_path=arguments.sidecar,
            index_path=arguments.index,
            receipt_path=arguments.receipt,
            workers=arguments.workers,
            threads=arguments.threads,
            host=arguments.host,
            base_port=arguments.base_port,
        )
        write_object(arguments.plan_output, plan)
        print(arguments.plan_output, flush=True)
        if arguments.dry_run:
            return 0
        outcome = execute_sidecar_group(
            plan,
            log_dir=arguments.log_dir,
            readiness_timeout=arguments.readiness_timeout,
            ready_output=arguments.ready_output,
            stop_file=arguments.stop_file,
        )
        if arguments.outcome_output is not None:
            write_object(arguments.outcome_output, outcome)
        return 0 if outcome["status"] == "sidecar_worker_group_stopped" else 1
    if arguments.command == "sidecar-cleanup":
        result = cleanup_sidecar(arguments.receipt, execute=arguments.execute)
        write_object(arguments.output, result)
        print(arguments.output, flush=True)
        return 0
    if arguments.command == "gateway":
        store = CertificateStore(
            arguments.registry,
            load_object(arguments.identity),
            minimum_cached_tokens=arguments.minimum_cached_tokens,
            revalidate_every=arguments.revalidate_every,
        )
        state = GatewayState(
            tuple(arguments.worker_origin),
            store,
            upstream_timeout=arguments.upstream_timeout,
        )
        server = GatewayHTTPServer((arguments.host, arguments.port), state)
        host, port = server.server_address
        print(f"Pareto64 gateway listening on http://{host}:{port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if arguments.command == "deploy":
        lifecycle_started = time.perf_counter()
        sidecar_paths = (
            arguments.sidecar,
            arguments.index,
            arguments.sidecar_receipt,
        )
        if arguments.mode == "shared" and any(path is None for path in sidecar_paths):
            raise ValueError(
                "shared deployment requires --sidecar, --index, and --sidecar-receipt"
            )
        if arguments.mode == "normal" and arguments.prepack:
            raise ValueError("normal deployment cannot prepack a sidecar")
        if arguments.prepack:
            if arguments.lifecycle_dir is None or arguments.scratch_root is None:
                raise ValueError(
                    "--prepack requires --lifecycle-dir and --scratch-root"
                )
            prepack_sidecar(
                contract_path=arguments.contract,
                evidence_path=arguments.evidence,
                model_path=arguments.model,
                server_path=arguments.llama_server,
                sidecar_path=arguments.sidecar,
                index_path=arguments.index,
                receipt_path=arguments.sidecar_receipt,
                lifecycle_dir=arguments.lifecycle_dir,
                scratch_root=arguments.scratch_root,
                host=arguments.worker_host,
                port=arguments.worker_base_port,
                readiness_timeout=arguments.readiness_timeout,
            )
        elif arguments.lifecycle_dir is not None or arguments.scratch_root is not None:
            raise ValueError(
                "--lifecycle-dir and --scratch-root are valid only with --prepack"
            )
        if arguments.mode == "shared":
            sidecar_plan = prepare_sidecar_launch(
                contract_path=arguments.contract,
                evidence_path=arguments.evidence,
                model_path=arguments.model,
                server_path=arguments.llama_server,
                sidecar_path=arguments.sidecar,
                index_path=arguments.index,
                receipt_path=arguments.sidecar_receipt,
                workers=arguments.workers,
                threads=arguments.threads,
                host=arguments.worker_host,
                base_port=arguments.worker_base_port,
            )
        else:
            sidecar_plan = prepare_normal_launch(
                contract_path=arguments.contract,
                evidence_path=arguments.evidence,
                model_path=arguments.model,
                server_path=arguments.llama_server,
                workers=arguments.workers,
                threads=arguments.threads,
                host=arguments.worker_host,
                base_port=arguments.worker_base_port,
            )
        plan = prepare_deployment(
            sidecar_plan,
            gateway_host=arguments.gateway_host,
            gateway_port=arguments.gateway_port,
            registry_path=arguments.registry,
            minimum_cached_tokens=arguments.minimum_cached_tokens,
            revalidate_every=arguments.revalidate_every,
        )
        write_object(arguments.plan_output, plan)
        print(arguments.plan_output, flush=True)
        if arguments.dry_run:
            return 0
        receipt = execute_deployment(
            plan,
            receipt_path=arguments.deployment_receipt,
            log_dir=arguments.log_dir,
            readiness_timeout=arguments.readiness_timeout,
            upstream_timeout=arguments.upstream_timeout,
            ready_output=arguments.ready_output,
            stop_file=arguments.stop_file,
            lifecycle_started=lifecycle_started,
        )
        print(arguments.deployment_receipt, flush=True)
        return 0 if receipt["status"] == "valid_pareto64_deployment_lifecycle" else 1
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
            threads=arguments.threads,
            prompt_cache=arguments.prompt_cache,
            context_per_slot=arguments.context_per_slot,
            kv_cache_type_k=arguments.kv_cache_type_k,
            kv_cache_type_v=arguments.kv_cache_type_v,
            batch_size=batch_size,
            micro_batch_size=micro_batch_size,
            flash_attention=arguments.flash_attention,
            weight_repack=arguments.weight_repack,
            log_verbosity=arguments.log_verbosity,
            service_manifest=(
                load_object(arguments.service_manifest)
                if arguments.service_manifest
                else None
            ),
            service_constraints=(
                load_object(arguments.service_constraints)
                if arguments.service_constraints
                else None
            ),
            service_manifest_path=arguments.service_manifest,
            service_constraints_path=arguments.service_constraints,
            runtime_manifest=(
                load_object(arguments.runtime_manifest)
                if arguments.runtime_manifest
                else None
            ),
            runtime_contract=(
                load_object(arguments.runtime_contract)
                if arguments.runtime_contract
                else None
            ),
            runtime_manifest_path=arguments.runtime_manifest,
            runtime_contract_path=arguments.runtime_contract,
            runtime_source_root=arguments.llama_source_root,
            runtime_build_root=arguments.llama_build_root,
        )
        write_recipe(arguments.recipe_output, recipe)
        print(arguments.recipe_output, flush=True)
        if arguments.dry_run:
            return 0
        argv = recipe["runtime"]["argv"]
        os.execv(argv[0], argv)
        raise AssertionError("execv returned unexpectedly")
    raise AssertionError(f"unsupported command {arguments.command}")
