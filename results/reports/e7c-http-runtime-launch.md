# E7c verified HTTP-only dependency-pruned launch

Native run [`30696606993`](https://github.com/Arshgill01/Arm/actions/runs/30696606993)
closed the product boundary left by E7b. On a four-core Neoverse N2, the job
rebuilt the exact three-patch llama.cpp `b10216` source with `GGML_LTO=OFF` and
`LLAMA_OPENSSL=OFF`, then launched the selected repacked loopback HTTP service
through `python -m pareto64 launch`.

## Result

The exact dependency-pruned HTTP service is a valid evidence-bound launch
integration. Pareto64 verified the retained E3f and E7b manifests, model bytes,
full-index source diff, CMake source/build relationship and required cache,
server version and binary hash, exact service arguments, and a fresh dynamic
dependency inventory before starting the server.

| Metric | Native result |
| --- | ---: |
| Selected-task quality | 23/30 (76.67%) |
| Reference prediction mismatches | 0 |
| Request failures | 0 |
| Cached-prefix reuse | every measured request |
| Throughput | 0.93026 req/s |
| Median / p95 HTTP latency | 1,065.13 / 1,852.71 ms |
| Server CPU seconds/request | 4.247 s |
| Readiness | 4,356.71 ms |
| Maximum RSS | 4,449,416 KiB |

The adapter recorded 13 dynamic dependency basenames. A second raw `ldd`
capture matched that inventory exactly, and neither `libssl.so.3` nor
`libcrypto.so.3` was present. All 30 requests reproduced the selected prediction
map with zero drift or failures and observed cached-prefix reuse.

Python 3.10 independent ingestion reproduced the uploaded summary byte for byte
at SHA-256
`f4e73971b0c6f2db25be52e365cf611848ec1bb1d738648bb43bdf4c2e1857cf`.

## Validation boundary

E7c integrates only this exact patched, repacked, OpenSSL-off loopback HTTP
service. HTTPS is unsupported by the build. This is not a new optimization
comparison, security or installed-package claim, energy claim, other-profile
promotion, or full upstream-platform validation.

The first native attempt [`30696286405`](https://github.com/Arshgill01/Arm/actions/runs/30696286405)
built and executed the service but was rejected before ingestion because the
new experiment contract omitted the otherwise unchanged request protocol. The
corrected contract explicitly freezes the same E6g/E6i warmups, task sequence,
token cap, instruction mode, seed, and timeout. No model, runtime, service,
acceptance threshold, or observed native result was changed or accepted
retroactively.

See the frozen [`E7c contract`](../../experiments/e7c_contract.json), retained
[`manifest`](../manifests/e7c-30696606993.json), E7b-bound
[`runtime contract`](../../configs/runtime-b10216-http-service.json), and native
[`workflow`](../../.github/workflows/current-runtime-launch.yml).
