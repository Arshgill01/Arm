# E5e context and KV-cache memory profile

E5e profiles the promoted cached single-slot service across two context sizes
and three K-cache precisions. The selected model, pinned runtime, four threads,
f16 V cache, explicit `auto` flash-attention mode, request set, and deterministic
recipe remain fixed.

## Result

Native run
[`30667019678`](https://github.com/Arshgill01/Arm/actions/runs/30667019678)
passed the frozen workflow and independent ingester end to end in 13m33s. The
result is `valid_selected_inference_memory_profile`, and the lexicographic
selector chose `ctx256_k_f16`.

The measured workload used at most 127 prompt tokens. Adding the unchanged
eight-token output cap gives a 135-token bound, so the selected 256-token
context retains 1.896x headroom. Its runtime allocation proof fell from 208 MiB
of f16 KV storage at 2,048 tokens to 26 MiB at 256 tokens.

| Profile | KV allocation | Quality per repetition | Throughput | Median / p95 HTTP | Maximum RSS | RSS reduction | Eligible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2048 / K f16 | 208.00 MiB | 23/30 · 23/30 | 0.9001 req/s | 1,063.7 / 2,057.4 ms | 4,656,020 KiB | baseline | no |
| 2048 / K q8_0 | 159.25 MiB | 23/30 · 23/30 | 0.9418 req/s | 1,064.5 / 1,672.6 ms | 4,552,008 KiB | 104,012 KiB | no: memory gate |
| 2048 / K q4_0 | 133.25 MiB | 22/30 · 22/30 | 0.9413 req/s | 1,063.8 / 1,669.4 ms | 4,504,092 KiB | 151,928 KiB | no: quality drift |
| **256 / K f16** | **26.00 MiB** | **23/30 · 23/30** | **0.8966 req/s** | **1,061.5 / 2,052.2 ms** | **4,468,260 KiB** | **187,760 KiB** | **selected** |
| 256 / K q8_0 | 19.91 MiB | 23/30 · 23/30 | 0.9388 req/s | 1,072.2 / 1,677.6 ms | 4,408,384 KiB | 247,636 KiB | yes |
| 256 / K q4_0 | 16.66 MiB | 22/30 · 22/30 | 0.9359 req/s | 1,069.9 / 1,679.8 ms | 4,383,792 KiB | 272,228 KiB | no: quality drift |

All 12 cells had zero request failures, stayed below the readiness and absolute
RSS ceilings, and proved real prefix reuse. The selected f16 profile reduced
conservative maximum process RSS by 187,760 KiB (183.36 MiB, 4.03%) while
retaining 99.62% of repeated median throughput. Pooled median and p95 latency
were respectively 0.21% and 0.25% lower than baseline.

## Quality boundary

K q8_0 preserved every selected E3f prediction at both contexts and also met
all gates at 256 tokens. K q4_0 did not: all four q4_0 cells reproducibly changed
`systems-04` from the correct/reference answer B to C, reducing quality from
23/30 to 22/30. The validator retained those measurements but made both q4_0
profiles ineligible.

## Decision

Pareto64 promotes a 256-token context with f16 K and V caches. The result shows
that application-aware right-sizing captures most of the safe memory reduction
without changing numerical precision. q8_0 saves another 58.48 MiB and improves
throughput in this run, but the frozen selector intentionally preserves f16
once f16 clears every resource and performance gate. q4_0's consistent answer
drift demonstrates why memory savings remain quality-gated.

## Reproduction

The retained manifest is
[`e5e-30667019678.json`](../manifests/e5e-30667019678.json). Independent local
Python 3.10 ingestion reproduced the uploaded summary byte for byte at SHA-256
`6312dc789eefad276b20d3204d9a5144251d49e3f04b9a767d9125dceaa5ed2c`.
The exact forward/reverse order, immutable inputs, factor controls, selection
policy, and acceptance gates are in
[`../../experiments/e5e_contract.json`](../../experiments/e5e_contract.json).
