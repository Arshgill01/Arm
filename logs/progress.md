# Progress journal

## 2026-07-31 — kickoff and requirements freeze

- Confirmed the exact event as Arm Create: AI Optimization Challenge 2026.
- Verified the official overview, rules, track detail, schedule, resources, and
  Arm Create pages.
- Created the local repository and configured the requested GitHub origin.
- Selected Apache-2.0, one of the two licenses explicitly accepted by the event.
- Recorded the six named optimization fronts, three published tracks, judging
  weights, mandatory artifacts, and conflicting official language.
- Deferred project selection until hardware/toolchain feasibility and repository
  research are complete.

### Interesting early finding

The highest-scoring strategy is not simply the fastest model. Technical
implementation is 40%, but impact, DX, and WOW total 60%. A reusable optimization
ladder with rigorous proof and a sharply visual demo can score across all four
criteria while still concentrating on one coherent workload and one track.

## 2026-07-31 — environment, ecosystem, and strategy checkpoint

- Audited the current x86_64 host. It is suitable for orchestration, tests,
  AArch64 cross-code generation, and LLVM-MCA modeling, but too noisy and not Arm
  hardware, so it cannot support final performance claims.
- Confirmed free native Linux Arm64 and Apple Silicon runners for the public
  GitHub repository. The organizer separately confirmed Apple Silicon counts for
  Mobile AI.
- Found the official late guidance that running on Arm alone is insufficient;
  the project must expose baseline, technical changes, measured benefit, and
  reusable artifacts.
- Found no challenge-owned starter repository. Arm LLM-Runner is the best
  sponsor-maintained substrate: a common API across four runtimes, explicit
  KleidiAI ablations, Linux/Android support, benchmarks, and Streamline markers.
- Surveyed the public competitor space. Standalone llama.cpp tuners, KleidiAI
  benchmark wrappers, and dashboards are already crowded.
- Identified a workload-aware, quality-constrained, cross-runtime planner as the
  leading single-project hypothesis. It remains gated on native feasibility and
  a source-level or search-method novelty contribution.
- Defined ordered experiments E0–E7 before beginning benchmark work.

### Breakthrough

The development workflow and product can be the same thing: an automated system
that repeatedly profiles, breaks, tunes, validates, and records a real Arm AI
workload. The experiment history becomes both engineering evidence and the live
demo of the reusable optimization tool. The Arm LLM-Runner abstraction makes the
comparison cross-runtime rather than another one-off llama.cpp tuner.

## 2026-07-31 — E0 native Arm probe

- Added a tested, architecture-gated environment/timing probe and manually
  dispatched it to GitHub's `ubuntu-24.04-arm` runner.
- Workflow run `30630496081` passed all steps on commit `6f7cd91`.
- Confirmed a native four-core Neoverse N2 environment with 16 GiB RAM, SVE2,
  I8MM, and BF16.
- The 21-trial compute probe produced a 118.631 ms median, 118.819 ms p95, and
  0.0797% coefficient of variation with identical checksums.
- PMU access remains blocked and no scaling governor is exposed. The environment
  passes feasibility/CI screening, not final energy/mechanism proof.

## 2026-07-31 — E1 LLM-Runner smoke, attempt 1

- Workflow run `30630773335` reached a native Neoverse N2 runner, cloned the
  pinned LLM-Runner revision, and downloaded and checksum-verified the pinned
  1.6 GB Phi-2 Q4_0 model.
- Configuration stopped before compilation because the runner's default Python
  was newer than LLM-Runner's declared supported range (`3.9...3.11`).
- This is an environment-contract failure, not a benchmark or Arm-kernel result.
  The next attempt explicitly selects Python 3.11 and preserves the original
  run as evidence rather than treating it as a performance datapoint.

## 2026-07-31 — E1 LLM-Runner smoke, attempt 2

- Workflow run `30630895263` successfully installed Python 3.11, but upstream's
  native toolchain continued to seed CMake's interpreter discovery with
  `/bin/python`, which is outside LLM-Runner's supported range.
- The next attempt supplies the setup action's `python3` path through the
  documented `Python3_EXECUTABLE` CMake cache variable. No compilation or
  inference datapoint was produced by this attempt.

## 2026-07-31 — E1 LLM-Runner smoke, attempt 3

- Workflow run `30631079879` proved that explicit interpreter binding works.
- It also exposed an upstream version-range edge: CMake interprets the declared
  inclusive maximum `3.11` as lower than the runner's `3.11.15` patch release.
- The next attempt pins Python 3.10, which is unambiguously inside the declared
  range. This remains setup evidence, not a performance result.

## 2026-07-31 — bounded Telegram decision bridge

- Implemented a standard-library-only Telegram receiver with exact chat/user
  authentication, two-or-three-option inline buttons, opaque one-time tokens,
  expiry, update deduplication, and a mode-0600 SQLite audit trail.
- Verified the current Codex app-server contract from version-matched schemas
  and a read-only canary over its WebSocket-framed Unix socket. The canary
  returned the exact current thread with active status and direct input enabled.
- Added fail-closed delivery: decisions wait while a turn is active, target an
  exact thread (never `--last`), and enter manual-reconciliation state if a
  dispatch response is ambiguous.
- Seven local tests pass, including unauthorized, expired, duplicate, active
  thread, and exact registered-option cases.
- Installed and started the hardened user service, then sent a live two-button
  canary. A user reply is intentionally required before bounded replies are
  considered approved for ongoing use.

## 2026-07-31 — E1 LLM-Runner smoke, attempt 4

- Workflow run `30631429898` passed the pinned-model and full CMake configuration
  gates, then compiled 42% of the native Arm build.
- Compilation failed because llama.cpp's `GGML_NATIVE` detection emitted a
  Neoverse N2 feature string containing both SVE2 feature names and a final
  `+nosve`. Its KleidiAI source selection used a substring search, selected SVE
  assembly, then compiled it with SVE disabled.
- The next attempt sets `GGML_NATIVE=OFF` so the explicit LLM-Runner
  `Armv8.6_1` target remains authoritative and selects only the advertised
  DotProd/I8MM KleidiAI kernels. This is also a credible upstream bug/patch
  candidate for the project's source-level optimization story.
- Split cache restore/save now persists the checksum-verified model before
  compilation, even if a later build step fails. The benchmark will also emit
  machine-readable JSON.

## 2026-07-31 — E1 LLM-Runner smoke passed

- Workflow run `30631789118` passed in 5m47s on a four-core Neoverse N2: pinned
  build, upstream Phi-2 functional test, real KleidiAI inference, provenance,
  and artifact upload all completed.
- The three measured iterations produced a 113.578 tokens/s median prompt rate,
  22.165 tokens/s median decode rate, 606.448 ms median TTFT, and 2,007.211 ms
  median total latency. Maximum RSS was 3,243,448 KiB.
- Configure, compiled kernel paths, and the runtime `CPU_KLEIDIAI` buffer provide
  independent backend evidence.
- The run is explicitly not a speedup claim because there is no same-job generic
  baseline. It is also excluded from quality claims because the legacy GGUF
  reports a missing pre-tokenizer and degraded generation quality.
- Added a tested artifact ingester, compact manifest, and reviewable E1 report.
  E1 passes; E2 is now unblocked.

## 2026-07-31 — E2 paired KleidiAI ablation

- Workflow run `30632406883` passed both controlled builds, both upstream
  functional tests, four alternating benchmark rounds, evidence validation, and
  artifact upload on the same native Neoverse N2 job.
- The predeclared primary prompt-throughput criterion did not pass: the median
  paired-round improvement was 1.03%, with improvement in three of four rounds,
  below the required 5% effect.
- Secondary signals were modest but consistent: decode throughput improved
  4.42% in all four rounds, total iteration latency improved 3.48% in all four,
  and whole-process wall time improved 1.91% in three rounds with one tie.
- Maximum RSS was effectively unchanged. One transient KleidiAI prompt outlier
  remains included; no post-result exclusions or threshold changes were made.
- The direct artifact-ingester invocation exposed and received a narrow import
  fix. Twelve local tests pass, including process-time parsing and the E2
  predeclared decision rule.
- E2 supports retaining generic and KleidiAI profiles in a workload-aware
  multi-objective planner, but not a blanket or quality claim. E3 remains gated
  on a modern, license-checked model artifact.

## 2026-07-31 — E3 protocol and harness frozen

- Selected Qwen2.5-1.5B-Instruct because its official GGUF and MNN packages are
  Apache-2.0, small enough for the native runner, and expose two LLM-Runner
  runtime paths without changing the base model family.
- Pinned the GGUF repository at `91cad51170dc346986eccefdc2dd33a9da36ead9`
  and the MNN export at `4ed860971cc9268355e31e26e6034e2d28e3dc7a`,
  including exact sizes and SHA-256 values for all eight package files.
- Authored a 30-task, six-category deterministic quality suite and a tested
  scorer. Eligibility requires two stable greedy repetitions, at least 75%
  accuracy, and a deficit of no more than one task from the best variant.
- Added a backend-neutral C++ quality CLI over LLM-Runner's common API. A local
  x86_64 build successfully compiled and linked the target against the pinned
  llama.cpp dependency; it is integration validation, not Arm evidence.
- Predeclared three cyclic native performance rounds and a Pareto rule over
  eligible accuracy, same-text latency, package size, and RSS. Token throughput
  is secondary across runtimes because their tokenizers differ.
- A local configure attempt exposed LLM-Runner's eager default-model download.
  The E3 workflow disables it and fetches only the explicit, checksum-pinned
  Qwen packages.

## 2026-07-31 — E3 native attempt 1 retained as calibration evidence

- GitHub Actions run `30634585010` fetched and checksum-verified every model
  artifact, then built both optimized llama.cpp and MNN paths with KleidiAI
  enabled on the native Arm runner.
- The run stopped during the first MNN quality repetition because LLM-Runner's
  MNN adapter concatenates package filenames onto the supplied directory. The
  workflow omitted the required trailing path separator, so it attempted to
  open `mnn_int4llm_config.json` and `mnn_int4tokenizer.txt`.
- Before that failure, both llama.cpp variants completed both frozen quality
  repetitions. Q4_0 was stable at 14/30 (46.67%) and Q4_K_M was stable at
  16/30 (53.33%). These partial results are retained rather than discarded.
- The retry changes only the MNN directory argument to end in `/`. The frozen
  tasks, two repetitions, eight-token output cap, 75% eligibility threshold,
  performance protocol, and Pareto rule remain unchanged after observing the
  partial results.

## 2026-07-31 — E3 native comparison completed honestly

- Run `30635472160` completed in 9m30s. Both runtime builds, all six quality
  repetitions, all nine cyclic performance rounds, the frozen scorer, and the
  artifact upload passed.
- The independent ingester accepted the raw artifact without code or data
  changes. Its compact manifest records `valid_no_quality_eligible_variant`.
- Q4_0 scored 14/30 (46.67%), Q4_K_M scored 16/30 (53.33%), and MNN int4 scored
  4/30 (13.33%); every variant repeated the same parsed predictions exactly.
