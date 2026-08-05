# Native experiment readiness gate

Pareto64 now has a reusable fail-closed gate for every future expensive native
Arm experiment. It is deliberately local and synthetic: passing it authorizes a
bounded native preflight, not a performance claim.

## Artifact shapes

The fixture validates the server's documented `/slots` array directly and
keeps ordinary evidence documents object-only. Required timing values accept
only finite numbers; missing, null, string and non-finite values retain distinct
failure reasons. Cell accounting distinguishes complete, failed, partial,
missing and unexpected cells, and only an exact complete set is claim-ready.
Raw request JSON objects must be explicitly bound by a safe relative-path
SHA-256 inventory.

Two independent fixture replays produce the same 755-byte canonical summary at
SHA-256 `bad324e2dbddd18c4f164f05edbfa59738b76f4e244d121fa22c0b00d863f963`.
The machine-readable [retained manifest](../manifests/evidence-readiness-gate-v1.json)
captures every accepted and rejected shape.

## Dispatch rule

The versioned policy requires this order:

1. mechanism/unit proof;
2. complete byte-stable synthetic control/candidate replay;
3. one control and one candidate on native `ubuntu-24.04-arm`;
4. full matrix only after that exact preflight passes.

Before dispatch, a lane must freeze the affected runtime share, internally
consistent Amdahl ceiling, minimum product-changing result, claim unlocked, and
maximum runtime/storage. If its best possible system-throughput gain is below
3%, it stops unless a distinct novelty, memory, quality or deployability value
was predeclared. A planned native pair returns `await_native_preflight`; a
passing pair with sufficient value returns `matrix_allowed`; the retained 1%
fixture returns `stop_below_amdahl_floor`.

## Reproduction

```bash
python3 experiments/evidence_readiness.py --self-test
python3 -m unittest tests.test_evidence_readiness
uvx --from ruff==0.12.11 ruff check \
  experiments/evidence_readiness.py tests/test_evidence_readiness.py
```

This gate makes no throughput, latency, CPU, memory, energy, cost, PMU, or
device claim.
