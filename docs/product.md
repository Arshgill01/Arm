# Pareto64 product core

Pareto64 turns validated native Arm experiment manifests into an explicit,
quality-constrained deployment decision. The planner is standard-library Python
and has no network, model, or runtime dependency at decision time.

```text
validated E3/E3b/E3c/E3d/E3e/E3f manifest
        │
        ▼
evidence consistency checks ──reject──► invalid input
        │
        ▼
predeclared quality gate ──────reject──► recorded reason
        │
        ▼
named SLO requirements ────────reject──► recorded reason
        │
        ▼
recomputed Pareto frontier
        │
        ▼
explicit lexicographic priority ───────► deployment plan
```

No weighted score is used. A candidate can enter the frontier only after the
source experiment declares it quality-eligible and it passes every named SLO.
The planner then removes only dominated candidates and chooses from the remaining
frontier using the user-visible priority order.

## Run the current plan

```bash
python3 -m pareto64 plan \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json \
  --output results/plans/e3f-cloud-quality.json
```

The retained E3 through E3e policy runs return `no_feasible_candidate`. E3
rejects Q4_0, Q4_K_M, and MNN int4 at the frozen quality gate. E3b then rejects a
larger 7B Q4_K_M anchor at a stable 73.33%, one task short of the unchanged 75%
floor. E3c rejects Qwen3-4B Q4_K_M, Q5_K_M, and Q8_0 at stable accuracies from
60.00% to 66.67%; Q8_0 also misses the load and RSS ceilings. Pareto64 does not
allow any resource or quality near-miss to become a deployment.

E3f is the first selected plan. Ministral 3 3B Q4_K_M reached a stable 76.67%
and passed the frozen latency, RSS, package, and load ceilings. The smaller,
faster Q4_0/KleidiAI path remained rejected at 70.00%, so the selected result
preserves the same quality-first behavior.

The same decision is available through the bounded HTTP service:

```bash
python3 -m pareto64 serve \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json \
  --host 127.0.0.1 \
  --port 8080
```

The service exposes `/healthz`, `GET /v1/plan`, `POST /v1/plan`, and `/metrics`.
Its default TCP accept backlog is 64, selected by frozen E4a native Arm evidence
after capacities 5, 16, and 64 were each evaluated in three cyclic rounds. The
`--backlog` option remains available for an explicit deployment override.

## Launch the selected inference runtime

The launch adapter recomputes the plan, refuses an empty frontier, verifies the
selected model's exact size and SHA-256, checks catalog/source revisions and the
pinned llama.cpp commit, and writes a hashed launch recipe before replacing
itself with `llama-server`:

```bash
python3 -m pareto64 launch \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json \
  --models experiments/e3f_models.json \
  --contract experiments/e3f_contract.json \
  --model-root /path/to/models \
  --llama-server /path/to/llama-server \
  --recipe-output /tmp/pareto64-launch.json \
  --parallel 1
```

The adapter preserves the measured four-thread deterministic serving
configuration and defaults to the E5e-selected 256-token context per slot.
Increasing `--parallel` increases total context proportionally so each slot
retains that allocation. `--context-per-slot` remains an explicit bounded
override for a separately validated workload profile.
`--batch-size` and `--micro-batch-size` are a bounded pair that default to the
E5f-selected 64/64 profile. Both requested and effective values are written to
the hashed recipe. Explicit paired overrides reproduce larger profiles when a
different workload has passed its own application-level quality gate.
Weight repacking remains enabled by default. `--no-weight-repack` is a bounded
escape hatch that records `weight_repack: false` in the recipe and passes the
pinned runtime's `--no-repack` flag; E5h is the frozen quality, memory, and
performance boundary for treating that path as a separate memory tier.
`--dry-run` performs every integrity and selection check and writes the recipe
without starting the server.

Prompt-prefix reuse is enabled by default after E5c reproduced every selected
answer and improved repeated median throughput 1.672x. The pinned llama.cpp
runtime warns that cache-dependent prompt batch sizes can alter logits, so the
hashed recipe records the mode and `--no-prompt-cache` remains available for
workloads that have not passed an equivalent application-level correctness
gate.