- The response cap was reached by 27/30 Q4_0, 10/30 Q4_K_M, and 29/30 MNN cases.
  MNN usually spent the eight-token budget starting a reasoning preamble.
- MNN's diagnostic measurements were compelling but gated: versus Q4_0 it used
  a 17.51% smaller package, 49.55% less peak quality-process RSS, and 43.49%
  lower median same-text task time after loading, while taking 5.02x as long to
  load. Its failed quality gate prevents a deployment claim.
- No variant enters the Pareto set. E3 remains visible as a valid empty-frontier
  result; a longer completion or parser calibration requires a separately
  predeclared experiment.

## 2026-07-31 — E6a native feature patch frozen

- Recovered the complete E1 attempt-4 artifact. The final native compiler flag
  was `-mcpu=neoverse-n2+crc+sve2-sm4+sve2-aes+sve2-sha3+norng+nossbs+dotprod+i8mm+nosve`.
  llama.cpp's compiled `HAVE_SVE` probe failed as intended, yet a later `+sve`
  substring search selected KleidiAI SVE assembly and broke the build.
- Confirmed the same string-based selection remains in current upstream source;
  no existing issue or commit found by the exact failure terms fixes it.
- Authored a five-line behavioral patch: remove the four string searches and use
  the already-computed `HAVE_DOTPROD`, `HAVE_MATMUL_INT8`, `HAVE_SME`, and
  `HAVE_SVE` results. The patch applies cleanly to the exact pinned llama.cpp
  commit and introduces no new probe or runtime branch.
- Frozen E6a to require the exact unpatched failure, a clean patched rebuild,
  exclusion of the invalid SVE sources, the upstream functional test, and real
  model inference. This is source-correctness evidence; no performance benefit
  will be claimed from a failed-build baseline.

## 2026-07-31 — E6a source-correctness fix validated

- Run `30636911078` passed the entire frozen contract in 6m03s on the native
  Neoverse N2 runner. The unpatched build exited 2 with the exact KleidiAI SVE
  assembly and unsupported-instruction signatures.
- The applied source diff is byte-for-byte identical to the frozen patch. After
  reconfiguration and a clean of all generated objects, the full patched build
  passed and compiled DotProd/I8MM—but no invalid SVE—KleidiAI kernels.
- The pinned upstream Phi-2 test passed 1/1. Real inference loaded a
  `CPU_KLEIDIAI` model buffer and completed every requested output token.
- The independent ingester accepted the artifact as
  `valid_source_correctness_fix`. Patched smoke medians were 113.847 prompt
  tokens/s, 22.748 decode tokens/s, 605.278 ms TTFT, and 1,977.464 ms total.
- No speedup is claimed because the unpatched configuration does not build, and
  no quality claim is allowed for the legacy tokenizer metadata. E6b remains a
  separate paired hot-path optimization requirement.

## 2026-07-31 — Pareto64 fail-closed planner vertical slice

- Implemented the first product code rather than another experiment wrapper.
  The standard-library CLI consumes a validated E3 manifest plus an explicit SLO
  policy, checks evidence consistency, applies quality and SLO gates, recomputes
  the Pareto frontier, and selects lexicographically from visible priorities.
- Weighted scores are structurally absent. Non-finite metrics, unknown policy
  keys, conflicting quality decisions, duplicate priorities, and invalid
  experiment status fail closed.
- Ran the planner on the real E3 evidence with the `cloud-balanced` policy. It
  correctly emitted `no_feasible_candidate`, retained individual rejection
  reasons for Q4_0, Q4_K_M, and MNN int4, and did not let MNN's resource wins
  bypass its 13.33% quality result.
- The generated plan hashes both source inputs and is committed as a product
  artifact. Twenty-four local tests pass, including the actual E3 integration
  and synthetic non-dominated selection cases.

## 2026-07-31 — E5a planner API frozen after local E2E probe

- Added a bounded threaded HTTP service over the same planner function: health,
  default plan, posted-policy evaluation, and process metrics. JSON request
  bodies are capped at 64 KiB; invalid policies and routes return structured
  errors without tracebacks.
- Added an automatic maximum-request shutdown for reproducible `/usr/bin/time`
  evidence and a mixed GET/POST concurrency probe that validates every response.
- The real CLI server passed a local 200-request/concurrency-four probe with zero
  failures, 3.921 ms median, 6.697 ms p95, and 914.0 requests/s. This x86 result
  is integration calibration only.
- Frozen native E5a at 400 measured requests, concurrency eight, zero failures,
  at least 100 requests/s, p95 at most 50 ms, and process RSS at most 256 MiB.
  It explicitly validates the planner decision plane, not model serving.

## 2026-07-31 — E5a native decision-plane load passed with a tail lead

- Run `30638049776` passed in 11 seconds. The independent ingester accepted all
  400 raw responses, both input hashes, service counters, process evidence, and
  the clean bounded shutdown.
- Native throughput was 369.685 requests/s; latency was 3.361 ms median and
  5.153 ms p95; RSS was 23,868 KiB. All responses remained fail-closed with no
  selected runtime, and all frozen gates passed.
- Two POST requests measured 1,006.317 ms and 1,053.691 ms while all other
  requests stayed below 7 ms. Both outliers remain included; E5a had no maximum
  latency gate and will not be reinterpreted after observation.
- The one-second step is consistent with fresh TCP connections overflowing
  `ThreadingHTTPServer`'s default accept backlog of five at concurrency eight.
  This is a mechanism hypothesis, not a conclusion. A separate paired backlog
  experiment can now test it without changing E5a.

## 2026-07-31 — E4a bounded backlog search frozen

- Verified Python's current `ThreadingHTTPServer` default accept backlog is five
  and exposed it as an explicit bounded Pareto64 server setting.
- Frozen candidates 5, 16, and 64 with three cyclic execution orders, 400
  requests per run, concurrency 32, and nine total fresh-process evaluations.
- The primary tail breach is latency above 50 ms. Selection minimizes total
  failures, then breaches, then backlog size, then pooled p95. A win requires
  default breaches in every round, zero selected breaches/failures, a
  p95/throughput/RSS guardrail, and a selected backlog larger than five.
- This experiment is deliberately stricter than E5a and reports full search
  overhead. No tuned backlog has been measured before freezing the contract.
- The first full local harness preflight showed that the stressed default can
  lose a connection, which also leaves request-count shutdown one short. Before
  native dispatch, the scorer was made failure-aware: baseline failures remain
  valid evidence, selection prioritizes zero failures, and only the selected
  candidate must have zero. The runner now interrupts the exact child cleanly
  when failed connections prevent automatic shutdown; performance thresholds
  and candidate values did not change.
- The subsequent complete local integration calibration evaluated all nine
  configurations and independently re-ingested the raw evidence. Backlog 5 had
  12 failures and 77 tail breaches, backlog 16 had zero failures but 43 tail
  breaches, and backlog 64 had neither. This x86 result validates the harness;
  only the frozen native Arm run can validate the experiment hypothesis.

## 2026-07-31 — E4a native backlog tuner passed

- Run `30638730535` completed all nine configurations in 18.088 seconds on the
  four-core Neoverse N2. The workflow summary and a separate local ingestion of
  the downloaded raw artifact were byte-identical.
- Backlog 5 reproduced the problem in every round: 19 total connection resets
  and 76 requests above 50 ms. Backlog 16 removed failures but retained 44
  approximately one-second tail requests.
- Backlog 64 had zero failures and zero tail breaches. Its pooled p95 was 21.862
  ms, maximum latency 24.939 ms, median-round throughput 1,560.048 requests/s,
  and maximum RSS 24,372 KiB.
- Every frozen acceptance criterion passed. Backlog 64 is now the Pareto64
  product default, remains explicitly overrideable, and is supported only as a
  decision-plane admission optimization—not an inference-throughput claim.

## 2026-07-31 — E6b NEON quantizer patch frozen

- Audited the pinned and current upstream llama.cpp Arm quantizer. Both still
  extract 32 integer lanes and issue scalar byte stores in
  `quantize_row_q8_0`; no later upstream commit has replaced the path.
- Added a narrowly scoped patch that preserves the existing NEON conversion,
  narrows the eight integer vectors in registers, and writes two 128-bit
  vectors. It changes no quantization formula, dispatch, dependency, or model.
- GCC 15 AArch64 cross-assembly reduced the function from 124 to 69 static
  instructions and from 36 to 3 stores. A QEMU Arm execution compared 8,224
  deterministic finite inputs, including a zero block, byte for byte and passed.
- Frozen E6b before native measurement: exact and upstream correctness tests,
  assembly obligations, unchanged 30-task Qwen outputs, four alternating direct
  benchmark rounds, and four paired real-inference rounds. The direct hot-path
  threshold is 1.25x at L1 scale and 1.15x at L2 scale, with inference and RSS
  guardrails and no weighted score.
- Native attempt `30640069346` stopped during configuration, before any build or
  benchmark, because LLM-Runner's optional test layer requires downloaded
  fixture models. The harness now disables that unrelated layer while retaining
  the pinned llama.cpp quantizer tests; no experimental input, patch, order, or
  acceptance threshold changed.

## 2026-07-31 — E6b native Q8 hot-path win validated

- Corrected run `30640282768` completed in 8m39s. Both controlled builds,
  standalone equivalence, upstream quantizer tests, emitted-assembly checks,
  frozen Qwen output comparison, all eight performance executions, result
  validation, and artifact upload passed.
- A separate local ingester invocation reproduced the 19,291-byte workflow
  summary exactly; its SHA-256 is
  `ad1adc78703b302cf707353c70642951b4d422b39ddc159f2dc84c97225592bf`.
- The patch improved direct Q8_0 quantizer throughput by a median paired 2.001x
  at 4,096 values and 2.029x at both 65,536 and 655,360 values. Every one of the
  12 paired size/round comparisons improved.
- Native assembly reduced the measured function from 155 to 98 static
  instructions, removed all 32 scalar byte stores, and emitted six vector
  narrowing instructions plus two vector stores.
- The standalone test was bit-identical over 8,224 finite values, upstream
  tests passed in both builds, and all 30 task outputs were unchanged. Real
  Qwen inference was neutral: every paired metric stayed above 0.99x and peak
  RSS was identical at 2,005,348 KiB.
- The result is accepted as an isolated Arm hot-path win, not a whole-model
  speedup, cycles, energy, or quality claim. No threshold or observation was
  changed after measurement.

## 2026-07-31 — E3b quality anchor frozen

- Tested the simplest E3 failure hypothesis locally before designing another
  native run. Raising the 1.5B Q4_K_M output cap from 8 to 64 tokens left it at
  16/30 (53.33%) on the identical tasks, so truncation alone is not the cause of
  the empty frontier. This x86 result is calibration only.
- Downloaded and checksum-verified the official Apache-2.0 Qwen2.5-7B-Instruct
  Q4_K_M split package. A local quality attempt was stopped without a result
  after 20m31s because the host's pre-existing full swap caused 166 GB of block
  reads for roughly four GiB RSS. No partial output or quality inference is
  retained from the stopped run.
