# Challenge-period changelog

Pareto64 and this repository were created during the Arm Create: AI
Optimization Challenge 2026 submission period. The full Git history is the
authoritative, timestamped record; this file groups the significant additions.

## 2026-08-01

### Product

- Added a fail-closed service-profile planner over the native E5h evidence.
  Explicit throughput and at-most-3-GiB policies select the repacked and
  no-repack tiers respectively; an impossible envelope is refused.
- Retained exact hashed service plans, including the bounded runtime argument,
  and extended clean-checkout verification to recompute both decisions.
- Passed the complete clean-checkout package on native `aarch64`: 103 tests,
  15 pinned hashes, exact model/service plans, and demo smoke test.
- Bound the service plan into the verified launcher. The recipe now records the
  measured tier and service input hashes, applies its repack mode, and rejects
  incomplete, infeasible, model-mismatched, or contradictory inputs.

### Submission and developer experience

- Extended the product guide, demo, video script, and submission narrative with
  the measured service-envelope decision and its refusal behavior.
- Expanded the focused product suite to 104 tests and the immutable verifier to
  15 hashes.

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
