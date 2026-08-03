# E14b verbosity-corrected selective-repack frontier

Native Arm run
[`30834588144`](https://github.com/Arshgill01/Arm/actions/runs/30834588144)
validates the complete four-point frontier and rejects both selective candidates
on the unchanged product gate. All points preserve the exact selected answer
map and are non-dominated, but neither jointly retains 80% of full-repack
throughput while saving 40% of its additional RSS over no-repack. Full repack
remains selected and the experimental exclusion hook is not promoted.

## Measured frontier

| Configuration | Repack buffer | Median req/s | Full retention | p95 ms | CPU s/request | Max RSS KiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full repack | 2,038.92 MiB | 0.92055 | 100.00% | 1,874.81 | 4.29467 | 4,451,904 |
| Attention raw | 1,590.12 MiB | 0.71858 | 78.06% | 2,238.86 | 5.51167 | 3,992,508 |
| Attention + FFN-down raw | 1,104.75 MiB | 0.57589 | 62.56% | 2,714.97 | 6.88617 | 3,495,248 |
| No repack | 0 MiB | 0.44545 | 48.39% | 3,323.57 | 8.92117 | 2,377,140 |

Every configuration ran twice in A–B–C–D–D–C–B–A order with a fresh process.
All 240 measured requests succeeded, every repetition scored 23/30, every
prediction map was stable, and every throughput CV was below 0.433%. Explicit
verbosity 4 captured the required mechanism proof in all eight cells:

- full repack: 2,024.36 MiB mapped + 2,038.92 MiB repack;
- attention raw: 2,024.36 + 1,590.12 MiB;
- attention plus FFN-down raw: 2,024.36 + 1,104.75 MiB;
- no repack: 2,039.54 MiB mapped and no repack buffer.

The exact tensor-exclusion inventories are 104 and 130 tensors as frozen.

## Gate decision

All four points are non-dominated, so the frontier-existence gate passes. The
selective target does not:

- `attention_raw` retains 78.06% throughput and p95 is 1.1942x, but it saves
  only 22.14% of full repack's extra RSS;
- `attention_down_raw` saves 46.11% of the extra RSS, but retains 62.56%
  throughput and p95 is 1.4481x.

The result is technically useful: repacked bytes, process RSS, throughput,
latency, and CPU cost move monotonically across four stable operating points.
It also shows that this pair of architectural tensor groups does not create the
target product tier. We do not move the 80%/40% thresholds, pick a post-hoc
regex, or promote a merely non-dominated point.

E14a remains independently invalid because it omitted the mechanism log level.
E14b changed only uniform verbosity; its configurations, order, repetitions,
requests, and acceptance object are mechanically equal to E14a.

## Reproducibility

Artifact `e14b-selective-repack-30834588144-1` (ID `8864659786`, GitHub digest
`f145f863…b0b96`) retains the exact source and four-patch diff, toolchain and
build commands, binary/dependency closure, model hash, all recipes, raw probes,
process logs, buffer proof, and host capture. Independent local ingestion
reproduced the 60,241-byte workflow summary byte for byte at SHA-256
`752c5d93…87810`. All 152 runner-inventoried files were rehashed; the inventory
SHA-256 is `7ce3b13f…c7d5d`. The compact
[`manifest`](../manifests/e14b-30834588144.json) has SHA-256
`571e15d5…663c3b`.
