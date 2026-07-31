# E5h Arm weight-repack boundary

E5h tests whether the selected Arm service can trade optimized weight layout
for a separate memory-constrained tier without changing the model, quantization,
context, prompt batch, cache behavior, or numerical output.

## Result

Native run
[`30672633366`](https://github.com/Arshgill01/Arm/actions/runs/30672633366)
completed both mechanism launches and the four-cell A–B–B–A matrix in 8m57s.
The result is `valid_selected_inference_memory_tier`: repacking stays enabled
by default, and the no-repack configuration is retained as a separate
low-memory tier.

| Profile | Model buffers | Quality per repetition | Throughput | Median / p95 HTTP | Ready | Maximum RSS | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **Repack on** | 2,024.36 MiB mapped + 2,038.92 MiB repack | **23/30 · 23/30** | **0.9295 req/s** | **1,049.6 / 1,858.4 ms** | 3,741.3 ms | 4,453,532 KiB | **default** |
| Repack off | 2,039.54 MiB mapped + 0 MiB repack | 23/30 · 23/30 | 0.4505 req/s | 2,416.0 / 3,304.3 ms | 2,121.4 ms | **2,381,264 KiB** | **memory tier** |

All 120 measured requests returned HTTP 200, stopped normally, reused at least
25 prompt tokens, and exactly matched the selected E3f prediction. Disabling
repack reduced conservative maximum RSS by 2,072,268 KiB and kept the process
below the frozen 3 GiB memory-tier ceiling. It retained 48.47% of baseline
throughput, while its 2.416-second median and 3.304-second p95 stayed inside
the predeclared 5/10-second latency ceilings.

## Mechanism

The baseline mechanism log contains distinct `CPU_Mapped` and `CPU_REPACK`
model buffers. The candidate log contains only the mapped model buffer. The
pinned llama.cpp `--no-repack` path sets `no_extra_bufts`, so model loading
does not offer KleidiAI or generic CPU extra buffer types. Every generated
recipe records the repack boolean and the candidate binds the upstream flag.

The 2,023.74 MiB model-buffer difference and 2,023.70 MiB process-RSS reduction
agree closely, connecting the source mechanism to the end-to-end result. The
throughput loss is equally material: the Arm-optimized repacked layout is the
right default when memory permits.

## Decision

Pareto64 keeps repacking enabled for the standard one-slot f16/256/64 cached
service. Operators with a memory-constrained deployment envelope can select
the independently gated tier with `--no-weight-repack`; the hashed recipe
records that choice. There is no weighted score and the slower tier does not
silently replace the default.

## Reproduction

The retained manifest is
[`e5h-30672633366.json`](../manifests/e5h-30672633366.json). Independent local
Python 3.10 ingestion reproduced the uploaded summary byte for byte at SHA-256
`e048f3e25d513430b49fd2ee0a140e8a0f82fe31d79b5fb0aafb36b470190faa`.
The exact order, immutable inputs, source proof, invocation binding, and gates
are frozen in
[`../../experiments/e5h_contract.json`](../../experiments/e5h_contract.json).
