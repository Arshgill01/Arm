# E3c — Qwen3 4B quantization quality frontier

Status: **valid native comparison; no variant passed the frozen quality gate**.

## Result

[GitHub Actions run 30647831008](https://github.com/Arshgill01/Arm/actions/runs/30647831008)
completed the frozen E3c contract in 20m20s on one four-core Neoverse N2 job.
Independent ingestion with the workflow's Python 3.10 runtime reproduced its
summary byte for byte; the SHA-256 is
`994c5f17d34b83da265ff090219385cfd0faee20e5f22c7a0d12f9fa84484a72`.

All predictions were stable across two repetitions. Q4_K_M was the most
accurate candidate at 20/30 (66.67%), followed by Q5_K_M at 19/30 (63.33%) and
Q8_0 at 18/30 (60.00%). Each missed the predeclared 75% absolute floor, so the
eligible set and Pareto frontier are empty.

| Variant | Worse correct | Accuracy | Stable | Absolute floor | Eligible |
| --- | ---: | ---: | --- | --- | --- |
| Qwen3-4B Q4_K_M | 20/30 | 66.67% | yes | no | no |
| Qwen3-4B Q5_K_M | 19/30 | 63.33% | yes | no | no |
| Qwen3-4B Q8_0 | 18/30 | 60.00% | yes | no | no |

Q4_K_M scored 3/5 arithmetic, 4/5 logic, 3/5 code reasoning, 3/5 data
reasoning, 2/5 systems reasoning, and 5/5 evidence reasoning. No task, answer,
instruction, parser rule, model output, or policy threshold was changed after
observation.

## Protocol

- Official Apache-2.0 Qwen3-4B-Instruct-2507 source and one pinned Apache-2.0
  Unsloth GGUF revision, with source and quantization-producer provenance kept
  separate
- Exact Q4_K_M, Q5_K_M, and Q8_0 package sizes and SHA-256 checksums
- One pinned LLM-Runner/llama.cpp build with KleidiAI enabled and both validated
  Pareto64 source patches applied
- The unchanged 30-task suite: two greedy repetitions, four threads,
  2,048-token context, eight-token cap, and first-standalone-A-D parser
- Three cyclic performance rounds per variant, each retaining one warm-up and
  three measured 128-input/64-output iterations

Runtime logs proved `CPU_REPACK` model buffers for Q4_K_M and Q5_K_M and a
`CPU_KLEIDIAI` model buffer for Q8_0. Quantization was the only candidate-level
difference; that difference selects the applicable backend path in the pinned
runtime.

## Application measurements

These are valid controlled measurements, but no row is a deployment
recommendation because every candidate failed quality eligibility.

| Variant | Package | Load median | Same-text total median | Quality max RSS |
| --- | ---: | ---: | ---: | ---: |
| Q4_K_M | 2.497 GB | 1,734.6 ms | 2,973.4 ms | 5,260,696 KiB |
| Q5_K_M | 2.890 GB | 1,496.0 ms | 3,802.0 ms | 6,024,908 KiB |
| Q8_0 | 4.280 GB | 14,625.9 ms | 1,173.6 ms | 8,502,456 KiB |

Q4_K_M and Q5_K_M met every resource ceiling in the separately frozen
`cloud-quality` policy but failed its accuracy requirement. Q8_0 additionally
exceeded the 10-second load ceiling by 4,625.9 ms and the 8 GiB RSS ceiling by
113,848 KiB. Its package size and same-text latency met their ceilings.

## Secondary token benchmark

| Variant | Encode median | Decode median | TTFT median | Total median |
| --- | ---: | ---: | ---: | ---: |
| Q4_K_M | 44.174 tokens/s | 13.320 tokens/s | 2,972.3 ms | 7,701.4 ms |
| Q5_K_M | 36.647 tokens/s | 9.338 tokens/s | 3,599.6 ms | 10,352.1 ms |
| Q8_0 | 146.252 tokens/s | 16.837 tokens/s | 933.7 ms | 4,676.4 ms |

Q8_0's applicable KleidiAI path delivered 3.31x Q4_K_M prompt throughput,
1.26x decode throughput, and a 1.65x shorter combined benchmark time. This is a
useful Arm runtime result, but it cannot override the quality, load, or memory
gates. Every iteration and process measurement remains in the raw artifact; no
outlier was removed.

## Decision

Do not promote an E3c candidate and do not relax the quality floor. The
fail-closed Pareto64 plan independently returns `no_feasible_candidate` and
records every quality and SLO rejection.

E3c rejects the hypothesis that a quantization-only sweep of this 4B model can
supply the required quality anchor. The separately predeclared E3d calibration
tests a stronger current 4B source model on a pinned current llama.cpp runtime;
it does not reinterpret this result. Hosted-runner limits still preclude energy,
PMU, or controlled-governor claims. Raw evidence remains in the 90-day artifact
`e3c-quality-per-byte-30647831008-1`; compact records are
[`../manifests/e3c-30647831008.json`](../manifests/e3c-30647831008.json) and
[`../plans/e3c-cloud-quality.json`](../plans/e3c-cloud-quality.json).
