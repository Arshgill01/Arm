# Pareto64

**Tagline:** Quality-constrained Arm64 inference: measure every tradeoff, reject
broken speedups, launch only the proven deployment.

**Track:** Cloud AI

**Source:** <https://github.com/Arshgill01/Arm>

**Interactive demo:** `<ADD PUBLIC DEMO URL>`

**Public video:** `<ADD PUBLIC VIDEO URL>`

## Project overview

The fastest AI configuration is often the wrong one. Quantization, backend
selection, batching, and low-level kernels can all improve a benchmark while
quietly reducing answer quality, breaking a target architecture, or shifting
cost into memory and tail latency.

Pareto64 is an evidence-first deployment planner for CPU inference on Arm64. It
takes native experiment evidence plus an explicit quality/SLO policy, rejects
invalid or quality-ineligible candidates, computes the non-dominated frontier,
and emits a reproducible deployment plan. Once a candidate passes, a fail-closed
launch adapter verifies its exact model hash, source revisions, policy, runtime
contract, and llama.cpp commit before starting the OpenAI-compatible server.

The memorable result is simple: our faster 2.05 GB KleidiAI model lost. It was
29% faster but scored only 70% on the frozen workload. Pareto64 selected the
2.15 GB Q4_K_M package because it reached a stable 76.67% and cleared every
latency, load, memory, and package-size obligation.

## What it does

- runs checksum-pinned AI experiments on native four-core Neoverse N2 hosts;
- preserves raw per-request/per-round data and independently re-ingests it;
- enforces stable quality before comparing latency, RSS, load time, or size;
- builds a Pareto frontier without a hidden weighted score;
- serves the decision through a bounded standard-library HTTP API;
- verifies and launches the exact selected GGUF with pinned llama.cpp settings;
- retains negative results and near-misses instead of rewriting thresholds; and
- packages reports, manifests, source patches, CI workflows, and an interactive
  judge demo in one Apache-2.0 repository.

## Native Arm results

### Quality-per-byte selection

Ministral 3 3B Instruct Q4_K_M scored 23/30 (76.67%) in both quality
repetitions. Its 2,146,497,824-byte package loaded in 2.73 seconds, used
4,696,108 KiB peak RSS, and completed the same-text workload in a 1.80-second
median. It was the only candidate to clear the unchanged 75% quality floor and
all Cloud AI SLOs.

The Q4_0/KleidiAI alternative was smaller (2.05 GB) and faster (1.28-second
median), but stable at 70%. Pareto64 rejected it before resource ranking.

### Exact inference serving

The product launch path served 120 measured OpenAI-compatible requests across
four fresh-server cells. Every response was HTTP 200, an exact standalone answer
letter, normally terminated, and identical to the selected experiment. Every
cell reproduced 23/30 with zero failures or drift. Readiness stayed below 4.1
seconds and maximum RSS below 4.91 million KiB.

A two-slot tuning candidate improved repeated median throughput only 1.019x,
below its predeclared 1.10x gate, and nearly doubled median request latency.
Pareto64 retained one slot rather than marketing a marginal concurrency win.

We then tested shared-prefix prompt caching in a separate frozen A–B–B–A
experiment. Upstream warns that cache-dependent prompt batch sizes can alter
logits, so all 120 responses had to match before speed counted. They did.
Caching reused at least 25 tokens per request, raised repeated median throughput
from 0.538 to 0.899 requests/s (1.672x), and cut pooled median HTTP latency from
1.807 to 1.062 seconds with only about 6.2 MiB additional maximum RSS.

Finally, we retested concurrency after enabling the cache rather than assuming
the two optimizations would compose. Cached two-slot serving preserved all 120
answers and prefix reuse, but improved throughput only 1.0619x while raising
median latency 93.3% and maximum RSS by about 239 MiB. It missed the frozen
1.10x promotion gate, so the product still defaults to one slot.

