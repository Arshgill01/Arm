# E6h current-runtime no-repack memory-tier upgrade

Native run [`30690331795`](https://github.com/Arshgill01/Arm/actions/runs/30690331795)
completed the frozen clean-`b10208` versus patched-`b10216` comparison for the
existing Pareto64 no-repack memory tier on a four-core Neoverse N2. Both
revisions were built from scratch in one job with matched native/KleidiAI
Release settings. Four fresh servers ran in
historical–current–current–historical order with the exact selected Ministral
Q4_K_M model and the same no-repack, f16/256/64, cached, four-thread, one-slot
service.

## Result

Patched llama.cpp `b10216` cleared every frozen memory-tier upgrade gate and is
a valid candidate for this exact no-repack service. It is not an automatic
product promotion or evidence for another service profile.

| Runtime | Median throughput | Pooled median / p95 HTTP | Median server CPU seconds/request | Median readiness | Max RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Clean b10208 | 0.45048 req/s | 2,420.69 / 3,307.14 ms | 8.81567 s | 916.97 ms | 2,381,164 KiB |
| Patched b10216 | 0.45156 req/s | 2,416.65 / 3,301.92 ms | 8.80250 s | 865.17 ms | 2,381,344 KiB |

The candidate retained 100.24% throughput, used 99.85% of baseline CPU seconds
per request, and produced median/p95 latency ratios of 0.9983x/0.9984x. Its
readiness ratio was 0.9435x and maximum RSS increased by 180 KiB. Every cell
remained below the predeclared 3 GiB ceiling, and all relative gates passed.

Both runtimes reproduced the selected 23/30 prediction map in both repetitions,
with stable predictions, zero mismatches, zero request failures, and prefix reuse
in every measured request. Proof-only server starts for both revisions showed
the mapped model buffer and no `CPU_REPACK` buffer.

## Validation boundary

E5h remains the evidence that no-repack is a distinct memory tier and records
its fast-versus-memory tradeoff. E6h asks only whether that exact tier survives
the runtime upgrade. It does not establish an energy saving, model-wide speedup,
full upstream matrix, fast-tier result, or unattended product promotion. A
separate evidence-bound launch integration is still required before Pareto64
can start the patched memory tier.

Python 3.10 independent re-ingestion reproduced the uploaded summary byte for
byte at SHA-256
`7b112b385729ef092f2026bf35b63926ac985251d70faea2cf03e4936253b27f`.

The earlier attempt `30689986153` completed both exact builds but stopped before
any service cell because `llama-bench` does not implement the server's
`--no-repack` option. The corrected proof starts each server briefly at
proof-only verbosity; no source, model, service, measurement, order, or
acceptance gate changed.

See the frozen [`E6h contract`](../../experiments/e6h_contract.json), retained
[`manifest`](../manifests/e6h-30690331795.json), and native
[`workflow`](../../.github/workflows/current-runtime-service.yml).
