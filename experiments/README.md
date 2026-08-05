# Experiment evidence contract

Every measured run must preserve enough information to reproduce and challenge
the claim.

## Required record

- experiment ID, timestamp, operator, and git commit;
- hypothesis and the single primary change being tested;
- exact command and configuration;
- host/device, architecture, CPU features, core count, RAM, operating system,
  governor/power mode, runtime/compiler versions, and relevant environment;
- model, weights hash, dataset/input manifest, prompt/workload, and seed;
- warm-up policy, sample count, concurrency, and timing method;
- raw per-sample measurements, not only an average;
- correctness/quality result and acceptance threshold;
- peak/resident memory and artifact size where relevant;
- baseline link and derived absolute/relative delta;
- status: proposed, running, valid, invalid, superseded, or failed;
- confounders, anomalies, and follow-up decision.

## Statistical minimum

Use warm-ups plus repeated trials. Report median and tail behavior (normally p95)
for latency, and report dispersion. Do not compare two runs made under materially
different resource or thermal conditions without flagging the mismatch.

## Optimization rule

A speed, size, memory, energy, or cost win is not accepted if it violates the
defined correctness/quality floor. Approximate techniques must state the quality
trade explicitly.

## Architecture rule

x86_64 runs are useful for harness development and functional screening. They
are not proof of an Arm improvement. Final performance claims require an Arm
device or Arm64 cloud environment and a recorded architecture check.

## Expensive native experiment readiness

Before dispatching a new performance matrix on `ubuntu-24.04-arm`, validate its
frozen lane plan with
[`evidence_readiness.py`](evidence_readiness.py) and the versioned
[`evidence_readiness_policy.json`](evidence_readiness_policy.json). The required
order is mechanism/unit proof, a complete byte-stable synthetic replay, one
native control/candidate preflight, and only then a matrix. The plan must freeze
the affected runtime share, Amdahl ceiling, minimum product-changing result,
claim boundary, and runtime/storage budget. A lane whose system-throughput
ceiling is below 3% stops unless it predeclared a distinct novelty, memory,
quality, or deployability value.

The local artifact-shape fixture covers the documented `/slots` array, missing,
null and unsupported timing values, complete/failed/partial cells, raw JSON
request inventories, and independent byte-stable replay:

```bash
python3 experiments/evidence_readiness.py --self-test
python3 -m unittest tests.test_evidence_readiness
```
