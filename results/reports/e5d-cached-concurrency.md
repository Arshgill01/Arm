# E5d cached-concurrency interaction

E5d tests whether E5c's quality-gated shared-prefix cache changes E5b's
rejected concurrency result. Both configurations use the exact promoted cache,
model, runtime, four threads, request set, and deterministic recipe. The only
measured change is one server slot/client versus two slots/clients.

## Result

Native run
[`30664666945`](https://github.com/Arshgill01/Arm/actions/runs/30664666945)
passed the frozen workflow and independent ingester end to end in 7m51s. The
result is `valid_selected_inference_no_cached_concurrency_win`: the experiment
is valid, but cached two-slot serving is not eligible for promotion.

Each fresh dual-slot server received one explicitly routed, unmeasured warmup
per slot before normal automatic scheduling began. All 120 measured requests
returned HTTP 200, stopped normally, produced an exact standalone A-D letter,
and matched the frozen E3f prediction. Every cell reproduced 23/30 with zero
failures or drift, and every measured request reused at least 25 prompt tokens.

| Metric | Cached single slot | Cached two slots | Effect |
| --- | ---: | ---: | ---: |
| Repeated median throughput | 0.9056 req/s | 0.9617 req/s | **1.0619x** |
| Repeated median prompt encode | 983.3 ms | 1,906.8 ms | **93.9% higher** |
| Pooled median HTTP latency | 1,052.7 ms | 2,034.4 ms | **93.3% higher** |
| Pooled p95 HTTP latency | 2,045.1 ms | 3,076.5 ms | **50.4% higher** |
| Minimum reused prompt tokens | 25 | 25 | mechanism observed |
| Maximum process RSS | 4,655,908 KiB | 4,900,432 KiB | +244,524 KiB |
| Median deployment readiness | 3,901.1 ms | 3,839.5 ms | neutral |

The candidate stayed below the 5/10-second median/p95 latency ceilings, the
8 GiB absolute RSS ceiling, the 512 MiB incremental RSS ceiling, and the
15-second readiness ceiling. It failed only the independently predeclared
1.10x throughput gate.

## Decision

Pareto64 retains cached single-slot serving as the verified default. Prompt
caching did improve the two-slot ratio relative to E5b's uncached 1.0189x
result, but the resulting 1.0619x gain is still too small to justify almost
double median request latency and about 239 MiB additional maximum RSS.

This result establishes an important cross-layer boundary: prompt reuse and
continuous-batching concurrency are individually testable, but their benefits
cannot be assumed to compose on a fixed four-core Arm host.

## Reproduction

The retained manifest is
[`e5d-30664666945.json`](../manifests/e5d-30664666945.json). Independent local
Python 3.10 ingestion reproduced the uploaded summary byte for byte at SHA-256
`a844e58ea3f89e8fd9d9e8697ad6c680865a6719d2f6b34298af0d56be7d76e5`.
The exact single/dual/dual/single order, warmup routing, immutable inputs, risk
statement, and acceptance gates are in
[`../../experiments/e5d_contract.json`](../../experiments/e5d_contract.json).
