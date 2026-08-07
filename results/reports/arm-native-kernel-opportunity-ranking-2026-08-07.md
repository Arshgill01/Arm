# Arm-native kernel speed pass: opportunity ranking

Status: checkpoint 1, awaiting the required user review before implementation.

## Bound target

- Model: `Ministral-3-3B-Instruct-2512-Q4_K_M.gguf`, 2,146,497,824 bytes,
  SHA-256 `fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4`.
- Comparability source: llama.cpp b10216,
  `876a4321163249c43ca4e986818fab5ab081f282`.
- Upstream audit source: llama.cpp
  `fc3f10b3895ebb0ddfe1fcb7fd5950f2c1719339`, fetched 2026-08-07 UTC.
- Native profile host: four-core AArch64 Neoverse N2 with DotProd, I8MM,
  SVE2 and a 16-byte SVE vector length.
- Stable result host available for a later admitted A/B: eight-core Google
  Axion Neoverse V2 with standard Arm PMU access.
- Fixed comparison: identical model bytes, quantization, prompts, quality,
  CPU/core budget, batching and cache policy. Caching is excluded from the
  compute headline.

## Hot path

The retained E20a source profile measured the selected model at pp512, pp4096
and tg128. The timed build is diagnostic only, but it identifies the work to
optimize.

| Work | pp512 share | pp4096 share | tg128 share | Consequence |
| --- | ---: | ---: | ---: | --- |
| All `MUL_MAT` nodes | 68.56% | 23.75% | 96.66% | Q4_K matrix work is the only audited path with double-digit whole-model headroom across decode and ordinary prefill. |
| FFN gate + up projections | 31.43% | 10.85% | 30.74% | A real fused/tiled FFN can matter, but the useful matrix products are included in this share and cannot be removed. |
| Attention Q/K/V projections | 11.52% | 4.00% | 12.78% | Secondary to FFN and below the long-prompt admission floor. |
| Flash attention | 30.32% | 75.86% | 1.53% | Long-prefill is attention-bound, so a Q4_K kernel cannot produce a 20% pp4096 result by itself. |

E20c supplies a separate upper-bound clue for activation packing. Reusing one
q8_K pack across each FFN gate/up pair removed 26 conversions and reduced
median CPU seconds/request by only 0.2597%. Weighting the selected graph's
q8_K input widths makes those removed conversions approximately 11% of the
activation-pack input elements. The implied whole-service q8_K conversion
share is therefore about 2.3%, subject to the E20c cached-service boundary.
Even perfect removal would be only about 1.024x; a 2x packer would be about
1.012x. Fresh instrumentation must confirm this inference before it is used as
a claim.

The retained Axion runs counted `cpu_cycles`, `inst_retired`, `l1d_cache`,
`l1d_cache_refill`, and `l2d_cache`, but those whole-process counters do not
attribute individual kernels. They establish that PMU measurement is available
for the later matched A/B, not a kernel cause.

## Source dispatch audit

The exact b10216 source and the audited 2026-08-07 upstream commit have the same
relevant gap and dispatch structure.

1. Q4_K weights select repack traits with q8_K activations in
   `ggml/src/ggml-cpu/repack.cpp`.
2. On AArch64 with I8MM, Q4_K selects the 8x8 repack family. DotProd-only Arm
   selects 8x4.
3. `ggml_gemm_q4_K_8x8_q8_K` and the corresponding GEMV functions already have
   substantial AArch64 NEON/I8MM implementations in
   `ggml/src/ggml-cpu/arch/arm/repack.cpp`; a 32-byte-SVE branch also exists,
   but the retained N2 reports a 16-byte vector length and therefore uses the
   NEON/I8MM branch.
4. `ggml_quantize_mat_q8_K_4x4` and
   `ggml_quantize_mat_q8_K_4x8` have no Arm definitions. The fallback header
   maps them to scalar generic implementations in `repack.cpp`. Those routines
   scan and copy four 256-float rows, scalar-quantize 1,024 values, scalar-store
   the interleaved layout and scalar-accumulate 64 sums.
5. Arm `quantize_row_q8_K` still calls `quantize_row_q8_K_ref`, affecting the
   row/tail path.
6. llama.cpp's KleidiAI integration exposes only Q4_0 and Q8_0 weight kernels.
   It has no Q4_K/q8_K dispatch. The b10216 build fetches KleidiAI v1.24.0.

This means the activation packer is a genuine missing AArch64 implementation,
but the dominant Q4_K x q8_K multiply is already Arm-specific. Work on the
multiply must improve an existing I8MM path rather than claim to add a missing
Arm kernel.

