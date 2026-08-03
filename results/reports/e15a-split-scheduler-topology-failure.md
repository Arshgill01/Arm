# E15a asymmetric scheduler: retained topology failure

Status: **invalid native runner topology mismatch; no promotion**

GitHub run: [30849270574](https://github.com/Arshgill01/Arm/actions/runs/30849270574)

Artifact: `e15a-split-scheduler-30849270574-1` (ID `8870310205`)

Artifact digest: `sha256:6eb27a160f1d16135de752a0c1432f6591c298a62592f07def7bd15a81dd3948`

## What happened

The frozen E15a contract required the exact two-logical-CPU Neoverse-N2 topology
recorded by E9a. The native `ubuntu-24.04-arm` job instead exposed four logical
Neoverse-N2 CPUs. The workflow correctly rejected the result at independent
validation with `E15a native runner topology differs`.

This was not a measurement crash. All 16 fresh server processes completed all
480 measured requests before validation. The retention validator rechecked the
exact runtime closure, model, recipes, raw cases, CPU counters, cache evidence,
process evidence, and all 224 artifact files. Every configuration reproduced the
exact selected 23/30 answer map in every repetition with zero request failures
and zero reference-prediction mismatches.

## Descriptive results on the unfrozen four-CPU topology

These values are preserved to prevent cherry-picking, but they are not eligible
for promotion or a confirmatory claim.

| Configuration | Decode/batch threads | Throughput (median req/s) | Throughput ratio | Median latency ratio | p95 ratio | CPU/request ratio | Original gates |
|---|---:|---:|---:|---:|---:|---:|---|
| `tied4_4` | 4/4 | 0.9317 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | baseline |
| `split2_4` | 2/4 | 0.8811 | 0.9457 | 1.0625 | 1.0280 | 0.9958 | fail |
| `split1_4` | 1/4 | 0.8016 | 0.8604 | 1.1560 | 1.0869 | 0.9927 | fail |
| `prefill_control4_2` | 4/2 | 0.4895 | 0.5254 | 1.9097 | 1.9325 | 0.9904 | non-promotable control |

Neither promotable split reduced CPU seconds per request by the frozen two
percent, and both lost more than the allowed two percent throughput and latency.
The prefill-reduced control reproduced the expected large service regression.

## Decision

- Do not change the E15a topology gate after observation.
- Do not promote any scheduler configuration from this run.
- Preserve the complete raw artifact and failure manifest.
- A separately frozen successor may enforce a two-CPU process affinity on a
  native runner with at least two CPUs. It must retain the same performance and
  quality gates and disclose that the invalid four-CPU result was already seen.

## Claim boundary

The run establishes only that the complete E15a workload executed on an
unfrozen four-CPU GitHub-hosted Arm64 topology and was correctly rejected. It is
not evidence for a two-core scheduler promotion, energy, PMU, cost, or local
device behavior.
