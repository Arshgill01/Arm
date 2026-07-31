# E5c quality-gated shared-prefix prompt cache

E5c tests whether the exact E5b-selected native Arm service can safely reuse
the system/chat-template prefix shared by every request. The pinned llama.cpp
runtime warns that different prompt batch sizes can alter logits, so cache
promotion required exact task-level output stability before performance was
considered.

## Result

Native run
[`30662037235`](https://github.com/Arshgill01/Arm/actions/runs/30662037235)
passed the frozen workflow and independent ingester end to end in 9m41s. The
result is `valid_selected_inference_prompt_cache`: prompt caching is eligible
for promotion as the single-slot serving default.

All four fresh-server cells verified the same 2,146,497,824-byte Q4_K_M model,
SHA-256, selected plan, source revisions, llama.cpp `b10208` commit, runtime
buffers, recipe, and request settings. Every one of the 120 measured requests
returned HTTP 200, stopped normally, contained an exact standalone A-D letter,
and matched the frozen E3f prediction. Each cell reproduced 23/30 with zero
failures or drift.

| Metric | Cache disabled | Shared-prefix cache | Effect |
| --- | ---: | ---: | ---: |
| Repeated median throughput | 0.5378 req/s | 0.8991 req/s | **1.672x** |
| Repeated median prompt encode | 1,738.0 ms | 989.0 ms | **1.757x faster** |
| Pooled median HTTP latency | 1,807.0 ms | 1,061.6 ms | **41.3% lower** |
| Pooled p95 HTTP latency | 2,644.6 ms | 2,060.5 ms | **22.1% lower** |
| Median reused prompt tokens | 0 | 25 | mechanism observed |
| Maximum process RSS | 4,649,404 KiB | 4,655,712 KiB | +6,308 KiB |
| Median deployment readiness | 3,963.6 ms | 3,942.0 ms | neutral |

The no-cache cells reported exactly zero cached tokens. Every candidate request
reused at least 25 prompt tokens; the candidate distribution had a 25-token
median and 92-token maximum. The mechanism therefore appears in raw response
timings rather than being inferred from latency alone.

The improvement cleared both independently predeclared 1.10x gates by a wide
margin while staying under the unchanged median/p95 latency, readiness, and 8
GiB RSS ceilings. The approximately 6.2 MiB maximum-RSS increase is negligible
relative to the selected model service.

## Decision

Pareto64 may enable prompt caching for the verified single-slot selected-model
path. The launcher retains an explicit no-cache override for workloads whose
prompts do not share a stable prefix or whose application correctness has not
been validated. E5b's rejected two-slot result remains unchanged; this win
comes from eliminating redundant prefix evaluation, not dividing the four
cores across more requests.

## Reproduction

The retained manifest is
[`e5c-30662037235.json`](../manifests/e5c-30662037235.json). Independent local
Python 3.10 ingestion reproduced the uploaded summary byte for byte at SHA-256
`27a426dd9ed0ed8e4b9ef513a5ced7418f7a722b91e94ca1bc10f8f76d84bfa7`.
The exact ABBA order, immutable inputs, risk statement, and acceptance gates are
in [`../../experiments/e5c_contract.json`](../../experiments/e5c_contract.json).
