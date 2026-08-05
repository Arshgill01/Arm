# E12b generated-quant quality frontier: independent artifact aggregation

Native GitHub Arm64 source run
[`30869536393`](https://github.com/Arshgill01/Arm/actions/runs/30869536393)
completed all nine generated-quant jobs successfully. The aggregate job failed
before ingestion because recursive discovery selected both each artifact's root
cell `summary.json` and its nested retained `e12a/summary.json`: 18 files failed
the exact-nine assertion.

## Recovery boundary

The source workflow remains failed. Recovery selects exactly one root summary
from each expected artifact directory, verifies that summary through the
workflow's file inventory, and independently reruns the unchanged aggregate
function. It excludes exactly nine nested E12a prerequisite summaries. No model
is regenerated, no scorer is rerun, no native measurement is added, and no
recipe, task, sample, metric, dominance rule, or gate changes.

All nine source cell jobs report zero failures across 14,374 token-score
requests each. The recovery verifies 130,473 workflow-inventoried files,
including all 129,366 compressed raw responses, against the nine GitHub
artifacts.

## Generated results

| Generated recipe | Size, GiB | ARC Easy norm | HellaSwag norm | WinoGrande | Readiness, ms | Peak RSS, GiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q3_K_M control | 1.672 | 0.55 | 0.68 | 0.62 | 1,626.3 | 5.548 |
| Q3_K_M + imatrix | 1.672 | 0.59 | 0.71 | 0.61 | 1,621.0 | 5.548 |
| IQ4_XS control | 1.837 | 0.62 | 0.70 | 0.63 | 1,215.6 | 5.216 |
| IQ4_XS + imatrix | 1.825 | 0.55 | 0.71 | 0.56 | 1,115.1 | 5.149 |
| Q4_K_S control | 1.912 | 0.58 | 0.67 | 0.62 | 2,434.2 | 6.766 |
| Q4_K_S + imatrix | 1.912 | 0.61 | 0.71 | 0.61 | 2,328.1 | 6.766 |
| Q3_K_M + output/embed Q6 | 1.672 | 0.59 | 0.71 | 0.61 | 1,933.9 | 5.548 |
| IQ4_XS + V/down Q5 | 1.932 | 0.59 | 0.73 | 0.60 | 1,521.3 | 5.727 |
| Q4_K_S + edge layers Q6 | 2.024 | 0.62 | 0.70 | 0.64 | 2,430.6 | 6.983 |

The matched imatrix effects are mixed:

- Q3_K_M changes ARC/Hella/Wino by `+0.04/+0.03/-0.01` for 320 more bytes.
- Q4_K_S changes them by `+0.03/+0.04/-0.01` for 320 more bytes.
- IQ4_XS changes them by `-0.07/+0.01/-0.07` while saving 13,270,720 bytes.

The output/embed Q6 recipe exactly matches Q3_K_M imatrix's three quality
coordinates while being 32 bytes larger, so it is dominated. The combined
stock-plus-generated quality/size frontier retains 11 points. This is a useful
exploratory map, not a deployment decision: E12b has no matched service
throughput, latency, or CPU evidence and cannot promote a model.

## Retained evidence

The [machine-readable manifest](../manifests/e12b-30869536393-recovered.json)
binds source commit `3ab529e82e9a981857be3ebe108c58a774c65581`, failed
aggregate job `91905283851`, all nine successful cell job IDs, artifact IDs,
sizes, digests and expirations, per-cell inventories, raw results, and the
independent aggregate. The manifest hashes to
`5101132b071098b6bfb5368f41159b8c80256383fcc728c360d0e82afe3cec44`.

The result applies only to these nine exact b10216-generated recipes and the
pinned 300-sample external workload. It makes no service, energy, PMU,
local-device, fleet, cost, pruning, causal-kernel, or other-runtime claim.
