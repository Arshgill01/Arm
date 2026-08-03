# Challenge-period changelog

Pareto64 and this repository were created during the Arm Create: AI
Optimization Challenge 2026 submission period. The full Git history is the
authoritative, timestamped record; this file groups the significant additions.

## 2026-08-03

### Native evidence

- Retained E10a's native cache-divergence calibration as a negative result.
  Four semantic drifts reproduced, but cached top-1 margins overlapped stable
  requests, so no margin threshold or independent holdout was selected.
- Added a bounded exact-token probability selector to exact llama.cpp b10216.
  It returns up to 256 requested pre-sampling token scores in request order
  without changing logits or sampled-token semantics.
- Retained E10b's first native attempt after source, build, dependency, model,
  and readiness checks passed but a string-versus-`Path` probe error stopped
  execution before warmup. The repair added a real-input regression test and
  changed no experiment gate.
- Passed E10b on a four-logical-CPU Neoverse N2 runner. Across six pairs, all
  four requested log probabilities matched the existing full-vocabulary path
  within `3.58e-7`, sampled output was identical, median response size fell
  99.9779%, and median HTTP latency fell 18.6%. The result promotes only the
  response primitive for a separately frozen multi-token evaluator.

### Submission and publication

- Extended the immutable submission verifier to 55 hashes and explicit E10a,
  E10b-failure, and E10b claim-boundary checks; the focused suite now contains
  175 tests. Native clean-checkout run `30798816900` passes the full package,
  planner replay, gallery checks, video-word ceiling, and static demo smoke.
- Updated the judge index, Devpost draft, experiment plan, README, and static
  HTML demo with the E10a/E10b evidence and its narrow response-path claim.
- Recorded that `Arshgill01/Arm` is public. Anonymous repository, raw license,
  current workflow, and credential-disabled clone checks pass. Static demo
  hosting and video publication remain separate entrant actions.

## 2026-08-01

### Product

- Retained E9e as a premeasurement stop. Exact b10216's draft initializer
  loads the target path, all 240 frozen E9a completions contain only two
  generated tokens, and LLM-Runner's independent backends cannot consume the
  selected GGUF Q4_K_M identity. License and storage checks passed, but the
  required mechanism, comparability, and workload gates failed, so no
  speculative or cross-runtime benchmark was launched.

- Retained E9d as an honest strict-sanitizer rejection. The exact unpublished
  mail series passed native GCC 14, Clang 18, and both forced feature builds,
  but strict UBSan stopped an upstream quantizer test. A pristine b10216
  control reproduced the same function-type diagnostic; a non-gating scoped
  lane passed remaining ASan/UBSan/leak checks. No PR or readiness claim was
  published.

- Froze E9d as the exact unpublished b10216 three-commit mail series. The
  contract requires byte-identical aggregate application plus native GCC 14,
  Clang 18, forced feature-selection, and targeted ASan+UBSan correctness; it
  explicitly opens no upstream PR and adds no performance claim.

- Retained E9c as a valid negative boundary after all 36 fresh processes and
  576 requests completed on native Arm. Cache mechanics and every performance
  gate passed, but 252 reference mismatches, 204 non-standalone responses, and
  12 paired cache-state mismatches disabled all generalized cache policies.

- Froze E9c as the first ordered fallback after E9b: a bounded native Arm
  prompt-cache generalization matrix on the exact E7c service. Nine
  predeclared prefix-cardinality/shared-token points use 36 reverse-balanced
  fresh processes, exact-output and cache-mechanism checks, and a fail-closed
  threshold/allowlist/disabled policy without untested interpolation.

- Retained E9b's native exact-server API blocker before any external task
  result. Exact E7c and corrected-tokenizer parity passed, but b10216 cannot
  supply lm-eval's required echoed prompt logprobs; the full holdout did not
  start and the original admission contract remains unchanged.

- Retained E9a's same-job native Arm final comparison. The exact E7c service
  preserved all 240 measured answers and reached 1.7168x throughput, 0.5846x
  median latency, 0.7056x p95 latency, and 0.5806x CPU seconds/request versus
  the exact earliest E5b one-slot recipe. The result is explicitly compounded;
  isolated experiments remain the causal evidence.

- Froze E7c as the separate fail-closed integration for E7b's HTTP-only build.
  The launcher now understands E7b's evidence shape, binds the OpenSSL-off cache
  and server binary, rejects either forbidden dynamic dependency, records the
  observed `ldd` inventory in its recipe, and still admits only the exact
  repacked loopback service. E6g/E6i replays remain byte-identical.