- Frozen E3b as a controlled model-scale comparison: official 1.5B and 7B
  Q4_K_M packages, the same llama.cpp runtime and validated Pareto64 patch set,
  and no change to the 30 tasks, instruction, parser, eight-token cap, two
  repetitions, or 75% quality floor from E3.
- Added four alternating native performance rounds and an independent ingester
  that validates artifacts, model hashes and sizes, patch provenance, runtime
  buffer proof, raw quality processes, benchmark parameters, eligibility, and
  the unweighted frontier.
- Generalized the fail-closed planner input boundary narrowly from E3 to E3 or
  E3b schema-1 quality-frontier evidence. No candidate is promoted before the
  native E3b result passes.
- Predeclared a quality-first 16 GiB cloud policy before E3b measurement: 75%
  accuracy, 5-second median same-text latency, 8 GiB RSS, 5 GB package, and
  10-second model-load ceilings, with accuracy first in the visible
  lexicographic priority. No post-result threshold adjustment is permitted.

## 2026-07-31 — E3b native quality anchor retained as a near-miss

- Run `30643977955` completed the full contract in 17m23s. A separate local
  ingestion reproduced the workflow summary byte for byte; SHA-256 is
  `8fd89b9ea82490935e7226dce4d8b20b346828bbb3aead8ab1805572481fb628`.
- The 1.5B candidate repeated its E3 result at a stable 16/30 (53.33%). The 7B
  candidate improved to a stable 22/30 (73.33%) but missed the predeclared 75%
  floor by exactly one task. The eligible set and Pareto frontier remain empty.
- The 7B candidate's same-text median was 5,128.984 ms and quality-process RSS
  was 8,972,028 KiB. These exceed the separately frozen cloud limits by 128.984
  ms and 583,420 KiB; its 4,683,073,632-byte package and 2,732.612 ms load met
  their limits.
- The real planner returned `no_feasible_candidate` and retained the quality,
  accuracy, latency, and RSS rejection reasons. No task, parser, output cap,
  model result, or policy threshold was altered after observation.
- E3b rejects the 7B Q4_K_M quality-anchor hypothesis without invalidating the
  product direction. The next calibration must target a stronger
  quality-per-byte candidate under a new predeclared contract.

## 2026-07-31 — E3c Qwen3 quantization frontier frozen

- Screened current permissively licensed small-model candidates from primary
  model cards. Selected official Apache-2.0 Qwen3-4B-Instruct-2507 because it is
  a 4B non-thinking model whose published benchmark prior targets E3b's weak
  arithmetic, logic, code, and systems categories. Published scores are used
  only to choose the candidate, not as submission evidence.
- Pinned its official source revision separately from the Apache-2.0 Unsloth
  quantization-producer revision. Exact Q4_K_M, Q5_K_M, and Q8_0 packages total
  2,497,281,120, 2,889,514,080, and 4,280,405,600 bytes respectively; every
  SHA-256 is frozen before native measurement.
- Kept all 30 tasks, answers, instruction, greedy decoding, eight-token cap,
  parser, two repetitions, 75% floor, one-task best rule, runtime build, and
  source patches unchanged. Quantization is the only within-E3c candidate
  difference.
- Frozen three cyclic performance rounds and explicit framework-auto chat
  template evidence. The shared ingester now supports E3c while reproducing the
  already accepted E3b manifest byte for byte.
- Reused the existing cloud policy without adjustment and pinned its SHA-256 in
  the E3c contract. The native artifact will contain both the independently
  derivable frontier and a fail-closed Pareto64 deployment plan.

## 2026-07-31 — E3d current Qwen3.5 KleidiAI frontier frozen

- Audited all 30 fixed tasks and confirmed their answer keys; no task or answer
  was changed after the E3b/E3c observations.
- Selected official Apache-2.0 Qwen3.5-4B from primary-source benchmark evidence
  as the next quality-per-byte hypothesis. Pinned source revision
  `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` and the separate Unsloth GGUF
  producer revision `e87f176479d0855a907a41277aca2f8ee7a09523`.
- The sponsor LLM-Runner still pins a 2025 llama.cpp that predates Qwen3.5.
  Pinned current upstream tag `b10208` at commit
  `9d9a6d29f6b981cc7f41983d26e56485c6af1811`; its CMake source pins KleidiAI
  v1.24.0 and its backend source supports Q4_0/Q8_0 quantized weights.
- Frozen only those two KleidiAI-supported quantizations, exact hashes and sizes,
  model-Jinja non-thinking mode, deterministic decoding, real HTTP quality,
  three cyclic upstream benchmark rounds, runtime-buffer proof, and the
  unchanged quality/deployment policies before native measurement.
- Added a fail-closed E3d ingester, current llama.cpp benchmark-shape validation,
  HTTP response/timing capture, planner support, and a complete synthetic
  artifact test. No E3d model output has been measured before this freeze.

## 2026-07-31 — E3c native quality-per-byte result retained

- Green run `30647831008` completed the frozen contract in 20m20s on a
  four-core Neoverse N2 runner. Independent ingestion under the workflow's
  Python 3.10 reproduced the summary byte for byte at SHA-256
  `994c5f17d34b83da265ff090219385cfd0faee20e5f22c7a0d12f9fa84484a72`.
- Q4_K_M, Q5_K_M, and Q8_0 produced stable two-repetition scores of 20/30,
  19/30, and 18/30. All missed the unchanged 75% quality floor; no candidate
  entered the eligible set or Pareto frontier.
- Q4_K_M and Q5_K_M met all resource limits. Q8_0 reached 146.252 prompt and
  16.837 decode tokens/s but required 14,625.9 ms to load and 8,502,456 KiB
  peak quality-process RSS, missing the frozen limits by 4,625.9 ms and 113,848
  KiB.
- The retained planner result is `no_feasible_candidate`. No task, output,
  parser, threshold, execution order, or policy was changed after observation.

## 2026-07-31 — E3e bounded-reasoning frontier frozen

- Used only the completed non-thinking Q4_0 portion of the separately frozen
  E3d artifact as calibration: two identical 20/30 outputs, 1,620.8 ms median
  prompt time, and about 40.4 ms per generated token. No thinking-mode response
  had been requested or observed before selecting E3e budgets.
- Source inspection of pinned llama.cpp tag `b10208` found its explicit
  per-request `reasoning_budget_tokens` path and sampler-enforced end-of-thinking
  sequence. This gives a runtime mechanism for bounding quality-seeking compute
  rather than relying on an instruction that the model may ignore.
- Froze budgets 0, 16, 32, and 48 with exactly eight additional output tokens
  per candidate. The 48-token case projects below five seconds from native
  timing, but it must pass the unchanged measured latency, RSS, package, load,
  stability, and 75% quality gates to enter the frontier.
- Kept the Q4_0 hash, current runtime, KleidiAI revision, tasks, answers,
  instruction, final-answer parser, temperature, seed, threads, context, and
  cloud policy unchanged. Added reverse-balanced repetitions, separated
  reasoning capture, independent ingestion, and fail-closed planner support.

## 2026-07-31 — E3d current-runtime result retained

- Run `30650734222` completed the full native measurement matrix in 15m35s.
  Dedicated verbose probes proved `CPU_KLEIDIAI` model buffers for both exact
  Qwen3.5 packages.
- Q4_0 and Q8_0 were each stable at 20/30 (66.67%). Neither met the unchanged
  75% floor, so the eligible set and frontier remain empty.
- Q8_0 reached 112.774 prompt and 14.961 decode tokens/s versus Q4_0's 59.330
  and 12.620, but its 16,590.0 ms load and 11,368,620 KiB RSS exceeded the
  frozen ceilings. Q4_0 met all resource ceilings and failed only quality.
- Post-processing rejected current llama.cpp's nine-character benchmark commit
  abbreviation because the synthetic fixture expected eight. The raw artifact
  remained complete. The ingester now derives the prefix from the frozen full
  commit, and an independent Python 3.10 run validated the artifact at SHA-256
  `887f202cb150348a0dfd0029b0f1dc2256809c66acc710194b336ef73aba044b`.
- The independent planner returned `no_feasible_candidate`; no task, output,
  parser, order, threshold, or policy was changed after observation.
- Clean reproducibility run `30652188393` subsequently passed the corrected
  workflow end to end from retained-evidence commit `fbe770b`.

## 2026-07-31 — E3e rejected and reasoning-budget bug reproduced

- Run `30651144293` completed the entire reverse-balanced 0/16/32/48-token
  matrix. The frozen ingester correctly rejected it because budget 0 emitted
  reasoning content rather than enforcing the documented immediate end.
- All 60 zero-budget requests consumed exactly eight generated tokens inside
  reasoning and emitted no final answer. Positive budgets produced stable
  diagnostic scores of 13/30, 11/30, and 7/30; none met the quality floor, and
  budget 48 also exceeded the five-second latency ceiling.
- Source tracing found that the forcing state increments for any accepted token.
  Qwen3.5's prefilled newline after `<think>` therefore consumes the one-token
  forced end sequence before generation. The same code remains on current
  upstream `master`.
- An added test against untouched tag `b10208` reproduced the defect with exit
  134 at the exact state assertion. A one-condition token-equality guard made
  all 13 upstream reasoning-budget tests pass locally. Native validation is not
  yet claimed, and the E3e validator was not weakened.

## 2026-07-31 — E6c reasoning-budget correctness fix frozen

- Pinned the exact two-file patch at SHA-256
  `2c0c611f325fd036eadaa0b7dc5615898f1ded3f770b0cf8eacb3a472a613783`.
  The source change only advances `force_pos` when the accepted token equals
  the current forced token; the second hunk is the already-failing regression.
- The native workflow first applies only the test hunk and requires the
  untouched source to fail at the exact assertion. It then applies only the
  source hunk, requires the reconstructed diff and changed-file set to match,
  and runs the complete upstream unit target.
- Real-model validation keeps E3e's exact Qwen3.5 Q4_0 hash, runtime, tasks,
  prompt, deterministic settings, four threads, context, budget 0, and
  eight-token cap. All 60 patched requests must have zero reasoning characters,
  a standalone final answer, normal termination, and stable predictions.
- Accuracy and resource metrics remain diagnostic. Patch correctness does not
  waive the 75% deployment quality floor or create a planner candidate.
- Native attempt `30654443116` reproduced the expected baseline assertion, then
  stopped before the patched build because the runner rendered diff object IDs
  with nine characters while the frozen patch used seven. The workflow now
  pins `git diff --abbrev=7`; source hunks, patch hash, and all gates are
  unchanged.

## 2026-07-31 — E6c source fix validated; application gate rejected

- Run `30654805236` reproduced the untouched-source regression with exit 134,
  applied the frozen patch byte for byte, and passed all 13 upstream
  reasoning-budget tests on native Arm.
- The exact Qwen3.5 Q4_0 model used a `CPU_KLEIDIAI` buffer. All 60 real HTTP
  requests emitted zero reasoning characters, so the patch corrected the
  pre-generation forcing-state transition exposed by E3e.
- Only 5/30 responses per repetition were standalone A-D answers ending by
  `stop`. The other 25 entered final-channel explanatory text and reached the
  unchanged eight-token cap. Both repetitions were text-identical.
