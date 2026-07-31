# E3b — same-task model-scale quality anchor

Status: **valid native comparison; no variant passed the frozen quality gate**.

## Result

[GitHub Actions run 30643977955](https://github.com/Arshgill01/Arm/actions/runs/30643977955)
completed the frozen E3b contract in 17m23s on one four-core Neoverse N2 job.
A second local invocation of the evidence ingester reproduced the workflow
summary byte for byte; its SHA-256 is
`8fd89b9ea82490935e7226dce4d8b20b346828bbb3aead8ab1805572481fb628`.

The 7B candidate improved the worst-repetition score by six tasks over 1.5B,
and both models were perfectly stable across repetitions. However, 7B reached
22/30 (73.33%): exactly one task below the predeclared 75% floor. The eligible
set and Pareto frontier therefore remain empty.

| Variant | Worse correct | Accuracy | Stable | Absolute floor | Eligible |
| --- | ---: | ---: | --- | --- | --- |
| Qwen2.5-1.5B Q4_K_M | 16/30 | 53.33% | yes | no | no |
| Qwen2.5-7B Q4_K_M | 22/30 | 73.33% | yes | no | no |

The 7B category scores were 2/5 arithmetic, 4/5 logic, 4/5 code reasoning,
4/5 data reasoning, 3/5 systems reasoning, and 5/5 evidence reasoning. No task,
answer, instruction, parser rule, or output was changed after observation.

## Protocol

- Official Apache-2.0 Qwen2.5 1.5B and 7B Instruct Q4_K_M packages, pinned by
  repository revision, exact file size, and SHA-256
- One pinned llama.cpp build with KleidiAI enabled and both validated Pareto64
  source patches applied; runtime `CPU_REPACK` buffers proved for each model
- The unchanged E3 suite: 30 tasks, two greedy repetitions, four threads,
  2,048-token context, eight-token cap, and the same first-standalone-A-D parser
- Eligibility: stable predictions, at least 75% worst-repetition accuracy, and
  no more than one task behind the best candidate
- Four alternating performance rounds per model, with one warm-up and three
  measured 128-input/64-output iterations in every round

## Application measurements

These are valid controlled measurements, but neither row is a deployable
recommendation because both failed quality eligibility.

| Variant | Package | Load median | Same-text total median | Quality max RSS |
| --- | ---: | ---: | ---: | ---: |
| Qwen2.5-1.5B Q4_K_M | 1.117 GB | 793.1 ms | 1,136.9 ms | 2,108,644 KiB |
| Qwen2.5-7B Q4_K_M | 4.683 GB | 2,732.6 ms | 5,129.0 ms | 8,972,028 KiB |

The 7B package was 4.19x larger, used 4.25x the quality-process peak RSS, and
took 4.51x as long on the same-text task workload. Under the separately frozen
`cloud-quality` deployment policy it also missed the 5-second same-text limit by
129.0 ms and the 8 GiB RSS limit by 583,420 KiB. Its 4.683 GB package and
2.733-second load remained inside their respective ceilings.

## Secondary token benchmark

Because both candidates use the same model family, tokenizer, quantization
type, runtime, and settings, this scale comparison is controlled. It remains
secondary to the application-quality gate.

| Variant | Encode median | Decode median | TTFT median | Total median |
| --- | ---: | ---: | ---: | ---: |
| Qwen2.5-1.5B Q4_K_M | 121.745 tokens/s | 32.302 tokens/s | 1,082.742 ms | 3,047.117 ms |
| Qwen2.5-7B Q4_K_M | 25.891 tokens/s | 8.221 tokens/s | 5,065.567 ms | 12,731.883 ms |

Relative to 1.5B, the 7B candidate was 4.70x slower for prompt processing and
3.93x slower for decode. Every iteration and process measurement remains in the
raw artifact; no outlier was removed.

## Decision

Do not lower the quality floor and do not promote either candidate. Preserve
E3b as a valid near-miss: it rejects the hypothesis that the 7B Q4_K_M package
is a sufficient quality anchor under the frozen application and 16 GiB cloud
policy.

The fail-closed Pareto64 plan independently returns `no_feasible_candidate` and
records all quality and SLO rejection reasons. A follow-up must be separately
predeclared and target a stronger quality-per-byte candidate without modifying
E3b. Hosted-runner limits still preclude energy, PMU, or controlled-governor
claims. Raw evidence remains in the 90-day artifact
`e3b-quality-anchor-30643977955-1`; the compact records are
[`../manifests/e3b-30643977955.json`](../manifests/e3b-30643977955.json) and
[`../plans/e3b-cloud-quality.json`](../plans/e3b-cloud-quality.json).