We then profiled the service's KV memory against the real application envelope.
The workload needed at most 127 prompt tokens plus an eight-token output cap,
yet the server reserved 2,048 tokens. A frozen 2×3 context/K-precision
factorial showed that a 256-token f16 profile reduced the runtime KV allocation
from 208 to 26 MiB and maximum process RSS by 183.36 MiB while preserving every
answer, 99.62% of throughput, and essentially identical latency. q8_0 also
qualified, but the precision-first selector kept f16. q4_0 reproducibly changed
one correct answer in all four cells, so its larger memory and speed gains were
rejected. A clean promoted-default run then repeated the full matrix with the
selected cells using no context/KV overrides; 23/30, throughput retention, and
the memory win all reproduced.

With the context fixed, we profiled the remaining prompt compute-graph
reservation. The effective 256/256 logical/physical batch allocated a 40.13
MiB CPU compute buffer. A frozen forward/reverse 256/128/64 study promoted
64/64 as the launcher default: all 60 measured answers remained exact, the
compute buffer fell to 10.03 MiB, maximum RSS fell 14.48 MiB, and throughput
rose 2.26%. The 128/128
profile was not promoted because its maximum-RSS reduction missed the frozen 8
MiB process gate despite a smaller reported buffer. A clean promoted-default
run repeated all six cells with no Pareto64 batch flags on the 64/64 cells: all
180 answers matched again, throughput retention was 1.0240x, and maximum RSS
fell 17,264 KiB.

We then tested the next boundary without opening an arbitrary sweep. Batch 32
halved the remaining compute buffer to 5.02 MiB, preserved every answer, and
retained 1.0116x throughput, but maximum RSS increased by 660 KiB. It failed
the frozen process-memory gate, so 64/64 remains the default. The staged
contract allowed testing batch 16 only if 32 passed; we stopped instead of
searching past a negative result.

The remaining large allocation was Arm-specific weight repacking. In a frozen
A–B–B–A test, the default exposed a 2,038.92 MiB `CPU_REPACK` buffer and
reached 0.9295 requests/s at 4,453,532 KiB maximum RSS. Disabling repack
preserved all 120 answers and cached-prefix reuse while lowering maximum RSS by
2,072,268 KiB to 2,381,264 KiB. The cost was explicit: throughput fell to
0.4505 requests/s, or 48.47% retention. Pareto64 keeps repack as the fast
default and exposes the qualified no-repack path only as an opt-in memory tier.

We then removed the remaining manual choice. A second fail-closed planner reads
that same native manifest and a deployment envelope. The throughput policy
selects `repack_on`; an at-most-3-GiB policy selects `repack_off` and emits
`--no-weight-repack`; an impossible at-most-2-GiB policy refuses deployment.
As with model selection, every metric, rejection, input hash, Pareto member, and
runtime argument is recorded without a weighted score.

We also ablated the runtime's resolved Flash Attention auto graph rather than
crediting the default without evidence. All 120 answers remained exact. Auto
improved throughput only 1.0322x—below the frozen 1.05x gate—and worsened p95
latency 6.03%, despite better median latency and RSS. We retain the measurement
and bounded mode control, but make no material Flash Attention speed claim.

### Arm-specific source work

We fixed a llama.cpp/KleidiAI feature-selection defect where a substring search
could compile SVE assembly even after the final compiler flags disabled SVE.
The source now uses the build's validated feature probes. A native clean build,
functional model test, runtime-buffer proof, and real inference all passed.

We then optimized the Arm `quantize_row_q8_0` hot path. The baseline extracted
and stored 32 individual byte lanes. The patch narrows values in NEON registers
and emits two 128-bit stores:

- 155 → 98 static instructions;
- 32 → 0 scalar byte stores;
- 0 → 6 vector narrowing instructions;
- 0 → 2 vector stores; and
- 5.09 → 10.33 GB/s, a 2.029x repeated median direct speedup.

The standalone output was bit-identical, upstream quantization tests passed,
and every real-model response remained unchanged. Whole-model inference was
neutral, so we claim the measured quantizer win—not a model-wide speedup.