- The frozen validator correctly rejected the run. No E6c manifest or planner
  candidate is accepted, and the 75% deployment floor remains unchanged. The
  source-level correction evidence and application failure are retained
  separately rather than weakening the post-observation gate.

## 2026-07-31 — E3f Ministral quality-per-byte frontier frozen

- Selected official Apache-2.0 Ministral 3 3B Instruct from immutable primary
  evidence: the card reports 0.830 MATH Maj@1, strong system-prompt behavior,
  edge deployment intent, and production temperature below 0.1. Published
  aggregate scores are a selection prior only.
- Pinned the official source revision and a single Apache-2.0 GGUF producer
  revision. Exact Q4_0 and Q4_K_M packages are 2,046,375,200 and 2,146,497,824
  bytes with immutable SHA-256 values.
- Froze the existing 30 tasks, answers, semantic instruction, eight-token cap,
  parser, deterministic decoding, quality thresholds, current runtime, cyclic
  token benchmark, and deployment policy. Only quantization differs between
  candidates.
- Mapped the unchanged instruction to the model's system role before observing
  any Ministral output. This uses the model's documented prompt interface and
  suppresses its unrelated large default preamble; tasks remain user messages.
  Q4_0 additionally requires direct KleidiAI runtime-buffer proof.

## 2026-07-31 — E3f selects the first deployable candidate

- Run `30656151957` completed every native cell. Q4_0 was stable at 21/30
  (70.00%); Q4_K_M was stable at 23/30 (76.67%) and crossed the unchanged 75%
  floor by one task.
- Q4_K_M also passed all frozen resource SLOs: 2,146,497,824-byte package,
  2,731.7 ms load, 1,798.7 ms median model time, and 4,696,108 KiB peak quality
  process RSS. The planner selected it as the only feasible frontier member.
- Q4_0 proved a real `CPU_KLEIDIAI` model buffer and was materially faster, but
  its quality miss kept it out of the frontier. The result demonstrates the
  quality-first planner behavior rather than simply choosing the fastest path.
- Native post-processing encountered a non-UTF-8 metadata byte after all
  measurements. Replacement decoding for diagnostic logs fixed the mechanical
  assumption without changing any experiment input or gate. Independent Python
  3.10 ingestion retained manifest SHA-256
  `54adb3d4317e7a33c08c3bc59a4d534c5b5c6952a1dcc9a01b93e87a445aff9c`.
- Clean run `30657209779` subsequently passed the corrected workflow end to end
  in 11m44s, reproduced both stable scores and the selected candidate, and
  independently matched its uploaded summary byte for byte at SHA-256
  `268cc0ec71e3396758c49b1405025ef6b13a0652029d15d5b027ddd046fa6932`.

## 2026-07-31 — E5b selected inference serving frozen

- Added a fail-closed `pareto64 launch` adapter. It recomputes the selected
  frontier, binds the model catalog and runtime contract to E3f provenance,
  verifies the exact 2.15 GB package hash and pinned llama.cpp version, and
  emits a hashed recipe before executing the server.
- Froze a native Arm four-cell inference matrix with fresh servers and balanced
  baseline/two-slot order. The semantic prompt, tasks, seed, output cap,
  threads, and per-slot context remain identical to E3f.
- Every response must exactly reproduce E3f's stable selected prediction and
  23/30 quality before the two-slot configuration can claim at least 1.10x
  median throughput. Latency, readiness, RSS, runtime buffers, metrics, slots,
  and raw responses are independently revalidated.

## 2026-07-31 — E5b validates serving but rejects two-slot tuning

- First run `30659025892` completed all four measured cells but exposed an
  evidence-collection assumption: default server logs suppress the contracted
  INFO-level model-buffer records. The measured result was not reinterpreted.
- Added E3f's existing unmeasured verbose runtime proof and separated experiment
  validity from hypothesis success. The E5b contract, balanced order, measured
  commands, quality gates, and 1.10x throughput threshold stayed unchanged.
- Clean run `30659829983` passed end to end. All 120 requests were exact stable
  letters matching E3f, and every cell reproduced 23/30 with zero failures.
- Two slots improved repeated median throughput only 1.0189x, from 0.5371 to
  0.5472 requests/s, while pooled median latency rose from 1.81 to 3.57 seconds.
  Latency, readiness, and RSS ceilings passed, but the throughput gate did not.
- Exact selected-model inference serving is validated. The two-slot optimization
  claim is rejected and Pareto64 retains one slot by default. Independent
  ingestion matched the uploaded summary at SHA-256
  `aa529b16094ab398bf1d7c6aa698b452eeea6217f8016c280a5f2b6f947bf66c`.

## 2026-07-31 — E5c shared-prefix prompt cache frozen

- Audited the selected serving path and found that Pareto64 explicitly disables
  llama.cpp prompt caching, even though all requests share the same system and
  chat-template prefix.
- The pinned runtime documents common-prefix KV reuse as a performance feature,
  but warns that prompt batching can change logits; its cache-equivalence test
  is skipped on Linux. This makes the hypothesis performance-positive but
  correctness-sensitive.
- Froze a four-cell no-cache/cache/cache/no-cache experiment with one slot and
  client throughout. Both the hashed server recipe and request payload bind the
  cache mode, and raw timing evidence must prove zero reuse in the baseline and
  real prefix reuse in every candidate request.
- Promotion requires all 120 responses to reproduce E3f's stable 23/30 result,
  at least 1.10x repeated median throughput, at least 1.10x prompt-encode
  improvement, and the unchanged latency, readiness, and RSS ceilings.

## 2026-07-31 — E5c shared-prefix cache wins

- Native run `30662037235` passed the full workflow in 9m41s. All 120 measured
  responses matched E3f, and each fresh-server cell reproduced 23/30 with zero
  failures or drift.
- Cache-disabled cells reused zero prompt tokens. Every cache-enabled request
  reused at least 25; the candidate median was 25 and maximum was 92.
- Repeated median throughput improved from 0.5378 to 0.8991 requests/s
  (1.6718x). Repeated median prompt encode improved from 1,738.0 to 989.0 ms
  (1.7574x).
- Pooled median/p95 HTTP latency fell from 1,807.0/2,644.6 ms to
  1,061.6/2,060.5 ms. Maximum RSS increased by only 6,308 KiB, and readiness
  remained below four seconds.
- Both predeclared 1.10x performance gates and every quality/resource gate
  passed. Independent local ingestion matched the uploaded summary byte for
  byte at SHA-256
  `27a426dd9ed0ed8e4b9ef513a5ced7418f7a722b91e94ca1bc10f8f76d84bfa7`.

## 2026-07-31 — E5c promoted default reproduces cleanly

- Enabled prompt caching by default in the fail-closed launcher, retained an
  explicit `--no-prompt-cache` escape hatch, and bound the mode into the hashed
  recipe. The historical E5b baseline remains explicitly cache-disabled.
- Native run `30663285866` exercised cache-on without an enable override from
  promoted commit `c68cb7e`. Every one of 120 responses again matched E3f and
  every cell reproduced 23/30 with zero request failures or drift.
- Repeated median throughput improved from 0.5382 to 0.9047 requests/s
  (1.6809x), and repeated median prompt encode improved from 1,734.4 to
  982.7 ms (1.7650x). Candidate median/p95 HTTP latency was
  1,053.1/2,048.2 ms.
- Every candidate request reused at least 25 tokens. Independent Python 3.10
  ingestion matched the uploaded summary byte for byte at SHA-256
  `036a65d276a3e49b9ca4cfa3f8e8817d55a00e9a2ba66d5b25cfefc46ac31747`.
- Clean-checkout submission run `30663277762` passed all 72 tests, retained
  evidence verification, plan checks, and the demo smoke test on native Arm.

## 2026-07-31 — E5d cached-concurrency interaction frozen

- E5b's two-slot rejection was measured without the later E5c prompt-cache win.
  Since caching changes the prompt/decode balance, froze a separate interaction
  experiment instead of assuming that either earlier result transfers.
- The only measured change is cached one-slot/one-client versus cached
  two-slot/two-client serving. Both use the exact promoted model/runtime path,
  four threads, 2,048 tokens per slot, identical requests, and normal automatic
  slot scheduling during measurement.
- Each two-slot server preloads the common prefix into slot 0 and slot 1 with
  two unmeasured, explicitly routed warmups. The one-slot baseline receives the
  same warmup tasks, both on slot 0. This isolates steady-state concurrency
  without assigning measured requests to slots manually.
- Promotion requires all 120 answers and 23/30 quality to remain exact, cached
  reuse on every measured request, at least 1.10x repeated median throughput,
  5/10-second median/p95 latency ceilings, at most 512 MiB incremental RSS,
  and the existing readiness and 8 GiB absolute RSS ceilings.

## 2026-07-31 — E5d rejects cached two-slot serving

- Native run `30664666945` passed the frozen workflow in 7m51s. Both dual slots
  were preloaded before measurement, measured requests were automatically
  scheduled, and every measured request reused at least 25 prompt tokens.
- All 120 responses matched E3f exactly. Every cell reproduced 23/30 with zero
  request failures or drift, and every validity and resource gate passed.
- Repeated median throughput improved from 0.9056 to 0.9617 requests/s, only
  1.0619x and below the frozen 1.10x promotion threshold.
- Pooled median HTTP latency rose from 1,052.7 to 2,034.4 ms, and maximum RSS
  increased 244,524 KiB (about 239 MiB). Both remained inside their absolute
  ceilings, but do not justify the marginal throughput gain.
- Independent Python 3.10 ingestion matched the uploaded summary byte for byte
  at SHA-256
  `a844e58ea3f89e8fd9d9e8697ad6c680865a6719d2f6b34298af0d56be7d76e5`.
  Cached two-slot promotion is rejected; cached single-slot serving remains the
  verified default.
- Retained-evidence clean-checkout run `30665354849` passed all 75 tests, all
  six pinned evidence hashes, exact-plan checks, and the demo smoke test on
  native `aarch64`.

## 2026-07-31 — Judge demo exposes the cross-layer boundary

- Added the E5d cached single-slot versus two-slot comparison directly below
  the promoted E5c cache result, using the retained 0.9056/0.9617 requests/s,
  1,052.7/2,034.4 ms latency, and maximum-RSS evidence.
- Added E5d to the chronological decision ledger and updated the video script
  to explain why cache promotion does not imply concurrency promotion.
- Browser-tested the demo at 1,440×900 and 390×844. The interactive latency
  temptation still produces `No feasible candidate`, the mobile document has
  no global horizontal overflow, the evidence table scrolls within its own
  boundary, and the console reports zero warnings or errors.
- Captured the first-party 1,440×900 serving-boundary gallery image at
  `output/playwright/pareto64-serving-boundary.png` and added it to the compact
  package verifier.
- Clean-checkout native Arm run `30665760895` passed all 75 tests, six pinned
  evidence hashes, package verification, and the strengthened demo smoke test.

## 2026-07-31 — E5e context and KV-cache profile frozen

- E5d measured at most 127 prompt tokens with an eight-token output cap, while
  the promoted single-slot launcher still reserves 2,048 tokens of context.
  The frozen 256-token factor retains 1.896x headroom over the measured
  135-token bound.
