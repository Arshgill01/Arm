# E6f current-runtime selected-service upgrade

Native run [`30678703184`](https://github.com/Arshgill01/Arm/actions/runs/30678703184)
completed the frozen clean-`b10208` versus patched-`b10216` comparison on a
four-core Neoverse N2. Both revisions were built from scratch in one job with
matched native/KleidiAI Release settings. Four fresh servers ran in
historical–current–current–historical order with the exact selected Ministral
Q4_K_M model and the same repacked, f16/256/64, cached, four-thread, one-slot
service.

## Result

Patched llama.cpp `b10216` cleared every frozen upgrade gate and is a valid
candidate for the selected service. It is not a model-wide or automatic product
promotion.

| Runtime | Median throughput | Pooled median / p95 HTTP | Median server CPU seconds/request | Median readiness | Max RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Clean b10208 | 0.93085 req/s | 1,058.07 / 1,861.34 ms | 4.24650 s | 2,376.50 ms | 4,450,996 KiB |
| Patched b10216 | 0.93341 req/s | 1,049.39 / 1,849.99 ms | 4.24367 s | 2,491.03 ms | 4,451,096 KiB |

The candidate retained 100.28% throughput, used 99.93% of baseline CPU seconds
per request, and produced median/p95 latency ratios of 0.9918x/0.9939x. Its
median readiness ratio was 1.0482x and maximum RSS increased by 100 KiB. These
all clear the predeclared 0.95 throughput floor, 1.05 latency/CPU ceilings, 1.10
readiness ceiling, and 64 MiB RSS allowance.

Both runtimes reproduced the selected 23/30 prediction map in both repetitions,
with stable predictions, zero mismatches, zero request failures, and prefix reuse
in every measured request.

## Validation boundary

The artifact binds both source tags and commits, the three exact patch hashes
and four changed files, matched CMake caches, server versions, runtime buffer
proofs, model bytes, every server recipe and timed command, live server PIDs,
process CPU ticks, readiness, slots, metrics, and raw responses. Python 3.10
re-ingestion reproduced the uploaded summary byte for byte at SHA-256
`da95b831a0cccf3b16dd45e93e11855a6e0322c5aa163d145c24243b42470ace`.

The earlier attempt `30678221353` completed all native measurements but failed
closed because the new version capture retained stdout while `llama-server`
emits its version on stderr. The corrected capture combines both streams; no
source, patch, model, service, order, measurement, or gate changed.

This result validates only the exact selected-model native Arm service. It does
not establish an energy saving, model-wide speedup, full upstream matrix, or
unattended product promotion. See the frozen
[`E6f contract`](../../experiments/e6f_contract.json), retained
[`manifest`](../manifests/e6f-30678703184.json), and native
[`workflow`](../../.github/workflows/current-runtime-service.yml).
