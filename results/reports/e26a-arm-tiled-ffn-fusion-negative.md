# E26a Arm tiled-FFN fusion: native negative result

## Decision

Reject the production fusion. Neither the initial gate/up/SwiGLU tiling nor the
mandated extension through the down projection cleared the `1.15x` complete
one-layer gate on four Google Axion (Neoverse V2) cores. The implementation is
default-off and retained only as a rejected current-upstream patch; no rejected
hook is enabled in the repository's production patch path.

## Controlled setup

- Google Cloud `c4a-highcpu-4`, instance `arm-e26-20260808`, four cores pinned
  to `0-3`, native Neoverse V2/I8MM build.
- llama.cpp `876a4321163249c43ca4e986818fab5ab081f282` with the unchanged E23 and
  E24 baseline patches.
- Ministral 3 3B Instruct Q4_K_M, 2,146,497,824 bytes, SHA-256
  `fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4`.
- Complete dense FFN harness: Q4_K gate, Q4_K up, split SwiGLU and Q4_K or Q6_K
  down projection, dominant `3072 x 9216` shape.

## Results

The first 64-row gate/up-only mechanism wrote 2,048 rather than 73,728
intermediate bytes, but regressed from a `0.669214 ms` baseline median to
`0.6945035 ms` (`0.963586x`). Its output was byte-identical.

The fallback tiled gate/up/SwiGLU and accumulated the down projection using the
existing E23/E24 kernels as black boxes. Numerical error from the changed down
accumulation order was bounded at NMSE `2.42e-14` and maximum absolute error
`0.0029296875` in the Q6_K decode check.

| Down/type case | Best tile | Baseline ms | Candidate ms | Speedup | Saved bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Q4_K, 1 token | 6144 | 0.665090 | 0.667487 | 0.996409x | 24,576 |
| Q6_K, 1 token | 6144 | 0.824486 | 0.795706 | 1.036169x | 24,576 |
| Q4_K, 32 tokens | 3072 | 8.940103 | 9.019320 | 0.991217x | 1,966,080 |
| Q6_K, 32 tokens | 6144 | 9.975037 | 9.845738 | 1.013132x | 786,432 |

The best result is `1.036169x`, 11.4 percentage points below the cheap gate.
Avoided tensor writes are too small relative to quantized weight reads and the
extra tile barriers, activation repacking and partial-down accumulation. This
is an inference from the measured sweep, not a hardware-counter attribution.

## Gate consequences

The contract permits broad graph integration only after the one-layer gate.
Therefore `pp128`, `pp512`, `tg128`, the live-request comparison, and the
adjacent-model/second-CPU run were not executed. Reporting those after this
failure would spend resources on a mechanism already barred from promotion.

The rejected patch remains at
`patches/llama.cpp/e26/rejected/0001-ggml-cpu-tile-q4-k-ffn-swiglu.patch`
for reproducibility. It applies to the frozen current-upstream commit and the
pinned benchmark revision, binds exact gate/up/down FFN roles, falls back for
unsupported graphs, and does not modify the E23/E24 inner kernels.

Raw commands, build logs, host inventory, model identity, matched samples,
numerical outputs and tile sweep are retained under
`results/raw/e26a-axion-negative-20260808/`. The machine-readable decision is
`results/raw/e26a-axion-negative-summary.json`.
