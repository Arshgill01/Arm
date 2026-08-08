# E24 Arm-native decode kernel pass

Status: execution complete; retained positive result, double-digit decode target not met.

## Decision

Retain the Q6_K AArch64 patch as a measured kernel optimization. Do not present
it as a universal or double-digit whole-model decode improvement.

On the primary Google Axion Neoverse V2 host, the patch increased Ministral 3B
Q4_K_M `tg128` from `24.872925` to `25.9593425` tokens/second (`1.043679x`,
`+4.37%`) over the retained E23 baseline. The same kernel mechanism remained
positive on adjacent Axion models, but the independent Neoverse N2 Qwen run was
only `+0.33%` end to end. That N2 result is not material and limits the claim.

## Matched results

All whole-model cells use six fresh processes per variant, three internal
repetitions per process, four pinned cores and reverse-balanced ordering.

| Host and model | Comparison | Baseline | Candidate | Change |
| --- | --- | ---: | ---: | ---: |
| Axion V2, Ministral 3B Q4_K_M | E23 vs E23 + Q6 decode, `tg128` | 24.872925 | 25.959343 | +4.37% |
| Axion V2, Ministral 3B Q4_K_S | E23 vs E23 + Q6 decode, `tg128` | 26.556992 | 27.261580 | +2.65% |
| Axion V2, Qwen2.5 1.5B Q4_K_M | E23 vs E23 + Q6 decode, `tg128` | 49.497838 | 51.916711 | +4.89% |
| Neoverse N2, Qwen2.5 1.5B Q4_K_M | E23 vs E23 + Q6 decode, `tg128` | 37.758168 | 37.884631 | +0.33% |
| Axion V2, Ministral 3B Q4_K_M | stock vs E23 + Q6, `pp128` | 69.925075 | 77.525973 | +10.87% |
| Axion V2, Ministral 3B Q4_K_M | stock vs E23 + Q6, `pp512` | 51.880033 | 55.962300 | +7.87% |
| Axion V2, Ministral 3B Q4_K_M | stock vs E23 + Q6, `tg128` | 24.663235 | 25.772796 | +4.50% |

The decode-only patch preserved E23 prefill: the Axion candidate/baseline ratios
were `0.999658x` at `pp128` and `0.999741x` at `pp512`.

## Mechanism and direct proof

Profiling first ranked Q4_K GEMV at `55.78%` and Q6_K GEMV at `33.51%` of
exclusive `tg128` cycle samples. Corrected Q4_K I8MM and forced-unroll variants
either regressed or missed the direct gate, so the pass pivoted to the measured
Q6_K opportunity.

The retained Q6_K change removes a 256-byte widened-scale scratch array,
consumes scale rows once for both bias and dequantization, stores eight integer
accumulators in two NEON vectors, and loads Q6 column pairs at their point of
use. Real-model profiling assigned `31.00%` of candidate generation samples to
the changed symbol.

| Source and host | Shape | Baseline | Candidate | Direct ratio |
| --- | --- | ---: | ---: | ---: |
| b10216, Axion V2 | 3072 x 2304 | 412.785 us | 339.252 us | 1.216750x |
| b10216, Axion V2 | 9216 x 768 | 413.223 us | 339.844 us | 1.215920x |
| current master `cb26014d`, Axion V2 | 3072 x 2304 | 424.738 us | 346.457 us | 1.225947x |
| current master `cb26014d`, Axion V2 | 9216 x 768 | 426.391 us | 348.015 us | 1.225209x |
| b10216, Neoverse N2 | 3072 x 2304 | 710.497 us | 529.489 us | 1.341854x |
| b10216, Neoverse N2 | 9216 x 768 | 711.869 us | 530.809 us | 1.341103x |

The current-master patch applied without offsets, passed `diff --check`, built
with the local AArch64 cross-toolchain, then built and executed natively on
Axion. No open llama.cpp PR or issue was found by searches for `q6_K gemv
repack`, `ggml_gemv_q6`, or `Q6_K Arm` on 2026-08-07.

## Correctness and demo

All 12 generic-reference cases passed on both Arm hosts. The worst retained
Axion NMSE was `3.66714270791e-13`. Baseline and candidate model output was
byte-identical for the primary, both adjacent models and the N2 run. The
128-token streamed demo also produced identical SHA-256
`5927ede3b3acd5734f3fa94f48ff36ea64cfa62cfe82abb28c3d5b986e809295`.

The demo script disables stdout buffering and prints the baseline and candidate
streams live. One sequential demo is retained for inspection, but its timing is
not used as the performance claim; the reverse-balanced six-process matrix is
the controlling measurement.

Run the primary reproducer on an AArch64 host with at least four CPUs:

```bash
MODEL_PATH=/path/to/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
  experiments/e24_decode_kernel_reproduce.sh /var/tmp/e24-reproduce
```

Run the streamed demonstration from the complete baseline and candidate binary
directories produced by the experiment:

```bash
scripts/demo_arm_q6_k_decode.sh BASELINE_BIN CANDIDATE_BIN MODEL OUTPUT_DIR
```

## Upstream boundary

The current-master code patch is
`patches/llama.cpp/current/0001-arm-q6-k-gemv-reduce-scale-and-load-overhead.patch`.
llama.cpp's `AGENTS.md` prohibits agents from authoring commit messages, pushing
to that repository or submitting PR text. The repository therefore contains a
clean, tested code patch but no AI-authored upstream commit or PR. A human must
review every line, write the submission metadata, disclose AI use, run the
upstream-required full CI/perplexity/backend checks and own maintenance before
submission.

## Evidence and resource closure

The machine-readable result is `results/raw/e24c-summary.json`; all derived
gates pass. Raw evidence is retained under `results/raw/e24a-axion-20260807`,
`results/raw/e24b-axion-20260807`, `results/raw/e24c-axion-20260807` and
`results/raw/e24c-n2-31174841481`. The independent GitHub run is
<https://github.com/Arshgill01/Arm/actions/runs/31174841481>.

The complete retained archive and its independently stored SHA-256 are recorded
in `results/raw/e24c-archive.txt`. Its member listing was read back successfully
after creation.

The Axion VM existed from `2026-08-07T10:18:47.676Z` until verified absence at
`2026-08-07T12:00:32Z`. At the published `c4a-highcpu` starting rate of
`$0.03788` per vCPU-hour, eight vCPUs for that interval are about `$0.52` of
compute, plus the short-lived 30 GB boot disk. This is below the `$40` ceiling.
The exact instance and auto-delete disk both returned empty post-deletion
inventories. Pricing source: <https://cloud.google.com/products/compute/pricing/general-purpose>.

## Outcome against the pass

Every required artifact and validation lane is complete, including the two
mandatory user checkpoints. The implementation makes the primary matched
generation path measurably faster and preserves output and prefill, but it does
not meet the requested double-digit decode target and does not generalize to a
material end-to-end gain on the second Arm host. Any submission claim must keep
those limits visible.
