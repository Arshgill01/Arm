# E27 Arm long-context Flash Attention result

Status: accepted; every frozen gate passed.

## Decision

Retain the AArch64 SVE-build NEON `simd_gemm` microkernel. On a four-core
Google Axion/Neoverse V2 host, the unchanged Ministral 3B request improves from
`26.184890` to `76.201795` tokens/second at `pp2048` (`2.910144x`) and from
`15.355519` to `62.748160` at `pp4096` (`4.086359x`). The decode guard is
`0.999073x`, so the pass changes prefill time without trading away ordinary
decode throughput.

The claim is bounded to the tested builds, shapes, CPUs and models. A Qwen 1.5B
run on Neoverse N2 and a native build of current llama.cpp independently repeat
the improvement, but they do not establish universal performance on every Arm
CPU.

## Profile-led mechanism

The cumulative b10216 SVE build enters the tiled Flash Attention implementation
for the real model, but `simd-gemm.h` explicitly excludes
`__ARM_FEATURE_SVE` from its generic vector branch. Both QK multiplication and
V accumulation consequently use the final scalar `simd_gemm` fallback. At
`pp2048`, annotated samples put `22.43%` on the QK scalar `fmadd` and another
`14.81%` load plus `9.43%` scalar `fmadd` on V accumulation. K/V conversion,
online softmax, masking, tile selection and thread partitioning were materially
smaller and were left unchanged.

The patch adds one `GGML_SIMD && __ARM_FEATURE_SVE && __ARM_NEON` branch: a
four-row by sixteen-column fixed-width NEON FP32 FMA microkernel using
`float32x4_t` and `vfmaq_n_f32`. Four-column and scalar tail paths preserve
arbitrary matrix sizes. The existing non-SVE SIMD, RVV and scalar branches stay
in place, so unsupported build targets retain their prior implementation.

Real-inference `perf annotate` samples the candidate's `fmla v*.4s`
instructions inside `ggml_compute_forward_flash_attn_ext_tiled`. Flash
Attention's exclusive whole-profile share changes from `70.82%` to `17.51%`
at `pp2048`. The baseline shares are `39.53%`, `70.82%` and `82.13%` at
`pp512`, `pp2048` and `pp4096`, respectively, explaining why gains grow with
context length.

## Correctness and direct kernel result

The `5e-4` NMSE limit was frozen before timing. Nine reference-versus-tiled
cases cover head sizes 64 and 128, F16 and F32 K/V, three shapes and seeds 1,
17 and 42. All pass; maximum observed NMSE is `1.051861e-5` and maximum
absolute error is `4.448891e-4`.

Each direct result is the median of six fresh processes per variant in
reverse-balanced `baseline, candidate, candidate, baseline` order. Each
process contributes seven timed calls on cores 0–3.

| Shape | Scalar baseline | NEON candidate | Speedup |
| --- | ---: | ---: | ---: |
| d128, q512, kv512 | 127,134.438 us | 13,881.868 us | **9.158309x** |
| d128, q512, kv2048 | 720,747.553 us | 75,968.972 us | **9.487394x** |
| d128, q512, kv4096 | 1,532,731.785 us | 159,087.636 us | **9.634512x** |

All three exceed the frozen `1.20x` direct-admission gate.

## Matched whole-model result

Whole-model tests use the same model bytes, F16 K/V policy, flash-attention
setting, four pinned cores, batch/ubatch sizes and no-warmup policy. Each table
entry is the median of six fresh processes per variant, each with three
internal repetitions and the same reverse-balanced process order.

| Case | Baseline | Candidate | Ratio |
| --- | ---: | ---: | ---: |
| `pp512` | 55.920094 tok/s | 90.785846 tok/s | **1.623492x** |
| `pp2048` | 26.184890 tok/s | 76.201795 tok/s | **2.910144x** |
| `pp4096` | 15.355519 tok/s | 62.748160 tok/s | **4.086359x** |
| `tg128` | 25.766424 tok/s | 25.742545 tok/s | 0.999073x |

The prefill promotion gates and the `0.98` `pp512`/decode floors all pass.

## Adjacent model and second Arm CPU

GitHub Actions run `31248789575` tested Qwen2.5 1.5B Q4_K_M on four native
Neoverse N2 cores. Maximum NMSE is `1.117312e-5`. Direct speedups are
`6.787045x` at kv512 and `6.999456x` at kv2048; whole-model ratios are
`1.395054x` at `pp512`, `2.177965x` at `pp2048`, and `0.998213x` at `tg64`.
Every adjacent-model gate passed. Later named workflow runs, including the
combined E25/E26 branch head run `31253635705`, also completed successfully.

## Current upstream and live TTFT demo

The same standalone patch applies without offsets to current llama.cpp master
`69bf6437914596fbbc4caf09a7ac16f2acdd1a94`, which remained master when the
result was finalized. A clean native Axion build passes reference correctness
and repeats `9.486791x` and `9.526777x` direct speedups at kv2048 and kv4096.

The live demo runs one identical 8K-context request through separate baseline
and candidate `llama-completion` processes with seed 42, temperature zero, one
generated token and no prompt display. Baseline wall time is `841.26` seconds;
candidate time is `158.24` seconds, a **`5.316355x` time-to-first-token
improvement**. Both outputs have SHA-256
`5b043522e1771632ce2e4fe6ba7d10b99d119bdc56213e2a05a8ddf1c7e600a4`
and the retained diff is empty.

Run the standalone demo against already-built variants with:

```bash
scripts/e27_demo_arm_flash_attention.sh \
  /path/to/baseline/bin /path/to/candidate/bin \
  /path/to/model.gguf /path/to/prompt.txt /var/tmp/e27-demo
```

## Evidence and resource boundary

Primary compact evidence is under `results/raw/e27-axion-20260808`, current-
upstream evidence under `results/raw/e27-current-upstream-20260808`, and the
second-CPU run under `results/raw/e27-n2-31248789575`. Each directory retains
machine-readable summaries and SHA-256 inventories. The checksum-verified full
archive, including `perf.data` and complete disassembly, is preserved outside
Git at `/home/arshdeepsingh/work/e27-evidence-archives/e27-native-full-20260808.tar.gz`
with SHA-256
`8ace0a4a7bbf2bf8d35ade6680370e37cee1b78b4e044467c680979d0a804b6a`.

The Axion instance ran for `3.1435` hours with a six-hour automatic deletion
rule. Eight vCPUs at the published `$0.03787` starting rate imply about `$0.96`
of compute, with the short-lived 40 GB disk keeping the total far below the
frozen `$12` ceiling. Instance `arm-flash-e27-20260808` and its auto-delete boot
disk were explicitly deleted; retained exact-name post-delete inventories are
both empty.
