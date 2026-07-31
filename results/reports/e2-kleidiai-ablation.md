# E2 — paired KleidiAI ablation

Status: **valid controlled comparison; predeclared primary threshold not met**.

## Result

[GitHub Actions run 30632406883](https://github.com/Arshgill01/Arm/actions/runs/30632406883)
completed successfully in 8m56s on one four-core Neoverse N2 job. Both variants
built, both upstream Phi-2 functional tests passed, and runtime logs showed a
KleidiAI model buffer only in the KleidiAI variant. The intended build difference
was `USE_KLEIDIAI` only.

The primary prompt-processing effect was a 1.03% median paired-round improvement
in three of four rounds. That does **not** meet the predeclared requirement of at
least 5% in at least three rounds, so E2 is a valid negative primary result.

## Protocol

- Model: identical Phi-2 Q4_0 artifact, SHA-256 pinned in the manifest
- Builds: generic and KleidiAI, both `GGML_NATIVE=OFF` and `CPU_ARCH=Armv8.6_1`
- Workload: 64 prompt tokens, 32 generated tokens, context 512, four threads
- Sampling: four rounds per variant; one warm-up plus three measured iterations
  per round, for 12 measured iterations per variant
- Order: generic/KleidiAI, KleidiAI/generic, generic/KleidiAI,
  KleidiAI/generic

## Measurements

The effect column is the median of four paired round-mean ratios. Pooled medians
summarize all 12 measured iterations and are shown for scale; they are not used
to decide the primary threshold.

| Metric | Generic pooled median | KleidiAI pooled median | Paired effect | Better rounds |
| --- | ---: | ---: | ---: | ---: |
| Prompt processing | 112.337 tokens/s | 113.797 tokens/s | +1.03% | 3/4 |
| Token generation | 21.819 tokens/s | 22.645 tokens/s | +4.42% | 4/4 |
| Time to first token | 615.115 ms | 605.645 ms | +1.24% | 3/4 |
| Total iteration | 2,034.282 ms | 1,975.842 ms | +3.48% | 4/4 |
| Whole-process wall time | 9.060 s | 8.895 s | +1.91% | 3/4, one tie |
| Maximum RSS | 3,243,400 KiB | 3,243,436 KiB | -0.0014% | 1/4 |

One KleidiAI prompt iteration in round three measured 100.621 tokens/s, versus
113.657 and 113.922 tokens/s in the other two measured iterations. It remains in
the declared analysis. Removing it after observing the result would invalidate
the predeclared decision rule.

Raw logs and JSON are retained in the 90-day Actions artifact
`e2-kleidiai-ablation-30632406883-1`; the validated record is
[`../manifests/e2-30632406883.json`](../manifests/e2-30632406883.json).

## Interpretation and limits

For this short-prompt Phi-2 workload, KleidiAI does not justify a headline claim
on the primary metric. It does show a smaller, consistent secondary benefit for
decode throughput and end-to-end latency, with effectively unchanged peak RSS.
That result argues for a workload-aware planner that retains both variants and
selects from measured objectives instead of assuming one backend always wins.

The legacy GGUF emits a missing-pre-tokenizer warning. This same-model ablation
is valid for relative performance, but it remains excluded from all generation-
quality claims. The hosted runner also blocks PMU access and exposes no CPU
governor, so E2 is screening evidence rather than final mechanism or energy
evidence.

## Decision

Do not promote the E2 primary hypothesis. Preserve the honest negative result
and the secondary decode/latency signal. E3 should use a modern, license-checked,
provenance-pinned model and measure output quality before extending the planner's
Pareto frontier.
