# E5i Arm Flash Attention ablation

E5i tests whether the selected Arm service's resolved Flash Attention auto mode
delivers a material end-to-end win over the disabled graph. Model, numerical
representation, repacked weights, f16/256/64 serving profile, prompt cache,
request order, and concurrency remain fixed.

## Result

Native run
[`30674023380`](https://github.com/Arshgill01/Arm/actions/runs/30674023380)
completed the two mechanism launches and four-cell off–auto–auto–off matrix in
7m12s. The result is `valid_selected_inference_no_flash_attention_win`: auto
missed the frozen throughput-improvement and p95-latency gates.

| Mode | Resolved mechanism | Compute buffer | Quality per repetition | Throughput | Median / p95 HTTP | Maximum RSS | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Flash off | disabled · no fused-op success | 9.56 MiB | **23/30 · 23/30** | 0.9013 req/s | 1,117.6 / 1,750.9 ms | 4,458,508 KiB | ablation baseline |
| **Flash auto** | **auto · Flash Attention enabled** | 10.03 MiB | **23/30 · 23/30** | **0.9303 req/s** | **1,048.5 / 1,856.4 ms** | **4,451,124 KiB** | configured default; no new claim |

All 120 measured requests returned HTTP 200, stopped normally, reused at least
25 prompt tokens, and exactly matched the selected E3f prediction. Auto improved
repeated median throughput by 1.0322x, below the predeclared 1.05x minimum. Its
median HTTP latency improved by 6.18%, but p95 increased by 6.03%, failing the
non-regression gate. Maximum RSS was 7,384 KiB lower, inside the overhead bound.

## Mechanism

The verbosity-four auto launch records `flash_attn = auto`, a successful fused
operation probe, and `Flash Attention enabled`. The disabled launch records
`flash_attn = disabled` and no success line. Generated recipes bind the upstream
mode, while timed outer commands independently prove the off override and the
unflagged auto default.

The fused graph uses a 10.03 MiB compute buffer versus 9.56 MiB when disabled.
That small reported increase does not translate into higher process RSS; auto's
conservative maximum is lower. As in the batch studies, allocation logs explain
mechanism while process evidence decides memory claims.

## Decision

Pareto64 retains `auto` as its configured upstream-default mode, but E5i does
not promote or advertise a material Flash Attention serving win. The bounded
`--flash-attention off` override remains available for separately validated
workloads. No threshold is weakened and no weighted score is used.

## Reproduction

The retained manifest is
[`e5i-30674023380.json`](../manifests/e5i-30674023380.json). Independent local
Python 3.10 ingestion reproduced the uploaded summary byte for byte at SHA-256
`ca41dd4c8ce7eaec196ac4d6a1320f689755ae4fb9e5d13bb4061f3c24a46ba2`.
The exact order, immutable inputs, source proof, invocation binding, and gates
are frozen in
[`../../experiments/e5i_contract.json`](../../experiments/e5i_contract.json).
