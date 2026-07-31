# E1 — Arm LLM-Runner smoke

Status: **pass for native build/test/inference feasibility**; **not valid for a
speedup or quality claim**.

## Result

[GitHub Actions run 30631789118](https://github.com/Arshgill01/Arm/actions/runs/30631789118)
completed successfully in 5m47s on a four-core Neoverse N2 runner. It built the
pinned Arm LLM-Runner revision with its llama.cpp backend, explicit Armv8.6
DotProd/FP16/I8MM target, and KleidiAI enabled. The pinned upstream Phi-2 test
passed in 10.70 seconds and the real inference benchmark exited successfully.

KleidiAI use is supported by three independent signals: configure reported it
enabled, the build compiled its NEON/DotProd/I8MM kernels, and inference logged a
`CPU_KLEIDIAI` model buffer. This proves execution through the optimized backend;
it does not prove an improvement until a same-job generic baseline exists.

## Workload and measurements

- Model: Phi-2 Q4_0, 1.60 GB, SHA-256 pinned in the manifest
- Workload: 64 prompt tokens, 32 generated tokens, context 512
- Threads: 4
- Trials: 1 warm-up plus 3 measured iterations
- Maximum RSS: 3,243,448 KiB (about 3.09 GiB)
- Whole benchmark process: 9.07 seconds at 361% CPU

| Metric | Median | p95 | Population CV |
| --- | ---: | ---: | ---: |
| Prompt processing | 113.578 tokens/s | 113.916 tokens/s | 5.77% |
| Token generation | 22.165 tokens/s | 22.417 tokens/s | 0.66% |
| Time to first token | 606.448 ms | 681.307 ms | 5.63% |
| Total iteration | 2,007.211 ms | 2,087.580 ms | 2.11% |

Raw measured iterations and provenance are retained in the 90-day Actions
artifact `e1-llm-runner-30631789118-1`; the compact validated record is
[`../manifests/e1-30631789118.json`](../manifests/e1-30631789118.json).

## Validity limits

The legacy GGUF warns that it lacks a recognized pre-tokenizer and that
generation quality is degraded. The upstream functional test still passes, so
the artifact is adequate for E1 execution feasibility, but it is excluded from
quality claims. E2 must use a modern, provenance-pinned model artifact before
quality equivalence is assessed.

This run also has no generic/KleidiAI-off measurement. Its absolute timing is a
smoke baseline only; it is not evidence of an Arm optimization delta.

## Failure evidence that led here

The successful configuration records `GGML_NATIVE=OFF`. The preceding attempt
showed that llama.cpp native detection produced a Neoverse N2 feature string
containing SVE2 names followed by `+nosve`; its substring-based KleidiAI source
selection nevertheless compiled SVE assembly, which the final processor mode
rejected. Disabling that conflicting detection retained the explicit LLM-Runner
target and built the intended DotProd/I8MM path. The detection behavior is now a
candidate for a tested upstream source patch rather than a discarded CI failure.

## Decision

E1 passes. Proceed to an alternating, same-job E2 comparison of generic versus
KleidiAI builds, while separately replacing this old Phi-2 artifact for the
quality-constrained E3 path.
