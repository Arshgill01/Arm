# Arm AI Optimization Challenge Lab

Research, experiments, and the eventual submission for the **Arm Create: AI
Optimization Challenge 2026**.

[![Native Arm submission validation](https://github.com/Arshgill01/Arm/actions/workflows/submission-validation.yml/badge.svg)](https://github.com/Arshgill01/Arm/actions/workflows/submission-validation.yml)

The event asks entrants to create, migrate, or optimize an AI solution on Arm
architecture in one of three published tracks: Physical AI, Cloud AI, or Mobile
AI. The submission deadline is **August 14, 2026 at 4:00 PM PDT** (23:00 UTC;
August 15 at 04:30 IST).

## Final Cloud AI project

**Pareto64** is the final Cloud AI direction: a quality-constrained deployment
planner and verified launch path for Arm64 AI inference. Native feasibility,
quality, serving, and novelty gates have passed; rejected speedups and empty
frontiers remain part of the public evidence.

The product core is now executable: it validates schema-1 E3, E3b, E3c, E3d,
E3e, or E3f evidence, applies explicit quality and SLO gates, recomputes the Pareto
frontier, and emits a hashed deployment decision without a hidden weighted
score.

The judge-facing package is available in [`submission/`](submission/), and the
dependency-free interactive evidence demo is in [`demo/`](demo/). Verify the
compact submission from a clean checkout with:

```bash
python3 scripts/verify_submission.py
python3 -m unittest discover -s tests -v
python3 -m http.server 4174 --directory demo
```

E3c and E3d measured exact quantizations of Apache-2.0 Qwen3-4B and Qwen3.5-4B.
Their best stable score was 66.67% under the unchanged 75% task floor, so no
inference adapter may launch from either result. E3e's predeclared bounded-
reasoning run was correctly rejected: budget 0 failed the runtime's documented
immediate-end mechanism. That failure exposed a reproducible upstream sampler
state bug; no E3e frontier or deployment plan is accepted. E6c validated the
exact source correction and zero-reasoning behavior on Arm, but its frozen
eight-token standalone-answer gate rejected the application run. E3f's
Ministral 3 Q4_K_M is the first candidate to clear the unchanged quality and
cloud SLO gates. A fail-closed launch adapter now binds that selection to the
exact model hash and pinned llama.cpp build. E5b validates native inference
serving with zero answer drift while rejecting a marginal two-slot tuning win.
E5c then preserves all 120 answers while quality-gated shared-prefix caching
raises repeated median throughput 1.672x and cuts median HTTP latency 41.3%.
E5d tests the combined cache-plus-concurrency setting and rejects two slots
again: only 1.0619x throughput with 93.3% higher median HTTP latency.
E5e then right-sizes the validated application context from 2,048 to 256 tokens,
reducing maximum process RSS by 183.36 MiB while preserving every answer and
99.62% of throughput. Lower-precision q4_0 KV cache was faster but changed a
stable answer, so the product promotes the f16 right-sized profile instead.
E5f then promotes a 64/64 logical/physical prompt batch: every answer remains
exact, the CPU compute buffer falls 75%, maximum RSS falls 14.48 MiB, and
throughput rises 2.26%. The intermediate 128/128 profile is rejected because
its process-RSS reduction misses the frozen 8 MiB gate.
E5g then tests the next staged boundary. A 32/32 batch halves the remaining
compute buffer and preserves every answer and performance gate, but maximum RSS
increases by 660 KiB. It is not promoted, 64/64 remains the default, and the
predeclared study stops before 16/16.
E5h then removes the Arm weight-repack buffer under a separate frozen contract.
The no-repack path preserves every answer and lowers maximum RSS by 2,072,268
KiB to 2,381,264 KiB, while throughput falls to 48.47% of the repacked service.
Repacking remains the fast default; `--no-weight-repack` is retained as an
explicit low-memory tier.
E5i finally ablates the selected service's resolved Flash Attention graph.
Auto preserves every answer, improves throughput 3.22% and median latency
6.18%, and saves 7,384 KiB RSS, but p95 latency rises 6.03%. It misses the
frozen 1.05x throughput and p95 non-regression gates, so no material Flash
Attention serving win is claimed.
E6d rebases the three Arm source contributions onto llama.cpp `b10216` and
revalidates them natively. The feature and reasoning failures reproduce before
their fixes, all targeted tests pass after the complete series, and all twelve
paired Q8 rounds improve by roughly 95%. Its claim remains bounded to this
frozen current revision, targeted correctness, and direct hot-path performance.
E6e broadens that proof through an upstream-equivalent native Arm CPU lane: the
complete fatal-warnings build passes with KleidiAI enabled, followed by 47/47
CTest executions without a failure, error, or skip. It is one validated Arm CPU
lane, not the full upstream platform and backend matrix.

```bash
python3 -m pareto64 plan \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json \
  --output results/plans/e3f-cloud-quality.json
```

The selected model now has a second, measured decision stage. A throughput
policy selects the Arm-repacked service, while an at-most-3-GiB policy selects
the exact no-repack tier and emits its bounded launcher argument:

```bash
python3 -m pareto64 service-plan \
  --manifest results/manifests/e5h-30672633366.json \
  --constraints configs/service-memory.json
```

The retained result is `repack_off` with `--no-weight-repack`. Replace the
policy with [`configs/service-throughput.json`](configs/service-throughput.json)
to select `repack_on`; a policy no measured tier can satisfy returns
`no_feasible_profile` instead of guessing.

The verified launcher accepts the same evidence/policy pair through
`--service-manifest` and `--service-constraints`. It binds both hashes into the
launch recipe and applies the selected repack mode automatically. A manual
repack flag that conflicts with the plan is refused.

## Native evidence so far

| Gate | Outcome |
| --- | --- |
| [E0](results/reports/e0-native-arm.md) | Native four-core Neoverse N2 runner and repeatability characterized |
| [E1](results/reports/e1-llm-runner-smoke.md) | Pinned LLM-Runner built and executed end to end on Arm |
| [E2](results/reports/e2-kleidiai-ablation.md) | Primary KleidiAI threshold missed; smaller decode/latency benefits retained |
| [E3](results/reports/e3-qwen-frontier.md) | Three Qwen packages measured; frozen quality gate rejected all three |
| [E3b](results/reports/e3b-quality-anchor.md) | 7B improved to a stable 73.33% but missed the unchanged quality floor by one task |
| [E3c](results/reports/e3c-quality-per-byte.md) | Q4_K_M led a stable 4B quantization sweep at 66.67%; the unchanged quality gate rejected all variants |
| [E3d](results/reports/e3d-current-runtime.md) | Current Qwen3.5 Q4_0/Q8_0 both reached a stable 66.67%; Q8_0 was faster but exceeded load and RSS ceilings |
| [E3e](results/reports/e3e-bounded-reasoning.md) | Invalid mechanism run exposed a reproducible zero-budget forced-token state bug; no frontier was created |
| [E3f](results/reports/e3f-ministral-frontier.md) | Q4_K_M reached a stable 76.67% and passed every frozen quality, latency, load, RSS, and package gate |
| [E4a](results/reports/e4a-backlog-tuner.md) | Native bounded tuner selected backlog 64 with zero failures or tail breaches |
| [E5a](results/reports/e5a-planner-api.md) | Native fail-closed API passed load SLOs; one-second tail retained for tuning |
| [E5b](results/reports/e5b-selected-inference.md) | Exact selected-model serving reproduced 23/30 with zero drift; two slots missed the 1.10x throughput gate |
| [E5c](results/reports/e5c-prompt-cache.md) | Quality-gated shared-prefix caching preserved all 120 answers and raised throughput 1.672x while cutting median HTTP latency 41.3% |
| [E5d](results/reports/e5d-cached-concurrency.md) | Cached two-slot serving preserved all answers but reached only 1.0619x throughput while nearly doubling median latency; one slot remains the default |
| [E5e](results/reports/e5e-kv-context-profile.md) | A 256-token f16 context preserved all answers and saved 183.36 MiB maximum RSS; q4_0 drifted and was rejected |
| [E5f](results/reports/e5f-prompt-batch-profile.md) | A 64/64 prompt batch preserved all answers, cut the compute buffer 75%, and saved 14.48 MiB maximum RSS |
| [E5g](results/reports/e5g-prompt-batch-floor.md) | A staged 32/32 boundary preserved quality and speed but added 660 KiB maximum RSS; 64/64 remains the default |
| [E5h](results/reports/e5h-weight-repack-boundary.md) | No-repack preserved every answer and saved 2,072,268 KiB RSS; it is a slower explicit memory tier while repack stays default |
| [E5i](results/reports/e5i-flash-attention-ablation.md) | Resolved Flash Attention preserved quality but gained only 1.0322x throughput and worsened p95 6.03%; no material win is claimed |
| [E6a](results/reports/e6a-native-feature-fix.md) | Reproduced and fixed invalid native KleidiAI SVE source selection |
| [E6b](results/reports/e6b-q8-vector-store.md) | NEON vector narrowing doubled isolated Q8_0 quantizer throughput with neutral real-model inference |
| [E6c](results/reports/e6c-reasoning-budget-fix.md) | Source fix passed 13 upstream tests and removed all reasoning output; the frozen final-answer gate still rejected the real-model run |
| [E6d](results/reports/e6d-current-upstream-patches.md) | All three Arm patches revalidated on llama.cpp b10216; targeted tests passed and direct Q8 throughput improved about 95% |
| [E6e](results/reports/e6e-upstream-arm-cpu-lane.md) | Complete upstream-equivalent native Arm CPU build passed, followed by 47/47 clean CTest executions |

Negative results remain first-class evidence. No runtime is promoted into the
planner until it passes a predeclared quality/SLO contract.
The E5f through E5i, E6d, and E6e results are retained under their exact frozen
contracts and independently re-ingested byte for byte.

## Repository map

- [`docs/hackathon-requirements.md`](docs/hackathon-requirements.md): rules,
  deliverables, judging, dates, and compliance checklist.
- [`docs/track-analysis.md`](docs/track-analysis.md): published track boundaries
  and cross-front optimization opportunities.
- [`docs/strategy.md`](docs/strategy.md): concept comparison and the leading
  single-project hypothesis.
- [`docs/product.md`](docs/product.md): executable planner behavior, policy
  contract, and current E2E boundary.
- [`results/reports/service-tier-planner.md`](results/reports/service-tier-planner.md):
  measured E5h service-envelope decisions and refusal boundary.
- [`docs/experiment-plan.md`](docs/experiment-plan.md): ordered, gated benchmark
  program.
- [`docs/environment.md`](docs/environment.md): current host, native Arm routes,
  and measurement constraints.
- [`docs/relevant-resources.md`](docs/relevant-resources.md): vetted frameworks,
  profiling tools, starters, environments, and license traps.
- [`docs/competitive-landscape.md`](docs/competitive-landscape.md): prior winning
  patterns and current public competitor intelligence.
- [`docs/open-questions.md`](docs/open-questions.md): contradictions that require
  organizer clarification or a conservative working assumption.
- [`docs/source-registry.md`](docs/source-registry.md): URLs and source authority.
- [`experiments/README.md`](experiments/README.md): evidence contract for every
  benchmark.
- [`configs/cloud-balanced.json`](configs/cloud-balanced.json): explicit example
  quality/SLO and selection policy.
- [`configs/cloud-quality.json`](configs/cloud-quality.json): predeclared
  quality-first policy that independently rejected the E3b near-miss.
- [`configs/service-throughput.json`](configs/service-throughput.json) and
  [`configs/service-memory.json`](configs/service-memory.json): measured E5h
  service-envelope policies for the fast and at-most-3-GiB deployments.
- [`patches/README.md`](patches/README.md): reviewable source-patch inputs and
  validation status.
- [`logs/progress.md`](logs/progress.md): chronological project journal.
- [`ops/telegram.md`](ops/telegram.md): phone notification and decision workflow.
- [`ops/telegram_decisions.py`](ops/telegram_decisions.py): authenticated,
  bounded Telegram-to-Codex decision bridge.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
