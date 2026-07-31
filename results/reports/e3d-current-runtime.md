# E3d — Qwen3.5 current-runtime KleidiAI frontier

Status: **valid native comparison; no variant passed the frozen quality gate**.

## Result

[GitHub Actions run 30650734222](https://github.com/Arshgill01/Arm/actions/runs/30650734222)
completed every frozen measurement in 15m35s on one four-core Neoverse N2 job.
The run's post-processing step then rejected the evidence because current
`llama-bench` reports a nine-character commit abbreviation while the ingester
expected eight. The always-upload artifact preserved all measurements. After
the ingester derived the abbreviation from the frozen full commit, an
independent Python 3.10 ingestion accepted the artifact; the retained summary's
SHA-256 is
`887f202cb150348a0dfd0029b0f1dc2256809c66acc710194b336ef73aba044b`.
Clean reproducibility run
[`30652188393`](https://github.com/Arshgill01/Arm/actions/runs/30652188393)
then passed the corrected workflow end to end from commit `fbe770b`.

Both quantizations were stable across two repetitions and scored 20/30
(66.67%). They missed the unchanged 75% absolute floor, so the eligible set and
Pareto frontier are empty.

| Variant | Worse correct | Accuracy | Stable | Absolute floor | Eligible |
| --- | ---: | ---: | --- | --- | --- |
| Qwen3.5-4B Q4_0 | 20/30 | 66.67% | yes | no | no |
| Qwen3.5-4B Q8_0 | 20/30 | 66.67% | yes | no | no |

Q4_0 scored 2/5 arithmetic, 5/5 logic, 2/5 code reasoning, 3/5 data
reasoning, 3/5 systems reasoning, and 5/5 evidence reasoning. Q8_0 exchanged one
logic answer for one data answer and otherwise matched those category totals.
No task, answer, instruction, parser rule, model output, or policy threshold was
changed after observation.

## Protocol

- Official Apache-2.0 Qwen3.5-4B source and one separately pinned Apache-2.0
  Unsloth GGUF producer revision
- Exact Q4_0 and Q8_0 package sizes and SHA-256 checksums
- Upstream llama.cpp tag `b10208` with its pinned KleidiAI v1.24 dependency
- Real OpenAI-compatible HTTP requests, model-Jinja non-thinking mode, two
  greedy repetitions, four threads, 2,048-token context, and eight-token cap
- The unchanged 30-task suite and first-standalone-A-D parser
- Three cyclic performance rounds per variant, each retaining one warm-up and
  three measured 128-input/64-output iterations

A dedicated verbose `llama-bench` probe proved a `CPU_KLEIDIAI` model buffer
for both quantizations. Quantization was the only candidate-level difference.

## Application measurements

These are controlled measurements, not deployment recommendations, because
both candidates failed quality eligibility.

| Variant | Package | Load median | Same-text total median | Quality max RSS |
| --- | ---: | ---: | ---: | ---: |
| Q4_0 | 2.583 GB | 2,259.5 ms | 1,700.0 ms | 7,827,612 KiB |
| Q8_0 | 4.482 GB | 16,590.0 ms | 988.1 ms | 11,368,620 KiB |

Q4_0 met every resource ceiling in the frozen `cloud-quality` policy but failed
accuracy. Q8_0 additionally exceeded the 10-second load ceiling by 6,590.0 ms
and the 8 GiB RSS ceiling by 2,980,012 KiB. Both package sizes and application
latencies met their ceilings.

## Secondary token benchmark

| Variant | Encode median | Decode median | TTFT median | Total median |
| --- | ---: | ---: | ---: | ---: |
| Q4_0 | 59.330 tokens/s | 12.620 tokens/s | 2,157.4 ms | 7,225.4 ms |
| Q8_0 | 112.774 tokens/s | 14.961 tokens/s | 1,135.0 ms | 5,414.3 ms |

On the proven KleidiAI path, Q8_0 delivered 1.90x Q4_0 prompt throughput,
1.19x decode throughput, and a 1.33x shorter combined benchmark time. It cannot
override the quality, load, or memory gates. All repetitions remain in the raw
artifact; no outlier was removed.

## Decision

Do not promote either E3d candidate and do not relax the quality floor. The
independent fail-closed Pareto64 plan returns `no_feasible_candidate` and
records every rejection.

E3d rejects the hypothesis that immediate-answer quantization alone on this
current 4B model supplies the quality anchor. E3e was independently
predeclared before thinking-mode output was observed and tests whether bounded
reasoning compute changes that frontier. Hosted-runner limits still preclude
energy, PMU, or controlled-governor claims. Raw evidence remains in the 90-day
artifact `e3d-qwen35-kleidiai-30650734222-1`; compact records are
[`../manifests/e3d-30650734222.json`](../manifests/e3d-30650734222.json) and
[`../plans/e3d-cloud-quality.json`](../plans/e3d-cloud-quality.json).
