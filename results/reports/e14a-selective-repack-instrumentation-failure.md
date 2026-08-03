# E14a selective-repack instrumentation failure

Native Arm run
[`30832494881`](https://github.com/Arshgill01/Arm/actions/runs/30832494881)
completed the frozen eight-process, 240-request matrix, but it is not a valid
frontier result. The recipes used llama.cpp's default log verbosity 3 while the
frozen ingester required model-buffer and excluded-tensor proof emitted at
verbosity 4. The ingester stopped on the first missing
`CPU_Mapped model buffer size` line. E14a is retained as an instrumentation
failure and cannot select or promote a configuration.

## What completed

All four configurations ran twice in the frozen A–B–C–D–D–C–B–A order on
native `aarch64`. All 240 measured requests returned successfully. Every
repetition reproduced the selected Q4_K_M model's exact 23/30 answer map with
zero reference-prediction mismatches.

The following values are descriptive failed-run measurements only:

| Configuration | Median req/s | Full-repack retention | p95 HTTP ms | CPU s/request | Max RSS KiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full repack | 0.92702 | 100.00% | 1,860.69 | 4.26867 | 4,452,096 |
| Attention raw | 0.72687 | 78.41% | 2,230.91 | 5.45683 | 3,992,364 |
| Attention + FFN-down raw | 0.58279 | 62.87% | 2,681.54 | 6.80883 | 3,495,400 |
| No repack | 0.44969 | 48.51% | 3,311.57 | 8.83883 | 2,379,592 |

The measurements expose a smooth memory/throughput tradeoff, but neither
selective point would meet both frozen product targets even if mechanism proof
had been present. Attention-raw retains 78.41% throughput and saves 22.18% of
full repack's additional RSS over no-repack, missing the 80% and 40% floors.
Attention-plus-FFN-down saves 46.16% but retains only 62.87% throughput and its
p95 is 1.441x full repack, above the 1.25x ceiling. These calculations do not
rehabilitate the invalid run or replace the missing mechanism evidence.

## Exact blocker and successor boundary

Every cell lacks all three frozen mechanism-log classes: mapped buffer, repack
buffer, and tensor-exclusion lines. The direct recipes contain no
`--log-verbosity` argument, and the captured server reports its default as 3.
The earlier E5h mechanism experiment demonstrates that verbosity 4 is required
for these proof lines.

A separately frozen successor may add exactly `--log-verbosity 4` to every
cell. It must keep the four configurations, model, source patch, service flags,
order, two repetitions, 240 requests, quality checks, and every acceptance
threshold unchanged. E14a remains invalid regardless of the successor result.

## Reproducibility

Artifact `e14a-selective-repack-30832494881-1` (ID `8863831383`, GitHub digest
`bc0f051b…b4a55`) retains the contract, source diff and four patches, toolchain,
build commands, binary/runtime closure, exact model hash, host capture, all
eight recipes, process logs, probes, readiness, metrics, and slot state. The
extracted artifact contains 151 regular files totaling 21,098,986 bytes; their
ordered SHA-256 inventory digest is `b757abb1…1b9e`. The compact
[`manifest`](../manifests/e14a-30832494881.json) records the descriptive values
and forbids a promotion decision.
