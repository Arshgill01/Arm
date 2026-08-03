# Experiment environment audit

Audited: 2026-08-03 UTC.

## Current development host

| Resource | Observed state | Consequence |
| --- | --- | --- |
| OS/kernel | Ubuntu 26.04, Linux 7.0 on GCP | Modern build host, not the target |
| Architecture | x86_64 | Cannot substantiate Arm performance claims locally |
| CPU | 4 vCPU / 2 physical cores, AMD EPYC 7B12, AVX2 | Suitable for harness tests and x86 controls only |
| RAM/swap | 7.7 GiB RAM; heavy swap use | Poor environment for stable inference latency |
| Disk | 20 GiB free; filesystem 85% used | Avoid duplicate models and large local builds |
| GPU | None | CPU inference is the practical path |
| Containers | Three unrelated DataHub containers active; Docker uses about 54 GiB | Preserve unrelated workloads; do not benchmark locally under this noise |
| Performance counters | `perf_event_paranoid=4`; `perf` unavailable to unprivileged runs | Use wall clock locally; investigate PMU on native Arm separately |

Do not reclaim Docker data or stop unrelated containers without explicit target
review. The reported reclaimable space includes active user-owned work.

## Tooling already usable

- Clang/LLVM 21 and 22, including AArch64 code generation.
- `llvm-mca-22` with Neoverse V2 scheduling models.
- A verified cross-codegen smoke test emitted SVE2 instructions.
- Zig 0.14.1, GCC 15.2, CMake 4.2.3, Ninja 1.13.2, Rust, Go,
  Java, Node, and Python 3.11–3.14.
- Docker daemon and authenticated GitHub CLI with repository/workflow scopes.
- NumPy and ONNX Runtime, useful for small harness prototypes.

The host lacks native Arm execution, QEMU/binfmt, Arm GCC/sysroots, Docker
Buildx, and a GPU. Emulation can later test compatibility but must never be
reported as Arm performance.

## Native Arm routes and current billing boundary

GitHub provides these native standard hosted-runner labels:

- `ubuntu-24.04-arm`: 4 Arm64 vCPUs, 16 GiB RAM, 14 GiB SSD;
- `ubuntu-22.04-arm`: same published class;
- `macos-26`: 4-vCPU Apple Silicon, 14 GiB RAM.

GitHub states standard runner use is free and unlimited for public repositories,
subject to normal concurrency/job limits. The repository is currently private,
so additional hosted jobs may consume private-repository minutes. Under the
no-paid-services boundary, no further hosted job should be launched until the
repository is public or the entrant explicitly confirms an included, non-billed
allowance. Linux Arm runners use images managed in partnership with Arm; the
underlying processor/environment must still be captured in every run.

The retained native runs establish two technically available paths:

- Cloud AI: Linux Arm64 runner for native server/inference experiments.
- Mobile AI: Apple Silicon runner, which an Arm organizer explicitly confirmed
  counts for Mobile AI.

Hosted runners are ephemeral and noisy. They are excellent for repeatable
screening and CI regression tests, but final headline numbers should be repeated
on a named, stable Arm device or cloud instance when possible.

## Access still worth obtaining

- Arm Developer Program and Devpost enrollment confirmation.
- Arm Performix download/entitlement and a Neoverse target reachable by SSH.
- A stable named Arm cloud instance for final repeated benchmarks, or a local
  Raspberry Pi/Arm client device if the selected track changes.
- Optional Android/Apple device if a consumer-device thermal/energy story is
  selected.