- Validated E7c end to end on native Arm. The E7b-bound adapter launched the
  exact OpenSSL-off HTTP service, reproduced 23/30 with zero drift or failures
  and prefix reuse throughout, and matched an independent 13-library `ldd`
  inventory with both forbidden OpenSSL libraries absent. The first attempt's
  missing request-contract shape remains recorded as a rejected run.
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

- Reconciled the judge package with the final `5d3d4f3` native validation:
  163 tests, 49 immutable evidence hashes, planner replay, and demo smoke passed
  in GitHub Actions Arm64 run `30775996806`. The same run validates the four
  1,440×900 gallery images and video-word ceiling; the browser reported no
  warnings during the preceding render audit.
- Corrected the video timing contract after a spoken-word audit found 626 words
  behind the old 2m50s label. The revised 2m45s script has 363 spoken words and
  keeps the quality refusal, service win, Arm patch, and final negative
  boundaries. Submission verification now fails above 390 spoken words.
- Rechecked the controlling rules, track page, organizer guidance, schedule,
  and unpublished gallery on August 3; no technical or submission requirement
  changed.
- Corrected a mandatory publication false-pass after the live GitHub API
  reported `Arshgill01/Arm` as private. The repository and workflow evidence
  require an entrant-controlled visibility change plus anonymous-access checks
  before submission; no publication action was taken.
- Added a publication handoff and a pinned full-history Gitleaks audit. Four
  SHA-256 evidence values were narrowly allowlisted by exact fingerprint; no
  credential finding, sensitive filename, or large-history artifact remains.
- Added a final entrant handoff from a live read-only Devpost gallery audit:
  exact field identity, gallery order, all four survey prompts with
  evidence-backed recommendations, stop gates, and signed-out final checks.
  Corrected the paste-ready Devpost draft's stale 145-test line to the final
  retained 163-test count.
- Corrected the final validation pointer from the earlier E9a–E9e evidence
  checkpoint to the later native judge-package run at `5d3d4f3`, and renamed
  the checkout step so it does not imply the still-private repository is public.

- Extended the focused suite to 145 tests and the immutable verifier to 35
  hashes, including the corrected complete E7c contract and byte-identical
  native launch manifest.
- Passed the updated GitHub Actions clean-checkout package on native `aarch64`: all 145
  tests, 35 hashes, exact E7c dependency/launch assertions, planner/runtime
  checks, and demo smoke test succeeded.
- Extended the focused suite to 141 tests and the immutable verifier to 32
  hashes, including the frozen E7b contract and independently replayed native
  dependency-pruning result. The updated evidence row renders without desktop
  or mobile overflow and produces no browser warnings or errors.
- Passed the updated GitHub Actions clean-checkout package on native `aarch64`: all 141
  tests, 32 hashes, exact E7b dependency/result checks, planner/runtime
  assertions, and demo smoke succeeded.
- Extended the focused suite to 135 tests and the immutable verifier to 30
  hashes, including the frozen E7a compiler/build contract and independently
  replayed native no-win manifest.
- Passed the updated GitHub Actions clean-checkout package on native `aarch64`: all 135
  tests, 30 hashes, exact evidence/plan checks, and demo smoke test succeeded.
- Extended the product guide, demo, video script, and submission narrative with
  the measured service-envelope decision and its refusal behavior.
- Expanded the focused product suite to 128 tests and the immutable verifier to
  28 hashes, including separate E6f/E6h upgrade and E6g/E6i launch contracts,
  source diff, and independently replayed results for both current-runtime
  service tiers.

### Arm source contributions

- Froze E7b as an exact native Arm dependency-pruning ablation for the selected
  loopback HTTP service. It proves OpenSSL support from the CMake cache, full
  build commands, and transitive `ldd` inventory, then accepts OpenSSL-off only
  if it removes both frozen library edges, adds none, preserves exact quality,
  retains at least 98% throughput, and clears every resource guardrail. HTTPS,
  security, installed-package size, energy, and automatic-promotion claims are
  explicitly excluded.
- Retained E7b as a valid dependency-pruning win. OpenSSL-off removed exactly
  `libssl.so.3` and `libcrypto.so.3`, added no dependency, preserved 23/30 twice
  and every guardrail, retained 99.981% throughput, and reduced the eight-file
  build-local closure 1.003%. It remains gated behind a separate HTTP-only
  launch integration.
- Froze E7a as a matched native Arm whole-program optimization ablation for the
  exact selected service. It proves `GGML_LTO` from build commands, hashes and
  retains both transitive build-local runtime closures, and accepts only a
  predeclared throughput or footprint benefit behind shared quality, latency,
  CPU-time, readiness, RSS, and build-cost guardrails.
- Retained E7a as a valid no-win. LTO preserved every answer and common
  guardrail but gained only 0.137% throughput and reduced the transitive local
  runtime closure only 0.775%, so the unchanged build remains selected.
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
