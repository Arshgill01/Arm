# E25 Arm Q4_K decode-layout result

Status: primary target met.

## Decision

Retain the decoded-metadata Q4_K representation and matching AArch64 GEMV.
On the frozen four-core Google Axion configuration, Ministral 3B Q4_K_M
`tg128` improves from `26.102599` to `29.111489` tokens/second, or
`1.115272x`. This exceeds E25's frozen `1.10x` whole-model target without a
model change, extra cores, prompt caching, speculative decoding or a relaxed
output policy.

The claim is deliberately narrower than “all Arm CPUs.” Q4_K_S and Qwen
Q4_K_M are positive on Axion, but Qwen is neutral on Neoverse N1 because that
CPU lacks I8MM and the real-model packed dispatch remains gated off there.

## Mechanism

The retained patch packs Q4_K weights in the four-byte lane-dot layout and
adds a 128-byte decoded scale/min sidecar for every eight 256-element Q4_K
rows. The AArch64 dot-product GEMV reads those decoded bytes directly, removes
the hot six-bit metadata decoder, and reduces Q8 block sums directly from their
source scalars instead of round-tripping a temporary NEON vector through the
stack. Prefill uses the matching four-byte Q4 layout with the existing
eight-byte Q8 activation layout and performs the same direct scalar block-sum
reduction.

The sidecar is 128 bytes per 1,152 bytes of packed Q4 weights (`11.11%`), not a
second weight copy. Whole-process median RSS increases by 159,744 KiB. The
measured readiness proxy improves by 0.206 seconds, so the extra decode done at
model preparation does not create a startup regression on this host.

GDB captured 2,496 real-model calls to the new symbol, including the two full
principal matrices split across four worker chunks: 3,072 × 2,304 and
9,216 × 768. The dispatch counts and shapes are preserved in the raw evidence.

## Matched results

All whole-model numbers use fresh processes, four threads pinned to cores 0–3,
CPU-only inference, flash attention, the same model bytes and reverse-balanced
`E24, E25, E25, E24` ordering. Each process contributes three internal
repetitions.

| Host and model | Case | E24 | E25 | Ratio |
| --- | --- | ---: | ---: | ---: |
| Axion V2, Ministral 3B Q4_K_M | `tg128` | 26.102599 | 29.111489 | **1.115272x** |
| Axion V2, Ministral 3B Q4_K_M | `pp512` | 55.978004 | 55.159495 | 0.985378x |
| Axion V2, Ministral 3B Q4_K_S | `tg128` | 27.218004 | 31.091333 | **1.142308x** |
| Axion V2, Qwen2.5 1.5B Q4_K_M | `tg128` | 51.903897 | 56.450787 | **1.087602x** |
| Neoverse N1, Qwen2.5 1.5B Q4_K_M | `tg128` | 29.369348 | 29.360752 | 0.999707x |

The `pp512` result passes the inherited 0.98 prefill floor. The E24 Q6_K
direct guard is also preserved: candidate/baseline ratios are `1.001526x` and
`1.009506x` on the two required shapes.

## Direct and correctness proof

Reference correctness ran before the accepted timings. Q4_K GEMV NMSE is at
most `1.9347e-13` on the principal shapes. The mixed four-byte-Q4/eight-byte-Q8
GEMM harness covers block counts 1, 2, 3, 12 and 36 across three seeds; its
worst NMSE is `6.4704e-13`. The unchanged Q6_K guard's worst NMSE is
`3.2218e-13`.

| Host | Shape | E24 layout | Decoded layout | Ratio |
| --- | --- | ---: | ---: | ---: |
| Axion V2 | 3,072 × 2,304 | 194.654 us | 135.227 us | **1.439461x** |
| Axion V2 | 9,216 × 768 | 201.284 us | 137.978 us | **1.458812x** |
| Neoverse N1 | 3,072 × 2,304 | 381.520 us | 259.440 us | **1.470552x** |
| Neoverse N1 | 9,216 × 768 | 387.040 us | 263.880 us | **1.466727x** |

The N1 direct result proves that the dot-product kernel itself is portable. Its
neutral whole-model result is explained by the production dispatch: without
I8MM, the model does not choose the packed tensor trait. This limits the
generality claim and is not hidden as benchmark noise.

## Rejected experiments

The first layout family reused the existing four-byte Q4 representation. It
reached about `1.18x` directly but only `1.069658x` whole-model and was rejected.
A vector-return metadata decoder was neutral. The initial decoded sidecar
layout regressed `pp512` to `0.908786x`; a matching prefill kernel repaired it.
A scale-conversion hoist then regressed the balanced prefill ratio to
`0.973611x` and was rejected. Direct scalar Q8 block-sum reductions produced
the accepted clean-run `0.985378x` prefill ratio. The repaired layout initially
reached `1.095596x` whole-model; the GEMV block-sum cleanup moved the final clean
run to `1.115272x`. Two further screens—paired output tiles and forced subblock
unrolling—regressed the direct kernel and are retained as negative evidence.

## Current upstream and live demo

The standalone current-master patch targets llama.cpp
`69bf6437914596fbbc4caf09a7ac16f2acdd1a94`. It applies without offsets, passes
`diff --check`, builds on x86_64 and natively on Axion, runs a real-model smoke
test, and retains `1.44–1.48x` direct speedups on the primary shapes.

The named `E25 Q4_K decode-layout validation` workflow passed on GitHub run
`31251352112`. Its independent Arm runner passed patch application, build,
GEMV/GEMM reference checks and both direct gates (`1.351760x` and `1.327902x`).

The streamed baseline/candidate demo uses the same greedy policy and records
both live outputs and timings. The streams are coherent but not byte-identical:
the changed floating-point reduction order eventually changes a greedy token.
This is disclosed rather than treated as a quality-equivalence proof. The
reference-kernel NMSE checks above are the controlling numerical-correctness
evidence, and no sampling or output policy was relaxed.

Run the complete Arm reproducer with the frozen primary model:

```bash
MODEL_PATH=/path/to/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
  experiments/e25_q4_layout_reproduce.sh /var/tmp/e25-reproduce
```

## Evidence boundary

The machine-readable decision is in `results/raw/e25-summary.json`. Baseline
profiling is under `results/raw/e25a-axion-20260808`, primary and current-
upstream evidence under `results/raw/e25b-axion-20260808`, and the independent
N1 result under `results/raw/e25c-n1-20260808`. Each retained directory has a
verified SHA-256 inventory. The named GitHub lane is under
`results/raw/e25d-31251352112`.

The primary Axion VM ran for 2.4592 hours; the earlier profiling Axion and N1
validation machines were shorter-lived. Using Google's published starting
rates for [Axion](https://cloud.google.com/products/axion) (`$0.03787` per
vCPU-hour) and [T2A](https://cloud.google.com/products/compute/pricing/general-purpose)
(`$0.0385` for a one-vCPU standard VM), the conservative total E25 compute estimate is below `$1.20`,
well under the `$12` ceiling; disk cost is negligible at these durations.
All three E25 instances and their boot disks were explicitly deleted, and the
post-delete exact-name inventories are empty. The retained closure files bind
the instance IDs, timestamps, delete output and empty inventories.
