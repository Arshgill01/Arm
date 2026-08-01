# Measured service-tier planner

Pareto64 now converts the E5h Arm weight-repack boundary into a repeatable
deployment decision instead of leaving operators to copy a flag from a report.

## Inputs

- native manifest: `results/manifests/e5h-30672633366.json`
- manifest SHA-256:
  `e048f3e25d513430b49fd2ee0a140e8a0f82fe31d79b5fb0aafb36b470190faa`
- throughput policy: `configs/service-throughput.json`
- at-most-3-GiB policy: `configs/service-memory.json`

The source manifest must remain the selected schema-1 E5h result and prove
quality eligibility, zero request failures, both model-buffer mechanisms, and
consistent repack state. The planner rejects inconsistent or merely diagnostic
evidence.

## Decisions

| Envelope | Feasible profile | Runtime arguments | Retained plan |
| --- | --- | --- | --- |
| ≥0.9 req/s; median ≤1.5 s; p95 ≤2.5 s | `repack_on` | none | `results/plans/e5h-service-throughput.json` |
| RSS ≤3,145,728 KiB; ≥0.4 req/s | `repack_off` | `--no-weight-repack` | `results/plans/e5h-service-memory.json` |
| RSS ≤2,097,152 KiB | none | deployment refused | recomputed in tests |

Both measured profiles preserve every selected answer. Repack on reaches
0.9295 requests/s at 4,453,532 KiB maximum RSS. Repack off reaches 0.4505
requests/s at 2,381,264 KiB maximum RSS. Neither operating point is treated as
universally superior.

## Decision contract

The planner evaluates quality and every named SLO before Pareto filtering. It
then uses the policy's visible lexicographic priority and records
`weighted_score_used: false`. The output includes input hashes, observed
metrics, rejection reasons, feasible profiles, non-dominated frontier, selected
runtime state, and exact launcher arguments.

Recompute either retained decision with:

```bash
python3 -m pareto64 service-plan \
  --manifest results/manifests/e5h-30672633366.json \
  --constraints configs/service-memory.json
```