- Audited pinned llama.cpp `b10208`: quantized V cache requires flash attention,
  while the selected model's 128-wide K heads satisfy q8_0/q4_0 block sizing.
  E5e therefore varies only K precision and holds V at f16 to avoid a hidden
  required attention-kernel change; the existing `auto` mode is explicit in
  every launch recipe.
- Froze a 2×3 context/K-precision factorial with two repetitions and exact
  forward/reverse order. Separate INFO-level launches must prove all six KV
  allocation sizes without adding logging overhead to measured cells.
- Added bounded, fail-closed launcher overrides for context and K/V types. The
  validator treats answer drift as profile ineligibility rather than discarding
  valid evidence from the remaining factorial.
- Promotion requires exact selected quality, at least 128 MiB lower conservative
  maximum RSS, at least 95% throughput retention, no more than 1.10x median or
  p95 latency, and the existing readiness/RSS ceilings. Lexicographic selection
  preserves K precision before taking additional memory savings.

## 2026-07-31 — E5e selects context right-sizing without quantization

- Native run `30667019678` passed the full 12-cell workflow in 13m33s. All six
  mechanism launches proved the expected precision- and context-monotonic KV
  allocations; independent Python 3.10 ingestion matched the uploaded summary
  at SHA-256
  `6312dc789eefad276b20d3204d9a5144251d49e3f04b9a767d9125dceaa5ed2c`.
- The selected 256-token f16 profile reduced the runtime KV allocation from
  208 to 26 MiB and maximum process RSS by 187,760 KiB (183.36 MiB, 4.03%). It
  retained 99.62% throughput, slightly reduced pooled median/p95 latency, and
  reproduced 23/30 with zero answer drift in both repetitions.
- The 256-token q8_0 profile also passed every gate and saved 247,636 KiB, but
  the frozen selector preserved f16 because f16 already exceeded the 128 MiB
  target. The product therefore avoids unnecessary numerical compression.
- q4_0 was faster and saved more memory, but every q4_0 cell reproducibly
  changed `systems-04` from B to C and reduced quality to 22/30. Those valid
  negative measurements are retained and excluded from promotion.
- Added the memory profile and q4_0 quality boundary to the judge demo and
  under-three-minute script. Real-browser checks at 1,440×900 and 390×844 found
  zero console errors/warnings and no global mobile overflow; both evidence
  tables remain locally scrollable at 348/760 pixels.
- Replaced the serving-boundary gallery image with a first-party 1,440×900
  capture that shows context right-sizing beside the retained concurrency
  rejection.

## 2026-07-31 — E5e promoted default reproduces cleanly

- Promoted the 256-token context in both the CLI and runtime API while retaining
  f16 K/V cache, explicit `auto` flash attention, shared-prefix caching, and one
  slot. Historical E5b–E5d workflows now bind 2,048 tokens explicitly, so their
  frozen commands remain reproducible.
- Native run `30668306694` omitted all context/KV overrides for the two selected
  E5e cells. Artifact provenance bound the launcher default to
  `ctx256_k_f16`, and the independent validator accepted the full matrix.
- The selected profile again reproduced 23/30 twice with zero drift, retained
  1.0001x repeated median throughput, and reduced maximum RSS by 187,468 KiB.
  q4_0 again produced 22/30 and remained ineligible.
- Independent Python 3.10 ingestion matched the uploaded summary byte for byte
  at SHA-256
  `51f1e704259d300a460fb8f386f893dd2c86cd3d2e62c54071d48b099a96e8ac`.

## 2026-07-31 — E5f prompt batch profile frozen

- Audited pinned llama.cpp `b10208`: upstream logical/physical prompt-batch
  defaults are 2,048/512, causal attention clamps them to the 256-token
  context, and compute-graph reservation uses the effective microbatch. The
  retained E5e mechanism log confirms an effective 256/256 baseline and a
  40.13 MiB CPU compute buffer.
- Froze 256/256, 128/128, and 64/64 profiles in forward then reverse order with
  two repetitions each. The 128 profile covers the retained 127-token maximum
  prompt in one batch; 64 intentionally tests split-prompt behavior.
- Added bounded paired launcher overrides and recipe fields for requested and
  effective batch sizes. The baseline must omit both flags, while candidate
  recipes must bind both explicitly.
- Promotion requires exact selected predictions and prefix reuse, at least 8
  MiB lower compute buffer and conservative maximum RSS, at least 98%
  throughput retention, median/p95 latency within 1.05x, and the existing
  readiness/RSS ceilings. The selector uses no weighted score.

## 2026-07-31 — E5f selects the 64-token prompt batch

- Native run `30669700602` passed the six-cell matrix and three mechanism
  launches in 9m27s. Independent Python 3.10 ingestion matched the uploaded
  summary byte for byte at SHA-256
  `396222dd2ec0d66c0985392b0c2b65e4fa1b8a3100f57c4d1d30d50a41f92d4b`.
- Every profile reproduced 23/30 in both repetitions with zero selected-answer
  mismatches and at least 25 cached prompt tokens per measured request.
- The 64/64 profile reduced the CPU compute buffer from 40.13 to 10.03 MiB and
  conservative maximum RSS by 14,824 KiB. It retained 1.0226x throughput;
  median latency was 1.0044x and p95 was 0.9095x baseline.
- The 128/128 profile saved 20.06 MiB of reported compute-buffer allocation but
  only 1,076 KiB maximum RSS, so it missed the predeclared 8 MiB process gate.
  Only 64/64 is eligible for product promotion.
- Added E5f to the judge demo, evidence ledger, Devpost draft, and video script.
  Real-browser checks at 1,440×900 and 390×844 retained the fail-closed policy
  interaction, reported zero console errors/warnings, and kept document width
  at 390 pixels while all three 760-pixel evidence tables scroll locally.

## 2026-07-31 — E5f 64/64 promotion prepared

- Changed the runtime API and unflagged CLI launch path to the selected 64/64
  prompt batch while keeping paired overrides bounded and fail-closed.
- Pinned the historical effective 2,048/512 and 256/256 batches explicitly in
  E5b–E5e workflows, so those frozen commands do not inherit the new default.
- Updated E5f reproduction binding at both layers: selected cells omit Pareto64
  batch flags, while the generated llama.cpp recipe must contain explicit
  64/64 flags because upstream defaults remain 2,048/512.
- The promotion-aware ingester parses the timed outer command and validates the
  generated recipe separately. Re-ingesting the original artifact still
  reproduced retained SHA-256 `396222dd…f92d4b` byte for byte.

## 2026-07-31 — E5f promoted default reproduces cleanly

- Promotion commit `1c7cb63` passed clean-checkout validation on native Arm in
  run `30670951208`: 87 tests, eight retained evidence hashes, exact plan, and
  the dependency-free demo smoke test all passed.
- Native run `30670972497` repeated the six-cell forward/reverse matrix in
  9m02s. The two `batch64` cells exercised the unflagged Pareto64 default while
  every generated llama.cpp recipe still pinned its effective batch pair.
- All 180 measured requests returned normally and matched the selected E3f
  prediction. `batch64` was again the only eligible profile: 1.0240x throughput
  retention, 1.0060x median and 0.9088x p95 latency ratios, and 17,264 KiB less
  maximum RSS than the 256/256 baseline.
- Independent Python 3.10 ingestion matched the uploaded summary byte for byte
  at SHA-256
  `4b0e4632306829c4d3fa0ce5b01351bf4e2f9dec6cdc4e4f48f8e40a0542135a`.

## 2026-07-31 — E5g marginal batch floor frozen

- The retained request traces show the remaining tradeoff directly. Across 30
  measured requests, batch 64 needs 34 evaluated-prompt chunks and splits 4
  requests; batch 32 would need 63 chunks and split 28. Batch 16 would need 113
  chunks and split 29.
- Froze a staged 64/64-versus-32/32 A–B–B–A study. Batch 16 is not measured
  unless 32 first passes, avoiding a post-result sweep for a favorable cutoff.
- The 32/32 candidate must preserve every selected prediction and prefix reuse,
  retain at least 98% throughput, keep median and p95 latency within 1.05x, and
  reduce both the 10.03 MiB baseline compute buffer and maximum process RSS by
  at least 4 MiB.
- The promoted batch64 cells omit the outer Pareto64 flags but must retain
  explicit 64/64 values in the generated llama.cpp recipe. E5g reuses the
  promotion-aware ingester and adds no new runtime knob.

## 2026-07-31 — E5g closes the marginal batch floor

- Native run `30671733556` passed both mechanism proofs and the four-cell
  A–B–B–A matrix in 7m40s. All 120 measured requests returned normally, reused
  at least 25 prompt tokens, and matched the selected prediction.
- Batch 32 reduced the CPU compute buffer from 10.03 to 5.02 MiB, retained
  1.0116x throughput, and kept median/p95 latency at 1.0095x/0.9061x baseline.
- Conservative maximum RSS increased by 660 KiB, missing the frozen requirement
  to save 4,096 KiB. The result is a valid no-win; 64/64 remains the default.
- Per the staged contract, batch 16 is not tested after the 32 profile fails.
  Independent Python 3.10 ingestion matched the uploaded summary byte for byte
  at SHA-256
  `374e5af3d8af8c022d76ff51f614c50e1dd25f8948fcc727fe3f983afad984b6`.
- Retained-evidence run `30672258413` passed clean-checkout validation on native
  Arm: 89 tests, all nine evidence hashes, ten demo links/assets, exact plan,
  and the dependency-free demo smoke test.

## 2026-07-31 — E5h Arm weight-repack boundary frozen

- Audited pinned llama.cpp's `--no-repack` path. The flag sets
  `no_extra_bufts`; model loading then skips the KleidiAI and generic CPU extra
  buffer types offered ahead of the ordinary CPU buffer.
- The retained selected-service log reports a 2,024.36 MiB `CPU_Mapped` buffer
  and a distinct 2,038.92 MiB `CPU_REPACK` buffer, making this a materially
  different memory mechanism rather than another small allocator fluctuation.
- Added a bounded launcher boolean that defaults on, records the choice in the
  recipe, and maps the disabled path to upstream `--no-repack`. Historical
  recipes remain repack enabled.
- Froze a four-cell A–B–B–A study. A no-repack candidate becomes a separate
  memory tier only if it is exact, saves at least 1.5 GiB maximum RSS, stays at
  or below 3 GiB RSS, retains at least 30% throughput, and meets 5/10-second
  median/p95 plus 15-second readiness ceilings. It never replaces the faster
  default through a weighted score.

## 2026-07-31 — E5h selects an explicit low-memory tier

- Native run `30672633366` passed the source proof, two mechanism launches,
  and four-cell A–B–B–A matrix in 8m57s. All 120 measured requests returned
  normally, reused at least 25 tokens, and matched the selected prediction.
- Repack on exposed 2,024.36 MiB mapped plus 2,038.92 MiB `CPU_REPACK` model
  buffers. Repack off exposed only a 2,039.54 MiB mapped buffer.
