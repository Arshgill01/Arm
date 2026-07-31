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
