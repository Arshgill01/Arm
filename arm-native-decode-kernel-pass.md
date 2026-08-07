# Arm-native decode kernel pass

Status: executed on 2026-08-07. The retained Q6_K kernel patch improved the
primary Axion `tg128` result by 4.37% over E23 while preserving exact output and
prefill. The double-digit decode target was not met, and the second Arm host
showed a direct-kernel gain but no material whole-model gain. See
`results/reports/e24-arm-native-decode-kernel-pass.md` and
`results/raw/e24c-summary.json`.

## Objective

Make streamed token generation visibly faster through an AArch64 kernel or
dataflow change.

Keep the same model, quantization, output quality, Arm CPU and core budget. The
primary result is decode/token-generation speed, not prompt processing.

## Pass

1. Freeze the E23 Q4_K prefill patch as the new baseline and profile `tg128`
   plus one representative live request on native Arm.
2. Resolve the exact decode dispatch and rank the few kernels that dominate
   generation. Start with `ggml_gemv_q4_K_8x8_q8_K` only if the profile agrees.
3. Inspect current llama.cpp and KleidiAI before changing source.
4. Build a direct correctness and timing harness around the selected decode
   kernel.
5. Implement the smallest high-upside AArch64 change and prove that real model
   generation executes it.
6. Validate numerical correctness and deterministic model output before speed.
7. Run matched E23-versus-E23-plus-decode A/B tests, then report the cumulative
   stock-versus-combined result.
8. If decode does not move materially, retain the negative result and pivot to
   the next measured decode kernel. Do not convert a prefill gain into a decode
   claim.
9. After a narrow win, test adjacent Q4_K models and a second Arm machine.
10. Finish with a cumulative upstream-ready patch series, clean reproducer and
    side-by-side streamed-generation demo.

## Initial source leads

Follow the profile, beginning with:

1. Q4_K × q8_K GEMV scale decoding, sums, register pressure and loop schedule;
2. Q5_K/Q6_K GEMV only where measured decode share justifies it; and
3. a deeper decode dataflow change only after the narrow kernels are exhausted.

The E23 vector-scale prefill patch must remain intact. Its rejected shared
decoder variant caused a 2.6% decode regression and must not be repeated.

## Rules

- Target a visible double-digit decode gain; approximately 20% remains the
  desired result, not a promise.
- `tg128` and live streamed generation control the decision. Prefill is a
  regression guard.
- No prompt caching, speculative-decoding headline, model swap, extra cores or
  relaxed quality.
- Microbenchmarks prove mechanism but never replace whole-model generation.
- Change one mechanism at a time and preserve failed experiments.
- Pause for user review after the decode profile/ranking and after the first
  end-to-end result.
- Additional paid Arm hardware has a USD 40 ceiling unless the user changes it.
  Use automatic deletion and verify final resource absence.

## Required output

- decode hot-path and dispatch report;
- ranked opportunities with whole-model ceilings;
- working AArch64 patch and execution proof;
- correctness and matched decode results;
- cumulative stock-versus-combined inference result;
- clean reproduction command and raw evidence;
- upstream-ready patch series; and
- live baseline-versus-optimized streamed-generation demo.

## Success

The pass succeeds when an Arm-specific source mechanism makes tokens visibly
arrive faster on the same hardware without weakening output quality or losing
the retained E23 prompt-processing gain.