- No-repack reduced maximum RSS from 4,453,532 to 2,381,264 KiB, a 2,072,268
  KiB saving, and stayed below the 3 GiB tier ceiling. It retained 0.4847x
  throughput with 2.416/3.304-second median/p95 HTTP latency.
- Pareto64 retains no-repack only as an opt-in memory tier. Repacking remains
  the faster default. Independent Python 3.10 ingestion matched the uploaded
  summary byte for byte at SHA-256
  `e048f3e25d513430b49fd2ee0a140e8a0f82fe31d79b5fb0aafb36b470190faa`.
- Retained-product run `30673396572` passed clean-checkout validation on native
  Arm: 93 tests, all ten immutable evidence hashes, exact plan recomputation,
  and the standalone demo smoke test.

## 2026-07-31 — E5i Arm Flash Attention ablation frozen

- Audited pinned llama.cpp `b10208`: `--flash-attn off` maps to the disabled
  context path, while auto begins with the fused operation enabled and retains
  it only after `resolve_fused_ops` successfully probes backend allocation and
  computation.
- The retained selected-service mechanism log proves auto resolves on this Arm
  build: it records `flash_attn = auto` followed by `Flash Attention enabled`.
- Added a bounded `--flash-attention auto|on|off` launcher control. Auto remains
  the default and every generated recipe records the exact upstream mode.
- Froze an off–auto–auto–off study. Auto must preserve every selected prediction
  and cached prefix, improve throughput by at least 1.05x, avoid median/p95
  latency regression, and add no more than 16 MiB maximum RSS. Separate
  verbosity-four launches must prove the disabled and resolved-enabled graphs.

## 2026-07-31 — E5i retains Flash Attention as a valid no-win

- Native run `30674023380` passed both mechanism proofs and the four-cell matrix
  in 7m12s. All 120 measured requests returned normally, reused at least 25
  prompt tokens, and matched the selected prediction.
- Auto resolved Flash Attention and improved throughput from 0.9013 to 0.9303
  requests/s, a 1.0322x gain below the frozen 1.05x minimum. Median HTTP latency
  improved 6.18%, while p95 worsened 6.03% and failed its non-regression gate.
- Auto reduced maximum RSS by 7,384 KiB despite its reported compute buffer
  being 10.03 versus 9.56 MiB. No material serving win is promoted.
- Independent Python 3.10 ingestion matched the uploaded summary byte for byte
  at SHA-256
  `ca41dd4c8ce7eaec196ac4d6a1320f689755ae4fb9e5d13bb4061f3c24a46ba2`.
- Retained-result run `30674552684` passed clean-checkout validation on native
  Arm: 97 tests, all eleven immutable evidence hashes, exact plan recomputation,
  and the standalone demo smoke test.

## 2026-08-01 — E5h service tiers become executable decisions

- Added a separate fail-closed service-profile planning stage over the selected
  E5h evidence. It verifies the experiment permission, zero-failure and
  mechanism proofs, exact tier names, answer eligibility, and repack-buffer
  consistency before considering a deployment.
- Added explicit throughput and at-most-3-GiB policies. The retained plans
  select `repack_on` and `repack_off` respectively; the latter emits
  `--no-weight-repack`. A tested at-most-2-GiB policy returns
  `no_feasible_profile`.
- Local focused tests, scoped Ruff, JSON validation, exact retained-plan
  recomputation, and the submission verifier pass. The verifier now pins 15
  evidence/configuration/plan hashes.
- Public clean-checkout run `30674971776` passed on native `aarch64` from exact
  product commit `d274a6b`: 103 tests, all 15 hashes, exact retained model and
  service plans, and the dependency-free demo smoke test.

## 2026-08-01 — Measured service decisions reach the launch recipe

- Extended the existing verified launch adapter instead of creating a parallel
  entrypoint. Optional service evidence and policy inputs are independently
  recomputed and must select the same model as the quality frontier.
- The selected tier now controls the upstream repack argument automatically;
  the recipe records both new hashes, service frontier, metrics, and profile.
  Incomplete inputs, an empty frontier, and a contradictory manual repack flag
  fail before launch.
- Focused launcher, CLI, and service-planner tests pass for both throughput and
  at-most-3-GiB routing, exact `--no-repack` emission, hash binding, manual
  conflict, incomplete input, and impossible-policy refusal.
- Public clean-checkout run `30675220682` passed on native `aarch64` from exact
  launch-binding commit `f2c367e`: 104 tests, all 15 pinned hashes, exact plan
  checks, and the dependency-free demo smoke test.

## 2026-08-01 — E6d current-upstream patch revalidation frozen

- Audited current llama.cpp tag `b10216` at commit
  `876a4321163249c43ca4e986818fab5ab081f282`. The Q8 vector-store and
  reasoning-budget patches apply unchanged. The KleidiAI flag-substring bug
  remains; its patch needed only surrounding SME source-list context refreshed.
- Froze a no-model native revalidation so the scope stays precise: current
  source applicability, the exact validated-feature build failure/correction,
  baseline-fail/patched-pass reasoning tests, upstream quantizer correctness,
  emitted assembly, and four balanced direct-performance rounds.
- Added an independent E6d ingester and local gate tests. No current-upstream or
  upstream-ready claim is accepted until the frozen native workflow passes.
- Native attempt `30675615101` stopped before any build or measurement. Cloning
  a second worktree from the first partial clone tried to lazy-fetch an absent
  object from its promisor remote and exited 128. The workflow now copies the
  already verified clean pinned tree; no experiment input, order, or gate
  changed.

## 2026-08-01 — E6d current-upstream series passes

- Native run `30675654688` passed the complete frozen E6d contract in 6m59s on
  a four-core Neoverse N2. The feature baseline reproduced invalid SVE source
  selection; the corrected target built without it. The reasoning baseline
  exited 134 at the exact assertion; the complete series passed all 13 tests.
- Both baseline and patched trees passed the upstream quantizer target. Emitted
  assembly moved from 31 scalar byte stores and no vector operations to zero
  byte stores, six vector narrows, and two vector stores.
- All twelve paired 20,000-iteration Q8 rounds improved. Median ratios were
  1.956x at 4,096 values, 1.950x at 65,536, and 1.958x at 655,360.
- Independent ingestion matched the uploaded summary byte for byte at SHA-256
  `32e01c0baf21de4679ace516a1ef61f7520dbbbc641d218aa454380e0c9767fa`.
  The retained claim is limited to current-revision applicability, targeted
  correctness, and direct Q8 hot-path performance; no model-wide or full
  upstream-CI result is implied.
- Public clean-checkout run `30676167725` passed on native `aarch64` from the
  exact retained-result commit `b9dbd76`: 106 tests, all 16 immutable hashes,
  E6d mechanism and gate checks, exact planner recomputation, and the
  dependency-free demo smoke test.

## 2026-08-01 — E6e upstream-equivalent Arm CPU lane frozen

- Audited llama.cpp's pinned `build-cpu.yml` `ubuntu arm64` job and the test
  registry at `b10216`. The source registers 47 tests under the `main` label.
- Froze one broader native lane for the complete patch series: GCC/G++ 14,
  Release, fatal warnings, RPC, native tuning, explicit KleidiAI, the complete
  default build target, and the full upstream `main` CTest label.
- Acceptance requires zero test failures, errors, or skips and explicitly binds
  the reasoning-budget, quantizer-correctness, and quantizer-performance tests.
  This can establish one upstream-equivalent Arm CPU lane only; it does not
  represent the complete cross-platform or accelerator matrix.

## 2026-08-01 — E6e broader Arm CPU lane passes

- Native run `30676413765` completed in 6m16s. The complete Release default
  target built under GCC/G++ 14 with fatal warnings, RPC, native tuning, all
  tests, and explicit KleidiAI enabled.
- CTest passed all 46 tests carrying the upstream `main` label plus its required
  model-download fixture: 47/47 total, zero failures, zero errors, and zero
  skips. The reasoning-budget and both quantizer tests were clean.
- A separate local invocation reproduced the uploaded manifest byte for byte at
  SHA-256
  `63c0e450d967208e3eb81d21571c73354e8520940933434914920db5d63c27f1`.
  This accepts one upstream-equivalent native Arm CPU lane only, not the full
  platform, sanitizer, packaging, accelerator, or release matrix.
- Public clean-checkout run `30676781968` passed on native `aarch64` from exact
  retained-result commit `23ee4e5`: 108 tests, all 17 immutable hashes, E6d/E6e
  evidence checks, exact planner recomputation, and the demo smoke test.

## 2026-08-01 — Judge-facing optimization chain refreshed

- Rechecked the official organizer updates and unpublished project gallery. The
  latest guidance emphasizes the 40-point technical category, reusable impact,
  and a visible baseline → technical change → measured result → meaning chain.
  The gallery still exposes no official entries; its roughly 2,000 participants
  are not treated as competitors or submissions.
- Added compact optimization maps to the repository and Devpost draft covering
  model quality, prompt reuse, KV/context memory, prompt batching, Arm repack
  tiers, the NEON Q8 patch, and current-source robustness. Each row separates
  its frozen experiment and product disposition so effects are not summed.
- Kept the negative boundaries visible beside the wins: concurrency, cached
  concurrency, q4_0 KV, batch 32, and Flash Attention all remain rejected under
  their original gates.

## 2026-08-01 — E5j thread-efficiency profile frozen

- Audited the selected launch path and found its four-thread default had never
  been challenged independently of model, cache, batch, and graph choices.
- Added a bounded launcher thread override that cannot exceed the validated
  four-thread runtime contract and records identical inference and prompt-batch
  thread pools in the hashed recipe. The unflagged default remains unchanged.
- Extended the native request probe to sample the live `llama-server` process
  CPU counters after warmups and around only the measured requests. Integer
  user/system ticks, clock rate, CPU seconds per request, and average cores used
  are retained; model load, warmups, the client, and shutdown are excluded.
- Froze a 4–3–2–2–3–4 study with exact-answer and prefix-reuse gates, 95%
  throughput retention, 5% median/p95 latency tolerance, and a required 5% CPU
  seconds/request reduction. CPU time is not represented as energy or power.
- Native attempt `30677290911` stopped before model download, build, or
  measurement because its source proof searched for a nonexistent combined
  `n_threads_batch` symbol. Pinned source uses
  `params.cpuparams_batch.n_threads`; the proof now binds the exact public
  `--threads` and `--threads-batch` option declarations. No experiment input,
  order, measurement, or gate changed.

## 2026-08-01 — E5j retains the four-thread default

- Native run `30677332825` completed all six cells in 10m7s. Every profile
  reproduced 23/30 twice, with stable predictions, prefix reuse, and zero
  request failures.
- Three threads used 2.982 average server cores but reduced CPU seconds/request
  only 0.11%; throughput retention was 75.52%, and median/p95 latency rose
  31.53%/36.34%. Two threads used 1.995 cores, saved 1.36% CPU time/request,
  retained 51.18% throughput, and nearly doubled latency.
- Both candidates failed the unchanged CPU-time, throughput, and latency gates.
  Four threads remains the default; CPU time supports no energy or power claim.
