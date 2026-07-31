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
