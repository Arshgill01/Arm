# E6b — native Arm Q8 vector-store optimization

Status: **valid hot-path win; end-to-end inference neutral**.

## Result

[GitHub Actions run 30640282768](https://github.com/Arshgill01/Arm/actions/runs/30640282768)
completed the frozen E6b contract in 8m39s on a four-core Neoverse N2. A
separate local invocation of the evidence ingester reproduced the workflow
summary byte for byte. The only source difference was the frozen patch to
`quantize_row_q8_0` in llama.cpp.

| Values | Baseline | Patched | Median paired ratio | Improved rounds |
| ---: | ---: | ---: | ---: | ---: |
| 4,096 | 5.08–5.09 GB/s | 10.13–10.20 GB/s | **2.001x** | 4/4 |
| 65,536 | 5.11–5.12 GB/s | 10.37–10.39 GB/s | **2.029x** | 4/4 |
| 655,360 | 5.09 GB/s | 10.33–10.34 GB/s | **2.029x** | 4/4 |

The throughput unit above is the `GB/s` label emitted by upstream
`test-quantize-perf`. All 20,000-iteration rounds are retained. Order alternated
baseline/patched and patched/baseline on CPU 0; no outlier was removed.

## Mechanism and correctness

The pinned Arm implementation converted eight NEON vectors to integer values,
then extracted and wrote 32 individual byte lanes. The patch narrows those
values in vector registers and emits two 128-bit stores. Native emitted assembly
shows the intended mechanism:

| Assembly measure | Baseline | Patched |
| --- | ---: | ---: |
| Static instructions in function | 155 | 98 |
| Scalar byte stores | 32 | 0 |
| Vector narrowing instructions | 0 | 6 |
| 128-bit vector stores | 0 | 2 |

Correctness was checked at three levels: a standalone comparison over 8,224
deterministic finite values including an all-zero block was bit-identical, both
builds passed upstream `test-quantize-fns`, and all responses, token counts, and
termination reasons on the frozen 30-task Qwen suite were unchanged.

## Real-model guardrail

Four paired Qwen2.5-1.5B-Instruct Q4_0 rounds used 128 input tokens, 64 output
tokens, four threads, one warm-up, and three measured iterations. This model
benchmark remained effectively neutral, as expected for a narrowly bounded
activation-quantization helper:

| Metric | Median paired ratio | Worst observed paired ratio | Gate |
| --- | ---: | ---: | --- |
| Prompt throughput | 1.0004x | 0.9905x | passed |
| Decode throughput | 1.0000x | 0.9969x | passed |
| TTFT, lower is better | 1.0007x | 0.9909x | passed |
| Total time, lower is better | 1.0003x | 0.9916x | passed |

Peak RSS was 2,005,348 KiB for both variants. Every inference ratio exceeded
the frozen 0.98 guardrail. These measurements establish no whole-model speedup;
the accepted claim is a roughly 2x improvement of the isolated Q8_0 quantizer
with no detected model-level regression.

## Decision and limits

Accept the patch as Pareto64's performance-oriented Arm source contribution. It
passes every predeclared direct, mechanism, correctness, inference, and memory
gate without a weighted score.

The hosted runner exposes no usable PMU, energy meter, or governor control, so
the result does not claim cycles, energy savings, or device-wide performance.
Before proposing it upstream, rebase the small patch onto current llama.cpp and
repeat its upstream CI matrix. Raw evidence remains in the 90-day artifact
`e6b-q8-vector-store-30640282768-1`; the reviewable compact record is
[`../manifests/e6b-30640282768.json`](../manifests/e6b-30640282768.json).
