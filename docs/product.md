# Pareto64 product core

Pareto64 turns validated native Arm experiment manifests into an explicit,
quality-constrained deployment decision. The planner is standard-library Python
and has no network, model, or runtime dependency at decision time.

```text
validated E3/E3b/E3c manifest
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
  --manifest results/manifests/e3b-30643977955.json \
  --constraints configs/cloud-quality.json \
  --output results/plans/e3b-cloud-quality.json
```

Both real policy runs return `no_feasible_candidate`. E3 rejects Q4_0, Q4_K_M,
and MNN int4 at the frozen quality gate. E3b then rejects a larger 7B Q4_K_M
anchor at a stable 73.33%, one task short of the unchanged 75% floor; it also
records the candidate's small same-text latency and RSS SLO misses. Pareto64
does not allow any of those resource or quality near-misses to become a
deployment.

The same decision is available through the bounded HTTP service:

```bash
python3 -m pareto64 serve \
  --manifest results/manifests/e3b-30643977955.json \
  --constraints configs/cloud-quality.json \
  --host 127.0.0.1 \
  --port 8080
```

The service exposes `/healthz`, `GET /v1/plan`, `POST /v1/plan`, and `/metrics`.
Its default TCP accept backlog is 64, selected by frozen E4a native Arm evidence
after capacities 5, 16, and 64 were each evaluated in three cyclic rounds. The
`--backlog` option remains available for an explicit deployment override.

## Constraint contract

The schema-1 policy has two explicit parts:

- `requirements`: `at_least` for higher-is-better accuracy and `at_most` for
  lower-is-better latency, RSS, package size, and model-load time;
- `selection_priority`: a unique ordered list used only after quality, SLO, and
  Pareto filtering.

Every numeric metric must be finite and non-negative. Schema-1 E3, E3b, and E3c
quality-frontier manifests are accepted. Candidate sets, quality decisions,
experiment status, and the experiment's declared eligible set must agree or the
planner rejects the manifest. The output records hashes of both
input files, all observed metrics, all rejection reasons, the feasible set,
frontier, selected candidate, and the fact that no weighted score was used.

## Current boundary

This is the evidence-to-decision core and HTTP decision plane, not yet an
inference server. E5a validated its correctness, concurrency, latency, and RSS;
E4a then eliminated the observed admission tail under a stricter load. A runtime
launch adapter is intentionally deferred until a candidate passes the quality
gate; Pareto64 must not turn an invalid measurement into a deployment. E3b has
produced a valid empty frontier. E3c is therefore a separately frozen
quality-per-byte calibration over one newer non-thinking 4B model and three
quantization levels, not a relaxed policy.
