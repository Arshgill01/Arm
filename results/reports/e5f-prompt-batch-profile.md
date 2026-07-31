# E5f prompt batch and microbatch profile

E5f profiles the promoted f16/256 cached single-slot service across effective
logical/physical prompt batches of 256/256, 128/128, and 64/64. The selected
model, pinned runtime, four threads, context, cache precision, flash-attention
mode, request set, seed, and output cap remain fixed.

## Result

Native run
[`30669700602`](https://github.com/Arshgill01/Arm/actions/runs/30669700602)
passed the frozen six-cell workflow and independent ingester end to end in
9m27s. The result is `valid_selected_inference_batch_profile`, and the
unweighted lexicographic selector chose `batch64`.

| Profile | CPU compute buffer | Quality per repetition | Throughput | Median / p95 HTTP | Maximum RSS | RSS reduction | Eligible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 256 / 256 | 40.13 MiB | 23/30 · 23/30 | 0.8975 req/s | 1,067.9 / 2,067.2 ms | 4,468,380 KiB | baseline | no |
| 128 / 128 | 20.07 MiB | 23/30 · 23/30 | 0.8962 req/s | 1,064.3 / 2,064.4 ms | 4,467,304 KiB | 1,076 KiB | no: RSS gate |
| **64 / 64** | **10.03 MiB** | **23/30 · 23/30** | **0.9178 req/s** | **1,072.7 / 1,880.1 ms** | **4,453,556 KiB** | **14,824 KiB** | **selected** |

All 180 measured requests returned HTTP 200, stopped normally, reused at least
25 prompt tokens, and matched the selected E3f prediction. The 64/64 profile
reduced the reported compute buffer by 30.10 MiB (75.0%) and conservative
maximum process RSS by 14,824 KiB (14.48 MiB). Repeated median throughput was
1.0226x baseline, pooled median latency was 1.0044x, and p95 latency fell to
0.9095x baseline. Every frozen quality, memory, throughput, latency, readiness,
and absolute-RSS gate passed.

## Boundary

The 128/128 profile demonstrates why the contract requires process evidence as
well as a runtime allocation log. Its compute buffer fell by 20.06 MiB, and it
preserved quality and performance, but conservative maximum RSS fell by only
1,076 KiB—well below the predeclared 8 MiB minimum. It is a valid measurement,
not an eligible product optimization.

The 64/64 profile intentionally splits prompts whose unseen suffix exceeds 64
tokens. Despite that different execution path, both repetitions reproduced all
30 selected predictions. This application-level obligation is necessary
because pinned llama.cpp warns that caching and different prompt batch sizes
can change logits.

## Decision

Pareto64 promotes `batch64`. It is the only non-baseline
profile to clear every gate, lowers both the reported allocation and observed
process RSS, and improves rather than merely retains throughput in this run.
The 256-token context remains unchanged; the smaller batch reduces transient
compute-graph reservation rather than application context capacity.

## Reproduction

The retained manifest is
[`e5f-30669700602.json`](../manifests/e5f-30669700602.json). Independent local
Python 3.10 ingestion reproduced the uploaded summary byte for byte at SHA-256
`396222dd2ec0d66c0985392b0c2b65e4fa1b8a3100f57c4d1d30d50a41f92d4b`.
After promotion, native run
[`30670972497`](https://github.com/Arshgill01/Arm/actions/runs/30670972497)
repeated the complete matrix with the `batch64` Pareto64 invocation omitting
both batch flags. All 180 answers matched again; `batch64` retained 1.0240x
throughput and saved 17,264 KiB maximum RSS. Independent Python 3.10 ingestion
again matched the uploaded summary byte for byte at SHA-256
`4b0e4632306829c4d3fa0ce5b01351bf4e2f9dec6cdc4e4f48f8e40a0542135a`.
The exact forward/reverse order, immutable inputs, invocation binding, selection
policy, and acceptance gates are in
[`../../experiments/e5f_contract.json`](../../experiments/e5f_contract.json).
