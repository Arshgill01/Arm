# E5g marginal prompt batch floor

E5g tests whether the promoted 64/64 prompt batch still reserves unnecessary
transient memory. The study is deliberately staged: 32/32 is the only
candidate, and 16/16 is tested only if 32/32 clears every frozen gate.

## Result

Native run
[`30671733556`](https://github.com/Arshgill01/Arm/actions/runs/30671733556)
completed the two mechanism launches and four-cell A–B–B–A matrix in 7m40s.
The result is `valid_selected_inference_no_batch_profile_win`; no candidate is
eligible for promotion.

| Profile | CPU compute buffer | Quality per repetition | Throughput | Median / p95 HTTP | Maximum RSS | RSS change | Eligible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **64 / 64** | **10.03 MiB** | **23/30 · 23/30** | **0.9323 req/s** | **1,049.6 / 1,851.2 ms** | **4,451,092 KiB** | **baseline** | **default** |
| 32 / 32 | 5.02 MiB | 23/30 · 23/30 | 0.9432 req/s | 1,059.6 / 1,677.4 ms | 4,451,752 KiB | **+660 KiB** | no: RSS gate |

All 120 measured requests returned HTTP 200, stopped normally, reused at least
25 prompt tokens, and matched the selected E3f prediction. Batch 32 reduced the
reported compute buffer by 5.01 MiB and retained 1.0116x throughput. Its median
latency was 1.0095x baseline and p95 was 0.9061x baseline, so every quality and
performance gate passed.

## Boundary

The smaller allocation did not become a process-level memory win. Conservative
maximum RSS increased by 660 KiB, missing the frozen requirement to save at
least 4,096 KiB. This repeats the E5f lesson at the marginal boundary: a
runtime allocation log explains mechanism, but only process evidence can
justify a product memory claim.

The retained requests also explain why the study stops here. Batch 64 needs 34
evaluated-prompt chunks across 30 requests, while batch 32 needs 63. Batch 16
would need 113. The predeclared staged design permits testing 16 only after 32
passes; because 32 fails the process-memory gate, E5g does not continue down
the batch ladder.

## Decision

Pareto64 retains 64/64 as the launcher default. Batch 32 is a valid negative
measurement: it preserves quality and performance, but adds no observed process
memory benefit. No threshold is weakened and no weighted score is used.

## Reproduction

The retained manifest is
[`e5g-30671733556.json`](../manifests/e5g-30671733556.json). Independent local
Python 3.10 ingestion reproduced the uploaded summary byte for byte at SHA-256
`374e5af3d8af8c022d76ff51f614c50e1dd25f8948fcc727fe3f983afad984b6`.
The exact order, immutable inputs, invocation binding, and gates are frozen in
[`../../experiments/e5g_contract.json`](../../experiments/e5g_contract.json).