## How we built it

Pareto64 uses standard-library Python for schemas, evidence ingestion, Pareto
selection, the decision API, and the launch adapter. Native workflows build
immutable Arm LLM-Runner or llama.cpp revisions with KleidiAI, download exact
Apache-2.0 model packages, execute balanced experiments, retain raw results, and
run a second validator that recomputes every statistic and decision.

The selected runtime is llama.cpp `b10208` at commit
`9d9a6d29f6b981cc7f41983d26e56485c6af1811`, built with native Arm and
KleidiAI enabled. The selected model is Apache-2.0 Ministral 3 3B Instruct at a
pinned source revision and pinned GGUF producer revision.

## Challenges

The hardest work was keeping evidence stronger than the story. Several
promising directions failed honestly: a 7B model missed the quality floor by one
task; Qwen quantization sweeps left empty frontiers; a documented zero-reasoning
budget exposed a real sampler state bug; its source fix passed all 13 tests but
the unchanged eight-token application contract still rejected verbose final
answers; and two inference slots failed to create a meaningful throughput win.

We also found and corrected mechanical evidence assumptions—non-UTF-8 diagnostic
bytes, changing upstream commit abbreviations, and INFO-level buffer records—
without changing measured inputs or post-observation thresholds.

## Accomplishments

- first deployable quality/SLO frontier after multiple valid empty frontiers;
- exact model-to-runtime launch with cryptographic fail-closed checks;
- stable end-to-end native Arm inference service with zero response drift;
- quality-gated prompt reuse delivering 1.672x serving throughput and 41% lower
  median HTTP latency;
- a cross-layer cache/concurrency test that rejected a marginal 1.0619x gain;
- context right-sizing that saves 183.36 MiB without KV quantization or drift;
- prompt-batch right-sizing that cuts the compute buffer 75% and saves another
  14.48 MiB maximum RSS without answer drift;
- an explicit no-repack tier that saves 2,072,268 KiB maximum RSS while the
  2.06x-faster repacked layout remains the default;
- a measured service-profile planner that automatically routes throughput and
  at-most-3-GiB envelopes while refusing unmeasured capacity assumptions;
- two reviewable Arm source patches with correctness evidence;
- roughly 2x direct NEON quantizer throughput;
- a reusable no-weighted-score planner, HTTP API, experiment schema, reports,
  and clean-checkout validation workflow; and
- 103 local tests plus native Arm workflows for the final evidence path.

## What we learned

Optimization is a sequence of obligations, not a leaderboard. Quantization can
save time and lose the task. A locally dramatic kernel win can be invisible at
model level. More server slots can divide fixed compute rather than increase
throughput, while removing redundant shared-prefix work can produce a large win
with almost no memory cost. Even then, caching and concurrency did not compose
enough to clear the deployment gate. Workload right-sizing can remove reserved
memory without changing precision, while KV quantization can alter a stable
answer. The reusable contribution is the machinery that makes those limits
visible before deployment.
The same discipline applied to prompt batches: a reported allocation reduction
was insufficient until process RSS, quality, throughput, and latency all
cleared their independent gates.
Weight repacking showed the complementary tradeoff: a two-gigabyte allocation
can be removed safely, but doing so gives up more than half of serving
throughput. A product should expose both qualified operating points and route
explicit deployment envelopes to them instead of pretending one profile
dominates every use case.

## What's next

- rebase the two small llama.cpp patches onto current upstream and run its full
  CI matrix;
- expand the workload beyond the compact deterministic acceptance suite;
- add cost and energy evidence on a host with available counters;
- evaluate the same evidence contract across additional LLM-Runner backends;
  and
- package more planner policies for common Graviton, Cobalt, Axion, and Ampere
  deployment envelopes.

## Significant challenge-period updates

This repository and Pareto64 implementation were created during the challenge
period. The complete commit history records the research dossier, native
baseline, every frozen contract, failed and successful runs, planner/API,
runtime launcher, Arm source patches, interactive demo, and submission package.
