# E3e — bounded-reasoning frontier

Status: **invalid mechanism run; correctly rejected before frontier creation**.

## Result

[GitHub Actions run 30651144293](https://github.com/Arshgill01/Arm/actions/runs/30651144293)
completed all eight frozen native quality cells in 22m39s on one four-core
Neoverse N2 job. The ingester then rejected the artifact because the
zero-budget candidate emitted reasoning content. No E3e manifest, Pareto
frontier, or deployment plan is accepted from this run.

The failure is real, not missing evidence. Every zero-budget request consumed
the full eight-token output cap inside `reasoning_content`; none emitted a final
answer. Pinned llama.cpp documents budget 0 as an immediate end, so this violates
the predeclared mechanism contract.

| Budget | Stable score | Generated tokens | Reasoning characters | Total median |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0/30 | 8 median (8–8) | 25 median (25–51) | 2,152.8 ms |
| 16 | 13/30 | 21 median (19–24) | 56 median (51–98) | 3,306.7 ms |
| 32 | 11/30 | 40 median (35–40) | 124.5 median (89–165) | 4,677.9 ms |
| 48 | 7/30 | 56 median (51–56) | 187 median (129–237) | 5,980.7 ms |

The positive budgets did force an end and produce final answers in both
repetitions, but all missed the unchanged 75% floor. Budget 48 also exceeded
the five-second median application ceiling. These are diagnostic observations
from an invalid candidate matrix, not an accepted quality frontier.

## Root cause

Pinned tag `b10208` initializes the reasoning-budget sampler by accepting every
generation-prompt token as prefill. Qwen3.5's generation prompt ends with
`<think>` followed by a newline. At budget 0, matching `<think>` moves the
sampler into `FORCING`; accepting the trailing newline then advances
`force_pos` even though the newline is not the forced `</think>` token. With a
one-token end sequence, the state incorrectly becomes `DONE` before generation
begins.

The same unchecked transition remains at upstream `master` commit
`876a4321163249c43ca4e986818fab5ab081f282`. A new exact-source unit regression
fails on the untouched pinned tag with exit 134 at the expected state assertion.
Adding a guard that advances only when the accepted token equals the current
forced token makes the full upstream `test-reasoning-budget` target pass all 13
tests. This is local functional preflight, not yet a native or product claim.

## Decision

Preserve E3e as invalid mechanism evidence and do not weaken its validator. A
separately frozen source-correctness experiment must reproduce the baseline
failure, apply the exact reviewed patch, pass the complete upstream unit target,
and prove real zero-budget final answers on Arm before the fix is accepted.

The raw 90-day artifact is `e3e-reasoning-budget-30651144293-1`. Its independently
scored diagnostic quality summary has SHA-256
`ceebf82b195e941ae07334d71080db92c7476681f2c8fc3ff09604d351a48339`;
it is deliberately not retained as a deployable manifest.
