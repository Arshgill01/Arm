# Challenge-period changelog

Pareto64 and this repository were created during the Arm Create: AI
Optimization Challenge 2026 submission period. The full Git history is the
authoritative, timestamped record; this file groups the significant additions.

## 2026-08-01

### Product

- Retained patched llama.cpp `b10216` as a bounded selected-service upgrade
  candidate after exact predictions and every frozen performance/resource gate
  passed against clean `b10208`; automatic promotion remains disabled.
- Added that explicit opt-in adapter without rewriting E3f: it binds the E6f
  manifest, exact patched git diff, CMake source/build cache, server version and
  binary hash, and permits only the measured one-slot repacked f16/256/64
  four-thread profile. The unflagged b10208 path remains unchanged.
- Validated that adapter end to end on native Arm. E6g rebuilt and bound the
  exact source/build/server, launched through Pareto64, and reproduced 23/30
  with zero drift, failures, or missing prefix reuse.
- Froze E6h to test the separately measured no-repack memory tier across the
  historical-to-current runtime boundary, with exact quality/prefix, 3-GiB,
  throughput, latency, CPU-time, readiness, and RSS-retention gates.
- Retained E6h after patched b10216 reproduced 23/30 twice, retained 100.24%
  throughput, used 99.85% of baseline CPU seconds/request, added 180 KiB RSS,
  and kept every no-repack cell below 3 GiB. Product promotion remains disabled
  until a distinct memory-tier launch integration passes.
- Froze E6i as that distinct integration: a second immutable runtime contract
  binds E6h, requires the explicit no-repack adapter path, and keeps 23/30,
  prefix reuse, source/build/binary, readiness, one-slot, metrics, and 3-GiB
  gates separate from E6g's fast service.
- Validated E6i end to end on native Arm. The adapter launched the exact E6h-
  bound no-repack service, reproduced 23/30 with zero drift or failures and
  prefix reuse throughout, and used 2,381,040 KiB maximum RSS.

- Added a fail-closed service-profile planner over the native E5h evidence.
  Explicit throughput and at-most-3-GiB policies select the repacked and
  no-repack tiers respectively; an impossible envelope is refused.
- Retained exact hashed service plans, including the bounded runtime argument,
  and extended clean-checkout verification to recompute both decisions.
- Passed the complete clean-checkout package on native `aarch64`: 128 tests,
  28 pinned hashes, exact model/service plans, E5j/E6d/E6e/E6f/E6g/E6h/E6i
  checks, and demo smoke test.
- Bound the service plan into the verified launcher. The recipe now records the
  measured tier and service input hashes, applies its repack mode, and rejects
  incomplete, infeasible, model-mismatched, or contradictory inputs.

### Submission and developer experience

- Extended the product guide, demo, video script, and submission narrative with
  the measured service-envelope decision and its refusal behavior.
- Expanded the focused product suite to 128 tests and the immutable verifier to
  28 hashes, including separate E6f/E6h upgrade and E6g/E6i launch contracts,
  source diff, and independently replayed results for both current-runtime
  service tiers.

### Arm source contributions

- Rebased the validated-feature correction onto llama.cpp `b10216`; the Q8
  vector-store and reasoning-budget patches applied byte for byte.
- Reproduced both upstream source failures, passed all targeted tests after the
  complete series, and retained 12/12 improved direct Q8 rounds at 1.950–1.958x.
- Independently re-ingested the native E6d result byte for byte and extended
  the submission verifier to 16 immutable hashes.
- Passed a complete upstream-equivalent native Arm CPU build with KleidiAI and
  fatal warnings, then retained all 47 executed tests without a failure, error,
  or skip. Independent E6e ingestion extends the verifier to 17 hashes.
- Ran the exact selected service on clean `b10208` and patched `b10216` in a
  reverse-balanced lane. Current source reproduced 23/30 twice, retained
  1.0028x throughput, and passed all latency, CPU-time, readiness, and RSS gates.

## 2026-07-31

### Product

- Added the quality/SLO-gated Pareto planner with explicit Pareto dominance and
  lexicographic selection—never a hidden weighted score.
