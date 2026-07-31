# AGENTS.md

This repository is the working lab and submission candidate for the 2026 Arm
Create: AI Optimization Challenge.

## Operating rules

- Treat benchmark evidence as a product feature. Never claim an improvement
  without preserving the raw result, command, environment, and comparison.
- Keep baseline and optimized paths runnable from a clean checkout.
- Optimize for Arm hardware, not just for the current x86_64 development host.
- Prefer reproducible scripts over hand-run commands.
- Record failed experiments and regressions; they prevent repeated dead ends.
- Keep third-party licenses and model/data provenance explicit.
- Do not commit credentials, model-provider tokens, cloud credentials, Telegram
  tokens, private datasets, or large generated artifacts.
- Use Apache-2.0-compatible dependencies unless a deliberate exception is
  documented.
- Make checkpoint commits after research, baselines, and verified improvements.

## Validation expectations

- Run the narrowest relevant check first, then the end-to-end benchmark when a
  change could affect measured behavior.
- Compare correctness/quality before comparing speed, memory, energy, or cost.
- Mark simulated or cross-architecture results clearly; final claims require an
  Arm-powered test target.

## Evidence layout

- `docs/`: authoritative requirements, strategy, and design decisions.
- `experiments/`: experiment definitions and reproducible harnesses.
- `results/`: machine-readable raw results and derived reports.
- `logs/`: chronological research and experiment journal.
- `ops/`: notification and unattended-run operations.