- Python 3.10 independent ingestion matched the uploaded summary byte for byte
  at SHA-256
  `747b6795d42be691c07cf5aac38237095477d06149e787cc313ec2b9558c4ff7`.
- Public clean-checkout run `30677849517` passed on native `aarch64` from exact
  retained-result commit `cdcb34b`: 114 tests, all 18 immutable hashes,
  E5j/E6d/E6e evidence checks, exact planner recomputation, and the demo smoke
  test.

## 2026-08-01 — E6f current-runtime application lane frozen

- Identified the remaining current-source gap: E6d/E6e validate the complete
  three-patch series on llama.cpp `b10216`, but the selected application service
  still has only `b10208` model-level evidence.
- Froze a same-job clean-b10208 versus patched-b10216 comparison with matched
  native/KleidiAI Release builds and the exact selected f16/256/64 cached,
  repacked, four-thread single-slot service.
- The 4-cell reverse-balanced lane binds source tags/commits, all three patch
  hashes and changed files, CMake settings, model bytes, recipes, timed server
  commands, live PIDs, CPU counters, prefix reuse, and raw predictions.
- Current source must retain every selected answer, at least 95% throughput,
  median/p95 latency and CPU time within 5%, readiness within 10%, and maximum
  RSS within 64 MiB. Even a pass is only an upgrade candidate until a separate
  product launch contract is integrated and verified.
- Native attempt `30678221353` completed both exact builds, both runtime buffer
  proofs, and all four measurement cells, then stopped during ingestion. The
  validator correctly rejected empty version evidence: `llama-server --version`
  emits on stderr, while both new capture sites retained only stdout. Both sites
  now combine stdout/stderr and a regression test reproduces the stderr-only
  behavior. The frozen sources, patches, model, service, order, and gates did not
  change.

## 2026-08-01 — E6f current runtime earns an upgrade-candidate result

- Corrected native run `30678703184` completed in 10m22s. Both exact builds,
  both runtime buffer proofs, and all four fresh-server cells passed.
- Patched `b10216` reproduced 23/30 twice with stable predictions, prefix reuse,
  and no failures. It retained 100.28% throughput; median/p95 latency ratios
  were 0.9918x/0.9939x and server CPU seconds/request was 0.9993x baseline.
- Median readiness was 1.0482x baseline and maximum RSS increased 100 KiB. Every
  unchanged quality, throughput, latency, CPU-time, readiness, and RSS gate
  passed.
- Independent Python 3.10 ingestion reproduced the uploaded result byte for byte
  at SHA-256
  `da95b831a0cccf3b16dd45e93e11855a6e0322c5aa163d145c24243b42470ace`.
  The claim remains one exact native Arm selected-service upgrade candidate;
  automatic product promotion, energy, model-wide, and full-matrix claims stay
  disallowed pending separate launch provenance integration.

## 2026-08-01 — Current-runtime launch provenance integrated explicitly

- Preserved immutable E3f model evidence and the unflagged historical `b10208`
  path. Current source is an opt-in rather than a silent commit substitution.
- Added a separate launch contract pinned to the E6f manifest, b10216 commit,
  three patch hashes, exact four-file combined diff, and matched CMake flags.
- The adapter now verifies local git HEAD/diff, CMake source/build binding,
  server location/version/binary hash, model bytes, and the exact E6f service
  before writing a launch recipe. Partial inputs and object/file mismatches fail
  closed.
- Current source admits only the measured repacked, f16 K/V, 256-token, 64/64,
  automatic-Flash, cached, four-thread, one-slot profile. Historical lower-thread,
  no-repack, concurrency, and alternate graph controls do not inherit E6f.

## 2026-08-01 — E6g native launch integration frozen

- Froze a single current-source product reproduction that builds the exact
  patched b10216 tree, downloads the selected model, and launches through the
  new E6f-bound Pareto64 adapter rather than reconstructing its server argv.
- The adapter recipe, git diff, CMake cache, copied server binary, live PID,
  readiness, slots, metrics, process CPU counters, and all raw responses are
  retained for independent ingestion.
- E6g requires the exact 23/30 prediction map, prefix reuse in every measured
  request, zero failures, and absolute readiness/RSS gates. It is not a new
  performance comparison and cannot broaden the one validated service profile.
- Native attempt `30679759732` stopped before model download or build because
  the new source proof omitted E6f's `--full-index` diff option. The patch
  contents and changed-file inventory matched, but abbreviated object IDs
  changed the byte hash. Both product and workflow diff capture now use the
  exact E6f full-index format; inputs, source, service, and gates are unchanged.

## 2026-08-01 — E6g validates the exact current-runtime launch

- Corrected native run `30679814341` rebuilt the exact patched b10216 source and
  launched the selected service through the E6f-bound Pareto64 adapter.
- All 30 measured requests succeeded, reproduced the selected 23/30 prediction
  map without drift, and observed cached-prefix reuse. Readiness was 3.980
  seconds, throughput was 0.93038 requests/s, maximum RSS was 4,453,376 KiB, and
  server CPU time was 4.2467 seconds/request.
- The result binds the full-index source diff, patch set, git commit, CMake
  cache, copied server binary, model, recipe, live PID, one slot, metrics, and
  exact arguments. Other profiles and energy/full-matrix claims remain excluded.
- Independent Python 3.10 ingestion reproduced the uploaded result byte for byte
  at SHA-256
  `13496b5e62e50bc3e617e6a80631c87ac6bc29015ea83499cb2ff885ec404ac9`.
- Public clean-checkout run `30680198942` passed on exact retained-result commit
  `e92f4ff`: 122 tests, all 23 immutable hashes, E6g runtime/source/build/binary
  assertions, exact planner recomputation, and demo smoke.

## 2026-08-01 — E6h current-runtime memory-tier lane frozen

- Identified the remaining runtime split: E6g validates patched b10216 only for
  the repacked fast service, while the ≤3-GiB no-repack tier remains application-
  qualified on historical b10208.
- Froze a reverse-balanced historical/current comparison with no repack in every
  cell and all other model, build, service, workload, seed, and output settings
  fixed. Runtime proofs must show the mapped buffer and no repack buffer.
- Current source must reproduce every selected prediction and cached prefix,
  retain at least 95% throughput, keep median/p95 latency and server CPU time
  within 5%, readiness within 10%, RSS growth within 64 MiB, and every cell below
  3 GiB. Even a pass requires separate memory-tier launch integration.
- Refactored the E6f workflow/ingester to select either frozen contract while
  keeping fast as the default. Python 3.10 replay of run `30678703184` remained
  byte-identical at `da95b831…70ace`; the immutable E6f result did not change.
- Native attempt `30689986153` completed both exact builds, then stopped before
  any service cell because `llama-bench` does not accept the server's
  `--no-repack` option. The corrected mechanism step starts each exact server at
  proof-only log verbosity, verifies the mapped buffer and absence of a repack
  buffer, then shuts it down before the unchanged measured matrix.

## 2026-08-01 — E6h qualifies the current no-repack memory tier

- Corrected native Arm run `30690331795` passed every frozen gate on exact
  commit `c870e48`. Both revisions reproduced 23/30 twice with stable
  predictions, zero mismatches, zero failures, and cached-prefix reuse in every
  measured request.
- Patched b10216 retained 1.002403x throughput, used 0.998506x baseline server
  CPU seconds/request, and produced median/p95 HTTP latency ratios of
  0.998331x/0.998420x. Its readiness ratio was 0.943511x.
- Maximum RSS was 2,381,344 KiB, 180 KiB above clean b10208 and below the frozen
  3-GiB ceiling in every cell. Both proof starts showed the mapped buffer and no
  `CPU_REPACK` buffer.
- Independent Python 3.10 replay reproduced the uploaded manifest byte for byte
  at SHA-256
  `7b112b385729ef092f2026bf35b63926ac985251d70faea2cf03e4936253b27f`.
- The retained decision is only a no-repack memory-tier upgrade candidate. E5h
  remains the fast-versus-memory comparison, and a separate launch integration
  must pass before Pareto64 can start this profile on b10216.
- Public clean-checkout run `30690973261` passed on exact retained-result commit
  `3af7da4`: 125 tests, all 25 immutable hashes, E6h result assertions, exact
  planner/runtime checks, and the dependency-free demo smoke test.

## 2026-08-01 — E6i current memory-tier launch integration frozen

- Added a second current-runtime launch contract bound to the immutable E6h
  manifest and its exact no-repack f16/256/64, cached, four-thread, one-slot
  service. The existing E6f/E6g fast contract remains unchanged.
- Generalized the runtime validator with an explicit E6f/E6h evidence allowlist;
  each evidence shape retains its own accepted status and claim flag. Unknown
  experiments, swapped hashes, and cross-profile service settings fail closed.
- Generalized the E6g workflow/ingester to dispatch either fast E6g or memory
  E6i. The memory path must carry `--no-weight-repack`, produce exactly one
  server `--no-repack` argument, reproduce 23/30 with prefix reuse, and stay at
  or below 3 GiB.
- Independent Python 3.10 replay of retained E6g after the shared-code change
  remained byte-identical at `13496b5e…404ac9`; the fast integration result did
  not change.

## 2026-08-01 — E6i validates the current no-repack product path

- Native Arm run `30691254831` passed on exact frozen commit `f0ef0e7`. The job
  rebuilt exact patched b10216, verified E3f/E6h and all source/build/binary/model
  inputs, then executed the memory service through `python -m pareto64 launch`.
- All 30 requests succeeded and reproduced 23/30 with zero reference drift and
  cached-prefix reuse throughout. Readiness was 2,242.22 ms, throughput was
  0.448567 req/s, median/p95 HTTP latency was 2,424.61/3,323.20 ms, and measured
  server CPU was 8.84967 seconds/request.
- Maximum RSS was 2,381,040 KiB, below the frozen 3-GiB product ceiling. The
  recipe bound the E6h and memory-contract hashes, exact patched diff, four
  threads, one slot, f16/256/64, cache, and explicit no-repack setting.
- Independent Python 3.10 replay reproduced the uploaded manifest byte for byte
  at SHA-256
  `2bcbd7e1a7b727a763ca12c9664106a82d9ef8a70ec17ef1ac2fe9ed460c06d2`.
- This integrates only the exact memory service. E6g remains the separate fast
  integration; other profiles, energy, and the full upstream matrix remain out
  of scope.
- Public clean-checkout run `30691572261` passed on exact retained-result commit
  `60aa902`: 128 tests, all 28 immutable hashes, both current-runtime launch
  integrations, exact planner/runtime assertions, and demo smoke.

## 2026-08-01 — E7a LTO compiler/build ablation frozen

- Audited the remaining optimization fronts after E6i. All selected-service
  builds used the default Release `-O3` path with upstream `GGML_LTO=OFF`, so
  whole-program optimization remained an unmeasured build front.
- Inspected exact llama.cpp `b10216` source at commit `876a432…f282`: the
  `GGML_LTO` option is off by default and enables CMake interprocedural
  optimization only after `check_ipo_supported` succeeds.
- Froze exact patched `b10216`, GCC, native/KleidiAI, model, fast-service,
  workload, and reverse-balanced order. `GGML_LTO=OFF` versus `ON` is the only
  profile difference, proven from each CMake cache and full Ninja command set.