- Added a bounded standard-library HTTP planning service and native backlog
  tuner; backlog 64 eliminated all observed admission failures/tail breaches.
- Added a fail-closed inference launcher that recomputes selection, verifies
  exact model/runtime/input hashes, emits a recipe, and starts llama-server.
- Validated exact selected-model serving across 120 native Arm requests with no
  response drift; rejected a marginal two-slot optimization.
- Promoted quality-gated shared-prefix caching after it preserved all 120
  answers, raised throughput 1.672x, and cut median HTTP latency 41.3%.
- Retained cached single-slot serving after a separate interaction test found
  only 1.0619x two-slot throughput with 93.3% higher median latency.
- Promoted a 256-token f16 context profile after it preserved every answer and
  saved 183.36 MiB maximum RSS; rejected q4_0 after reproducible answer drift.
- Added bounded paired prompt-batch controls and froze E5f to compare the
  effective 256/256 default with 128/128 and 64/64 on native Arm.
- Promoted 64/64 after it preserved every answer, cut the CPU compute buffer
  75%, saved 14.48 MiB maximum RSS, and retained 1.0226x throughput.
- Reproduced the promoted unflagged 64/64 path across all six native cells;
  every answer matched again and the independently ingested summary was exact.
- Froze a staged E5g 64/64-versus-32/32 boundary; 16/16 remains out of scope
  unless 32/32 first clears every quality, performance, and memory gate.
- Retained 64/64 after 32/32 halved the remaining compute buffer and preserved
  quality/performance but increased observed maximum RSS by 660 KiB.
- Added a fail-closed weight-repack launcher control and froze E5h to test the
  two-gigabyte Arm repack buffer as a separate memory-tier tradeoff.
- Retained no-repack as an explicit memory tier after it preserved every answer
  and cut maximum RSS by 2,072,268 KiB; repack remains the 2.06x-faster default.
- Added a bounded Flash Attention mode control and froze E5i to test whether the
  resolved Arm auto graph earns a material serving-performance claim.
- Retained E5i as a valid no-win: auto gained 1.0322x throughput and reduced
  median latency/RSS, but worsened p95 6.03% and missed two frozen gates.
- Added a bounded thread control plus measured-window server CPU accounting and
  froze E5j across 4/3/2 inference threads.
- Retained four threads after three/two threads saved only 0.11%/1.36% CPU
  seconds per request while losing 24.48%/48.82% throughput; no energy claim is
  made from CPU time.

### Native evidence

- Established a repeatable four-core Neoverse N2 execution baseline and built
  Arm's Apache-2.0 LLM-Runner end to end.
- Ran quality-gated Qwen, Qwen3.5, and Ministral model/quantization frontiers.
- Retained multiple empty frontiers and a 7B one-task quality near-miss without
  weakening the frozen 75% task floor.
- Selected Apache-2.0 Ministral 3 3B Instruct Q4_K_M at stable 76.67% with a
  2.15 GB package and clean Cloud AI resource SLOs.

### Arm source contributions

- Fixed invalid llama.cpp/KleidiAI native feature selection by using validated
  compiler probes instead of textual flag searches.
- Replaced scalar lane extraction in the Arm Q8_0 activation quantizer with
  NEON narrowing and vector stores, doubling isolated direct throughput with
  bit-identical output and neutral guarded real-model inference.
- Reproduced and corrected a llama.cpp zero-reasoning-budget forced-token state
  transition; retained the separate application-level answer-format rejection.

### Submission and developer experience

- Added immutable experiment contracts, raw-data ingesters, compact manifests,
  reports, CI workflows, source patches, and an expanding product test suite.
- Added a dependency-free interactive evidence demo, browser screenshots,
  paste-ready Devpost draft, video script, claim index, compliance checklist,
  and clean-checkout package verifier.
- Extended the demo and video narrative with the independently validated E5d
  cache/concurrency boundary and a dedicated 1,440×900 gallery screenshot.
- Added the E5e context/KV memory boundary to the demo, evidence index, and
  under-three-minute video narrative.
