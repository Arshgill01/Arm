# E16c shared arena: retained premeasurement permission failure

Status: **invalid premeasurement runner failure; exact retry allowed**

GitHub run: [30850318745](https://github.com/Arshgill01/Arm/actions/runs/30850318745)

Artifact: `e16c-shared-repack-arena-30850318745-1` (ID `8870468109`)

Artifact digest: `sha256:331a210f21c6f4c3b49b4fbeb3252e3989520a9859dadcf4e247bccb76073cd4`

## What happened

The exact b10216 loader source built successfully on the native four-core
Neoverse-N2 runner. The selected model was verified, the packed sidecar was
constructed, its 183-tensor binding was validated, and the raw tensor dump was
deleted. The first two-worker group did not start because
`experiments/e16c_shared_arena_group.sh` was retained with mode `100644` and the
workflow invoked it directly. The shell returned status 126 (`Permission
denied`).

The `always()` cleanup path independently reverified the generated 2,139,013,120
byte sidecar, deleted it, and confirmed cleanup. The complete 84-file artifact
is retained and hashed.

## Evidence boundary

- Measured worker processes started: 0
- Measured requests completed: 0
- Quality, throughput, latency, CPU, RSS, or PSS observed: no
- Promotion permitted: no
- Contract or gate change permitted: no

Because the failure occurred before the first measured process, an exact retry
is valid after changing only the retained executable file mode to `100755`.
File content and the frozen E16c contract SHA-256 remain unchanged.
