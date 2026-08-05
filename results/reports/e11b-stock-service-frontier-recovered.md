# E11b stock-quant service frontier: complete artifact recovery

Source native GitHub Arm64 run
[`30869286295`](https://github.com/Arshgill01/Arm/actions/runs/30869286295)
successfully built the exact E7c service, downloaded all five mechanically
selected stock candidates, and completed all 40 fresh-process measurement
cells. The workflow still concluded in failure because its validator passed
the `/slots` response to an object-only JSON loader even though the endpoint
returned the expected one-element array.

## Recovery boundary

The source run remains failed. The recovery adds no measurement, changes no
model, service flag, workload, order, quality coordinate, frontier rule, or
acceptance gate. It changes only the parser used for `slots.json` to require a
JSON array of slot objects; every other retained JSON path remains object-only.
The complete replay is pinned to Python 3.10.20, matching the source job. This
matters because later Python statistics implementations differ by the last bits
of the cached-token population standard deviation.

The corrected parser validates all 40 cells, 1,200 measured requests, raw
answers, process CPU windows, readiness, RSS, cache evidence, commands, source,
binary closure, and dependencies. All configurations have stable predictions,
zero request failures, throughput coefficient of variation below 0.05, and pass
the frozen validity gates.

## Recovered frontier

| Model | Exact 30-task score | Anchor mismatches | Size, GiB | Median req/s | Median HTTP, ms | p95 HTTP, ms | CPU s/request | Max RSS, GiB | Readiness, ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Q4_K_M anchor | 23/30 | 0 | 1.999 | 0.9283 | 1,056.6 | 1,863.5 | 4.2648 | 4.243 | 2,530.6 |
| Q3_K_S | 15/30 | 14 | 1.526 | 0.2662 | 3,709.9 | 6,314.1 | 14.9548 | 2.101 | 1,317.6 |
| Q3_K_M | 17/30 | 6 | 1.672 | 0.3660 | 2,696.6 | 4,620.9 | 10.8698 | 2.851 | 1,723.1 |
| IQ4_XS | 22/30 | 1 | 1.825 | 0.5161 | 1,899.0 | 3,312.1 | 7.7010 | 2.452 | 1,218.4 |
| IQ4_NL | 23/30 | 1 | 1.910 | 0.9130 | 1,070.8 | 1,896.6 | 4.3365 | 4.065 | 2,027.9 |
| Q5_K_M | 22/30 | 1 | 2.304 | 0.7359 | 1,344.1 | 2,261.7 | 5.3595 | 4.848 | 2,531.0 |

All six points remain non-dominated under E11b's deliberately strict
multi-coordinate policy. That is useful, but not a license to run five more
confirmation jobs: E11b makes no product promotion, and the terminal model-tier
decision remains deferred until the already completed E12b generated-quant
artifacts are independently recovered.

## Retained evidence

The [machine-readable manifest](../manifests/e11b-30869286295-recovered.json)
binds source commit `7cac67ce6ac836aa3d78a9aa3c28ccb5ae8eeaee`, failed job
`91867736992`, artifact ID `8878168248`, and artifact digest
`sha256:5761150e1f5bedad5206364a5bbed8b87429826922e47fe9fb4a57f1b7b90e3b`.
The recovery independently hashes all 566 artifact files; their canonical
inventory hashes to
`b6bde877b69aee4bb511c875f3a3db9c567a12fd5d1e01347d1c7138f004d484`.

The evidence applies only to the exact frozen candidates, E7c service,
30-task workload, external quality coordinates, and native Neoverse N2 runner.
It makes no energy, PMU, local-device, mixed-quant, imatrix, pruning,
other-runtime, fleet, or cost claim.
