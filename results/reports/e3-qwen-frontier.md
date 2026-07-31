# E3 — quality-constrained Qwen runtime frontier

Status: **valid native comparison; no variant passed the frozen quality gate**.

## Result

[GitHub Actions run 30635472160](https://github.com/Arshgill01/Arm/actions/runs/30635472160)
completed successfully in 9m30s on one four-core Neoverse N2 job. The independent
artifact ingester accepted every checksum, source revision, task, repetition,
cyclic round, process measurement, and provenance field without modification.

All variants produced identical parsed predictions across their two repetitions,
but none reached the predeclared 75% accuracy floor. The eligible set and Pareto
front are therefore empty.

| Variant | Worse correct | Accuracy | Stable | Eligible |
| --- | ---: | ---: | --- | --- |
| llama.cpp Q4_0 | 14/30 | 46.67% | yes | no |
| llama.cpp Q4_K_M | 16/30 | 53.33% | yes | no |
| MNN int4 | 4/30 | 13.33% | yes | no |

## Protocol

- Model family: official Apache-2.0 Qwen2.5-1.5B-Instruct packages
- Runtimes: llama.cpp Q4_0, llama.cpp Q4_K_M, and MNN int4 through the pinned
  LLM-Runner common API
- Quality: 30 original tasks, two greedy repetitions, four threads, 2,048-token
  context, and at most eight generated tokens
- Eligibility: stable parsed predictions, at least 75% worst-repetition
  accuracy, and no more than one task behind the best variant
- Performance: three cyclic rounds per variant, each with one warm-up and three
  measured 128-input/64-output iterations

## Application measurements

These values describe the frozen eight-token quality workload. Because all
variants failed quality eligibility, they are diagnostic measurements and not a
deployable speed/size frontier.

| Variant | Package | Load median | Same-text total median | Quality max RSS |
| --- | ---: | ---: | ---: | ---: |
| llama.cpp Q4_0 | 1.066 GB | 701.6 ms | 712.2 ms | 2,133,640 KiB |
| llama.cpp Q4_K_M | 1.117 GB | 777.3 ms | 1,119.7 ms | 2,108,640 KiB |
| MNN int4 | 0.879 GB | 3,518.8 ms | 402.5 ms | 1,076,400 KiB |

Relative to Q4_0, MNN used a 17.51% smaller package, 49.55% less quality-process
peak RSS, and 43.49% less median per-task time after loading, but required 5.02x
the model-load time. Its 13.33% accuracy disqualifies all of those apparent
advantages from a product recommendation.

## Secondary token benchmark

| Variant | Generated per iteration | Encode median | Decode median | TTFT median |
| --- | ---: | ---: | ---: | ---: |
| llama.cpp Q4_0 | 5 | 224.357 tokens/s | 35.248 tokens/s | 597.485 ms |
| llama.cpp Q4_K_M | 64 | 122.439 tokens/s | 33.314 tokens/s | 1,076.506 ms |
| MNN int4 | 64 | 303.469 tokens/s | 54.425 tokens/s | 440.262 ms |

Token rate remains secondary across different tokenizers. Q4_0 also reached EOS
after exactly five tokens in every measured synthetic iteration, while Q4_K_M
and MNN generated all 64. Total iteration latency is therefore not a like-for-
like cross-variant result and is deliberately not promoted.

## Interpretation and limits

The failure is informative rather than a reason to relax the gate. The eight-
token cap ended 27/30 Q4_0 cases, 10/30 Q4_K_M cases, and 29/30 MNN cases at the
limit. MNN commonly began a reasoning preamble despite the instruction to return
one letter, so its parsed score mostly measures incomplete answers. Q4_K_M often
returned an option but still answered enough tasks incorrectly that a longer cap
cannot be assumed to make it eligible.

The run is screening evidence from a hosted Arm runner: PMU counters, energy,
and CPU-governor control remain unavailable. Raw logs and JSON are retained in
the 90-day Actions artifact `e3-qwen-frontier-30635472160-1`; the independently
validated record is
[`../manifests/e3-30635472160.json`](../manifests/e3-30635472160.json).

## Decision

Do not select a runtime from E3 and do not reinterpret the observed failures.
Preserve E3 as a valid empty-frontier result. Any completion-cap or answer-parser
calibration must be predeclared as a separate follow-up experiment and must keep
the original result visible.
