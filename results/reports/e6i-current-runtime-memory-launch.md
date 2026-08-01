# E6i verified current-runtime no-repack launch

Native run [`30691254831`](https://github.com/Arshgill01/Arm/actions/runs/30691254831)
closed the product-integration boundary left by E6h. On a four-core Neoverse N2,
the job rebuilt the exact three-patch llama.cpp `b10216` source and launched the
selected Ministral memory service through `python -m pareto64 launch` with the
new E6h-bound runtime contract and explicit `--no-weight-repack` control.

## Result

The exact no-repack service is a valid current-runtime launch integration.
Pareto64 verified the immutable E3f and E6h manifests, model bytes, full-index
source diff, CMake source/build relationship, server version and binary hash,
then executed the live server through the adapter.

| Metric | Native result |
| --- | ---: |
| Selected-task quality | 23/30 (76.67%) |
| Reference prediction mismatches | 0 |
| Request failures | 0 |
| Cached-prefix reuse | every measured request |
| Throughput | 0.44857 req/s |
| Median / p95 HTTP latency | 2,424.61 / 3,323.20 ms |
| Server CPU seconds/request | 8.84967 s |
| Readiness | 2,242.22 ms |
| Maximum RSS | 2,381,040 KiB |

Maximum RSS remained below the frozen 3 GiB product ceiling. The executed
recipe retained the E6h manifest hash, memory launch-contract hash, exact
patched commit and diff, four threads, one slot, f16/256/64 service, automatic
Flash Attention, shared-prefix caching, and no weight repacking. The live server
exposed the required slot and metrics endpoints and shut down with an accepted
status.

## Validation boundary

E6i integrates only this exact patched no-repack service. E5h remains the
fast-versus-memory tradeoff evidence, E6h remains the historical-to-current
upgrade comparison, and E6g remains the separate repacked fast integration.
This result is not an energy saving, new optimization comparison, other-profile
promotion, fast-tier result, or full upstream matrix claim.

Independent Python 3.10 ingestion reproduced the uploaded summary byte for byte
at SHA-256
`2bcbd7e1a7b727a763ca12c9664106a82d9ef8a70ec17ef1ac2fe9ed460c06d2`.

See the frozen [`E6i contract`](../../experiments/e6i_contract.json), retained
[`manifest`](../manifests/e6i-30691254831.json), E6h-bound
[`runtime contract`](../../configs/runtime-b10216-memory-service.json), and
native [`workflow`](../../.github/workflows/current-runtime-launch.yml).