## Ranked opportunities

### 1. Tune the dominant Q4_K x q8_K NEON/I8MM compute loop

- Artifact: a narrow rewrite of the selected 8x8 GEMM/GEMV kernel, beginning
  with the measured FFN shapes (K=3072 or 9216, N=9216 or 3072) and preserving
  the existing packed format.
- Whole-model ceiling: bounded by `MUL_MAT` at 68.56% pp512 and 96.66% tg128.
  A 1.20x kernel improvement would yield at most approximately 1.129x pp512 and
  1.192x tg128 if it covered every matrix node; actual coverage will be lower.
- Why first: it is the only small-enough source lane with measured double-digit
  end-to-end potential. The existing implementation has repeated scale/min
  decode, stack materialization of `bsums_arr`, and nested subblock setup worth
  measuring before any layout change.
- Cheap falsification: fixed real FFN-shape microbench plus counters and a
  same-binary dispatch toggle. Kill the exact rewrite if it cannot reach 1.10x
  directly or if its covered-node Amdahl projection is below 1.05x end to end.
- Main risk: the existing I8MM kernel may already be compute/weight-bandwidth
  efficient; source cleanup may not survive end to end.

### 2. Tiled FFN gate/up + SiLU multiply without full intermediates

- Artifact: one default-off, exact-role fused FFN operation for the 3072 x
  9216 selected-model shape; first combine gate/up tiles and post-op, then
  consider streaming the down projection only after a measured win.
- Whole-model ceiling: gate/up alone is 31.43% pp512, 30.74% tg128 and 10.85%
  pp4096. Adding the tiny GLU/MUL post-op raises the absolute removable-family
  bounds only slightly. Useful matrix multiply cannot be removed, so these are
  strict upper bounds, not expected gains.
- Why second: it can reduce complete intermediate writes/reads and has a
  plausible double-digit ceiling, unlike pack reuse. It is substantially more
  invasive than opportunity 1.
- Cheap falsification: a fixed-shape one-layer harness that counts materialized
  bytes. Kill gate/up-only fusion if the layer gain is below 1.10x; do not
  repeat E20c's activation-pack reuse.
- Main risk: tiling may lose reuse or parallel efficiency, and changed floating
  accumulation/order may require a quality rather than byte-identity gate.

### 3. Add exact NEON q8_K activation packers

- Artifact: byte-identical NEON implementations of 4x4, 4x8 and, only if
  measured, the row/tail packer, with generic functions retained for direct A/B.
- Whole-model ceiling: current retained service evidence implies about 2.3%
  total q8_K conversion share and therefore less than 1.024x under perfect
  removal. Fresh pp128/512/4096 and tg128 instrumentation may find a different
  workload-specific share.
- Why third: it is a clear upstream source gap and the smallest correctness
  surface, but current evidence says it is a bounded contribution rather than
  the desired visible speed result.
- Cheap falsification: instrument all three entry points and use the measured
  share to compute 2x, 4x and perfect Amdahl ceilings. Do not implement beyond
  the harness if no relevant workload can exceed 1.03x.
- Main risk: a large microbenchmark gain repeats the q8_0 result without moving
  whole-model inference.

## Recommendation at checkpoint 1

Proceed with opportunity 1. First add default-off timing/count instrumentation
to the existing Q4_K 8x8 dispatch and q8_K packers, capture pp128/512/4096,
tg128 and uncached service on native Arm, then optimize only the hottest inner
portion supported by the trace. Retain opportunity 3 as an upstreamable bounded
patch if the instrumentation is cheap, but do not let it consume the pass after
the ceiling is confirmed. Move to opportunity 2 immediately if the existing
I8MM loop does not expose a direct 1.10x microbenchmark improvement or a 1.05x
covered end-to-end projection.

## Audit commands

```text
git fetch --depth 1 origin 876a4321163249c43ca4e986818fab5ab081f282
git fetch --depth 1 origin master
rg -n 'ggml_quantize_mat_q8_K_4x[48]|quantize_row_q8_K|ggml_(gemm|gemv)_q4_K' ggml/src/ggml-cpu
rg -n 'Q4_K|q4_K|Q8_K|q8_K' ggml/src/ggml-cpu/kleidiai
```

Controlling evidence:

- `results/reports/e20a-cpu-node-profile.md`
- `results/manifests/e20a-30865578508.json`
- `results/reports/e20c-guarded-ffn-pair-no-win.md`
- `results/reports/e16a-repack-sidecar-feasibility.md`
- `results/reports/e22d-independent-axion-replication.md`