- Added hashed transitive build-local runtime-closure capture. The raw artifact
  contains the exact server/shared-library bytes rather than trusting a derived
  size alone; system libraries are explicitly excluded.
- Predeclared two non-weighted benefit paths: at least 1.03x throughput with no
  more than 1.05x closure, or at least 5% smaller closure while retaining at
  least 98% throughput. Exact quality plus latency, CPU-time, readiness, RSS,
  and build-cost guardrails apply to both paths. A miss retains LTO-off.
- Contract SHA-256 is
  `2d57010a168a777cc5de2ed2a7d6e0f11900d14a30d44ded6db34ecd85b1aa12`.
  The result cannot support energy, other-model/service/backend, or automatic
  product-promotion claims.

## 2026-08-01 — E7a retains LTO-off after a valid native no-win

- Native Arm run `30692292700` passed on exact frozen commit `64adb12` in
  10m42s. Both build caches and command inventories proved the single LTO
  difference; all eight transitive build-local runtime files per profile were
  copied, hashed, and checked against the captured `ldd` inventories.
- LTO-off/on reproduced 23/30 twice with stable predictions, zero reference
  mismatches or request failures, and cached-prefix reuse in every request.
  Every shared latency, measured CPU, readiness, RSS, and build-cost guardrail
  passed.
- LTO delivered only 1.001374x throughput and a 0.992250x runtime closure
  (20,059,048 to 19,903,600 bytes). It therefore missed both the frozen 1.03x
  throughput and 0.95x closure benefit branches. LTO-off remains selected.
- Candidate median/p95 latency ratios were 0.991672x/1.000956x, CPU
  seconds/request was 0.999532x, readiness was 1.029564x, maximum RSS decreased
  28 KiB, and build-time ratio was 0.961845x.
- Independent Python 3.10 replay reproduced the uploaded manifest byte for byte
  at SHA-256
  `b48e6c129d1f3305c2b788b422bc5321cd415b2bc2b26460804063ebc3b46839`.
  This is a retained compiler/build no-win, not an energy or broader service
  claim.
- Public clean-checkout run `30692856958` passed on exact retained-result commit
  `23ee23e`: 135 tests, all 30 immutable hashes, E7a contract/result assertions,
  exact planner/runtime checks, and the dependency-free demo smoke test.

## 2026-08-01 — E7b loopback HTTP dependency ablation frozen

- Audited the retained E7a `ldd` inventories and exact upstream `b10216` build
  definitions. `LLAMA_OPENSSL` defaults on specifically for HTTPS support;
  cpp-httplib then defines `CPPHTTPLIB_OPENSSL_SUPPORT` and links OpenSSL. The
  selected service is fixed to plain loopback HTTP but still resolves
  `libssl.so.3` and `libcrypto.so.3` in the default build.
- Performed a mechanism-only x86 screen on exact three-patch `b10216`. The
  `LLAMA_OPENSSL=OFF`, LTO-off server built and reported commit `876a43211`; its
  cache recorded the disabled option, its full Ninja command set contained no
  OpenSSL support/link marker, and `ldd` contained neither OpenSSL library. This
  is functional screening only, not Arm performance evidence.
- Froze one native Arm on/off experiment with the build option as the only
  profile difference and an on–off–off–on fresh-service order. The raw artifact
  retains CMake caches, full build commands, `ldd` inventories, and individually
  hashed build-local runtime files alongside all quality and service evidence.
- The candidate must remove both frozen OpenSSL edges, add no dependency,
  reproduce 23/30 twice with prefix reuse and zero drift/failures, retain at
  least 98% throughput, keep the local closure no larger, and pass latency,
  measured CPU, readiness, RSS, and build-cost guardrails. A miss retains
  OpenSSL-on; HTTPS, security, installed-package size, energy, and broader
  service claims remain excluded.
- Contract SHA-256 is
  `2c5cd9f8d84ef5f77fdd14c66a7822189ec09ff6688743e26f7f2fd7c77abea9`.
  Python 3.10 replay after extracting the shared service summarizer left E7a
  byte-identical at `b48e6c12…b46839`.
- The bounded final-evidence decision selected a local Arm device for controlled
  power/governor work. A follow-up decision is pending for the device platform;
  no sensor or governor interface has been assumed.

## 2026-08-01 — E7b validates HTTP-only dependency pruning

- Native Arm run `30695349303` passed on exact frozen commit `c47dfe7` in
  10m06s. The two CMake caches and full Ninja command inventories proved the
  single `LLAMA_OPENSSL` difference, and the ingester independently revalidated
  both raw `ldd` inventories and all copied build-local runtime files.
- The OpenSSL-on baseline resolved `libssl.so.3` and `libcrypto.so.3` among 15
  dependency basenames. OpenSSL-off removed exactly those two edges, added no
  dependency, and retained the same eight logical build-local files. Their
  total fell 201,256 bytes, from 20,058,904 to 19,857,648 bytes (0.989967x).
- Both profiles reproduced 23/30 twice with stable predictions, zero drift or
  failures, and cached-prefix reuse throughout. Candidate throughput was
  0.999811x baseline; median/p95 latency ratios were 0.999401x/1.001827x;
  measured CPU seconds/request was 1.001021x; readiness was 1.036803x; and
  maximum RSS decreased 1,544 KiB. Every frozen guardrail passed.
- Candidate build time was 193.08 seconds versus 203.62 seconds, a 0.948237x
  ratio. Build-process peak RSS was 2,718,396 versus 2,943,064 KiB. These remain
  supporting costs rather than headline optimization claims.
- Independent Python 3.10 replay reproduced the uploaded manifest byte for byte
  at SHA-256
  `8dffd667e8517a1b628c147f22f5e74755ab7d7d693e8eff1e1704ae387ffd9b`.
  OpenSSL-off is admitted only as a candidate for a separate loopback HTTP
  launch integration; HTTPS, security, installed-package size, energy, and
  other-service claims remain excluded.
- Public clean-checkout run `30695888838` passed on exact retained-result commit
  `d00be1c`: 141 tests, all 32 immutable hashes, E7b contract/result assertions,
  exact planner/runtime checks, and the dependency-free demo smoke test.

## 2026-08-01 — E7c HTTP-only launch integration frozen

- Added a third evidence-bound current-runtime contract rather than weakening
  the validated E6g fast or E6i memory contracts. It accepts only the retained
  E7b candidate, exact patched b10216 source, LTO-off/OpenSSL-off CMake cache,
  repacked fast service, and absence of `libssl.so.3`/`libcrypto.so.3` from the
  local server's dynamic dependency inventory.
- Generalized the Pareto64 runtime validator for E7b's build-profile evidence
  shape. The adapter still binds model/runtime input hashes, source diff,
  build-root relationship, server path/version/hash, and exact service before
  launch; it now also runs `ldd`, fails on unresolved/forbidden dependencies,
  and records the observed basenames in the launch recipe.
- The workflow independently retains a second raw `ldd` capture. E7c ingestion
  requires that inventory to match the adapter recipe before accepting the live
  30-request quality/cache/readiness/RSS/process proof.
- Python 3.10 replays of the shared E6g and E6i ingester paths remained
  byte-identical at `13496b5e…404ac9` and `2bcbd7e1…06d2` after the
  generalization.
- Runtime-contract SHA-256 is
  `95cb669b70de98851b8bb2f04d7be6650745e0fbd39aa4d3256b5bb9c2a2b928`;
  experiment-contract SHA-256 is
  `2f6a96acb0fa7c877c7f42083cd85b728c5779a75173bdcca62d801b306344de`.
  HTTPS, security, installed-package, energy, other-profile, and full-upstream
  claims remain explicitly excluded.

## 2026-08-01 — E7c first native attempt rejected before ingestion

- Native Arm run `30696286405` rebuilt the exact OpenSSL-off b10216 service,
  passed the evidence-bound Pareto64 launch adapter, and completed all 30 live
  requests. The independent ingester then rejected the result with
  `KeyError: 'request'` before validating any retained probe result.
- Root cause was a missing top-level request protocol in the new E7c experiment
  contract. The launcher and probe had inherited the unchanged E6g protocol,
  but the independent validator correctly requires that protocol to be frozen
  explicitly. E7c now copies the exact E6g/E6i warmups, 30-task order,
  eight-token cap, system instruction mode, temperature, seed, and timeout.
  No model, runtime, service, acceptance threshold, or completed native output
  was changed or accepted retroactively. The corrected complete contract is
  frozen at SHA-256
  `2f6a96acb0fa7c877c7f42083cd85b728c5779a75173bdcca62d801b306344de`;
  the incomplete first-attempt hash remains recoverable from commit `1ba321e`.

## 2026-08-01 — E7c native HTTP-only launch integration retained

- Corrected native Arm run `30696606993` passed on exact checkpoint `249e044`
  in 4m50s. The OpenSSL-off b10216 service built, launched only through the
  E7b-bound Pareto64 adapter, completed all 30 requests, passed independent
  ingestion, and uploaded the raw evidence artifact.
- All requests reproduced the selected 23/30 map with zero drift or failures
  and prefix reuse throughout. Throughput was 0.9302566 requests/s, median/p95
  HTTP latency 1,065.13/1,852.71 ms, server CPU time 4.247 seconds/request,
  readiness 4,356.71 ms, and maximum RSS 4,449,416 KiB.
- The adapter recipe and second raw `ldd` capture matched on 13 dependency
  basenames; neither `libssl.so.3` nor `libcrypto.so.3` was present. Python
  3.10 replay reproduced the uploaded manifest byte for byte at SHA-256
  `f4e73971b0c6f2db25be52e365cf611848ec1bb1d738648bb43bdf4c2e1857cf`.
  HTTPS, security, installed-package, energy, other-profile, and full-upstream
  claims remain excluded.
- Public clean-checkout run `30697133805` passed on exact retained-result commit
  `915717e`: native `aarch64`, all 145 tests, all 35 immutable hashes, E7c
  dependency/launch assertions, exact planner/runtime checks, and the
  dependency-free demo smoke test.

## 2026-08-01 — Final local-device evidence obligations audited

- Chose the already-promoted shared-prefix cache as the isolated E8a power
  question rather than combining unrelated product changes. Both sides retain
  the exact E7c source/build/server recipe; only request-level `cache_prompt`
  changes, with raw reused-token evidence required in every request.
- Defined two opposite-start four-cell blocks, four fresh-process repetitions
  per configuration, a post-warmup measured window, gross joules/request as the
  primary metric, supporting idle/thermal/frequency evidence, and immutable
  quality, sensor-domain, governor/power-mode, and power-source gates.
- Predeclared at least 1.10x repeated-median throughput and at most 0.90x gross
  joules/request. A valid miss remains a no-win. Monetary results require a
  bound tariff source/date/currency; local energy must not be mixed with cloud
  instance pricing or uncontracted hardware amortization.
- Left the sensor collector deliberately unfrozen. Linux, Apple Silicon, and
  Android expose materially different power and power-mode boundaries, and the
  authenticated platform reply has not yet been delivered into the task.
