# Arm AI Optimization Challenge Lab

Research, experiments, and the eventual submission for the **Arm Create: AI
Optimization Challenge 2026**.

The event asks entrants to create, migrate, or optimize an AI solution on Arm
architecture in one of three published tracks: Physical AI, Cloud AI, or Mobile
AI. The submission deadline is **August 14, 2026 at 4:00 PM PDT** (23:00 UTC;
August 15 at 04:30 IST).

## Current phase

1. Freeze the authoritative requirements and identify organizer-page conflicts.
2. Score candidate concepts against all judging criteria and optimization fronts.
3. Establish a correctness-first benchmark harness.
4. Run repeatable baselines and increasingly aggressive Arm-specific variants.
5. Validate the winning implementation end to end on real Arm hardware.

The provisional concept is **Pareto64**, a quality-constrained cross-runtime
planner for Arm AI inference. It becomes the final Cloud AI direction only if the
native feasibility and novelty gates in `docs/strategy.md` pass.

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

```bash
python3 -m pareto64 plan \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json \
  --output results/plans/e3f-cloud-quality.json
```

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
| [E6a](results/reports/e6a-native-feature-fix.md) | Reproduced and fixed invalid native KleidiAI SVE source selection |
| [E6b](results/reports/e6b-q8-vector-store.md) | NEON vector narrowing doubled isolated Q8_0 quantizer throughput with neutral real-model inference |
| [E6c](results/reports/e6c-reasoning-budget-fix.md) | Source fix passed 13 upstream tests and removed all reasoning output; the frozen final-answer gate still rejected the real-model run |

Negative results remain first-class evidence. No runtime is promoted into the
planner until it passes a predeclared quality/SLO contract.

## Repository map

- [`docs/hackathon-requirements.md`](docs/hackathon-requirements.md): rules,
  deliverables, judging, dates, and compliance checklist.
- [`docs/track-analysis.md`](docs/track-analysis.md): published track boundaries
  and cross-front optimization opportunities.
- [`docs/strategy.md`](docs/strategy.md): concept comparison and the leading
  single-project hypothesis.
- [`docs/product.md`](docs/product.md): executable planner behavior, policy
  contract, and current E2E boundary.
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
- [`patches/README.md`](patches/README.md): reviewable source-patch inputs and
  validation status.
- [`logs/progress.md`](logs/progress.md): chronological project journal.
- [`ops/telegram.md`](ops/telegram.md): phone notification and decision workflow.
- [`ops/telegram_decisions.py`](ops/telegram_decisions.py): authenticated,
  bounded Telegram-to-Codex decision bridge.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
