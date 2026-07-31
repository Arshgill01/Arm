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

## Repository map

- [`docs/hackathon-requirements.md`](docs/hackathon-requirements.md): rules,
  deliverables, judging, dates, and compliance checklist.
- [`docs/track-analysis.md`](docs/track-analysis.md): published track boundaries
  and cross-front optimization opportunities.
- [`docs/strategy.md`](docs/strategy.md): concept comparison and the leading
  single-project hypothesis.
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
- [`logs/progress.md`](logs/progress.md): chronological project journal.
- [`ops/telegram.md`](ops/telegram.md): phone notification and decision workflow.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