E5b validated the full launch path on native Arm with zero answer drift across
120 measured requests. Its two-slot candidate improved repeated median
throughput by only 1.89%, below the frozen 10% minimum, while pooled median
latency rose from 1.81 to 3.57 seconds. The default remains one slot; `--parallel`
is an explicit deployment override, not a promoted optimization.

E5c kept one slot and changed only shared-prefix caching. All 120 answers again
matched the selected evidence, while throughput rose from 0.5378 to 0.8991
requests/s and pooled median latency fell from 1.807 to 1.062 seconds. Unlike
the two-slot candidate, prompt caching cleared both frozen 1.10x performance
gates and is promoted.

E5d then tested whether the promoted cache makes two-slot serving worthwhile.
All 120 answers remained exact and both slots demonstrated prefix reuse, but
throughput improved only 1.0619x while pooled median latency rose 93.3% and
maximum RSS increased 244,524 KiB. The cross-layer candidate missed the same
1.10x gate, confirming cached single-slot serving as the default.

E5e profiled 2,048/256-token contexts against f16, q8_0, and q4_0 K caches while
holding the selected model, f16 V cache, request set, and serving path fixed.
The 256-token f16 profile preserved all selected predictions, retained 99.62%
of baseline throughput, and reduced maximum RSS by 187,760 KiB. q8_0 also met
every gate, but the precision-first selector kept f16. q4_0 reproducibly changed
one correct answer, so it was excluded. The 256-token f16 profile is promoted.

E5f held that selected service fixed and profiled effective prompt batches of
256/256, 128/128, and 64/64. Only 64/64 passed every gate: it preserved all 60
selected predictions, reduced the CPU compute buffer 40.13→10.03 MiB, lowered
maximum RSS by 14,824 KiB, and retained 1.0226x throughput. It is selected for
promotion and is now the launcher default; 128/128 missed the process-RSS gate.

E5g tested the next batch floor without changing that default. Batch 32 reduced
the reported compute buffer from 10.03 to 5.02 MiB and preserved every selected
prediction, 1.0116x throughput, and both latency gates. Conservative maximum
RSS increased by 660 KiB, however, so it failed the frozen 4 MiB process-memory
gate. Pareto64 retains 64/64 and, per the staged contract, does not test 16/16.

## Constraint contract

The schema-1 policy has two explicit parts:

- `requirements`: `at_least` for higher-is-better accuracy and `at_most` for
  lower-is-better latency, RSS, package size, and model-load time;
- `selection_priority`: a unique ordered list used only after quality, SLO, and
  Pareto filtering.

Every numeric metric must be finite and non-negative. Schema-1 E3, E3b, E3c,
E3d, E3e, and E3f quality-frontier manifests are accepted. Candidate sets, quality
decisions, experiment status, and the experiment's declared eligible set must
agree or the planner rejects the manifest. The output records hashes of both
input files, all observed metrics, all rejection reasons, the feasible set,
frontier, selected candidate, and the fact that no weighted score was used.

## Current boundary

The evidence-to-decision core, HTTP decision plane, and selected-runtime launch
adapter are implemented. E5a validated planner correctness, concurrency,
latency, and RSS; E4a then eliminated the observed admission tail under a
stricter load. The adapter remained locked until E3f passed the quality gate, so
Pareto64 cannot turn an invalid measurement into a deployment. E3b, E3c, and
E3d all produced valid empty frontiers. E3d's current-runtime Qwen3.5
candidates both reached a stable 66.67%. E3e was rejected before frontier
creation because budget 0 violated the runtime's documented immediate-end
mechanism. E6c subsequently validated the exact source correction and zero
reasoning output on native Arm, but failed its frozen eight-token standalone
final-answer obligation; it creates no deployable candidate.

E3f now selects Ministral 3 3B Q4_K_M after a stable 76.67% result and clean
resource SLOs. E5b is the frozen native Arm gate for the launch adapter and
two-slot inference service. The service passed every quality and resource gate,
but two slots missed the throughput-improvement threshold, so inference serving
is validated while the single-slot default is retained. E5c subsequently
validated quality-preserving shared-prefix caching at 1.672x throughput and
promoted it within that single-slot default. E5d separately tested their
interaction and rejected cached two-slot serving at only 1.0619x throughput.
E5e then selected a 256-token f16 context, saving 183.36 MiB maximum RSS without
answer drift or material performance loss.
