# E16b read-only repack-sidecar loader ingestion failure

Native Arm run
[`30841531260`](https://github.com/Arshgill01/Arm/actions/runs/30841531260)
completed its sidecar construction, fail-closed identity preflight, eight fresh
processes, 240 measured requests, final sidecar verification and cleanup. The
frozen ingester then raised `KeyError: 'cases'` before producing its summary or
runner inventory. E16b is therefore invalid and cannot promote the loader.

## Descriptive failed-run evidence

An independently hashed, diagnostic-only replay reads the raw cases from the
retained probe object—the intended location—while applying every other frozen
validation. All 240 requests reproduce 23/30 with zero failures or prediction
drift. All four loader processes prove an `r--s` mapping at offset `00100000`,
validate all 183 tensors without runtime repacking, and reject a deliberately
wrong model hash before readiness.

The following values are descriptive only because the frozen ingester failed:

| Evidence | Normal repack | Sidecar loader | Loader / normal |
| --- | ---: | ---: | ---: |
| Median requests/s | 0.92613 | 0.93084 | 1.0051x |
| Median HTTP latency | 1,063.25 ms | 1,057.79 ms | 0.9949x |
| p95 HTTP latency | 1,862.91 ms | 1,856.67 ms | 0.9966x |
| Median CPU seconds/request | 4.27283 | 4.25383 | 0.9956x |
| Maximum RSS | 4,449,612 KiB | 4,450,164 KiB | 1.0001x |
| Median post-workload PSS | 4,446,708 KiB | 4,447,248.5 KiB | 1.0001x |
| Median readiness | 2,475.96 ms | 911.70 ms | 0.3682x |

This trace suggests a material same-job readiness benefit with steady-state
performance retained, but no RSS/PSS reduction. It is not a cold-storage
measurement: the job deliberately does not flush the Linux page cache. The
one-time construction process reaches readiness in 6.358 seconds, writes a
2,139,013,120-byte sidecar in 6.10 seconds, and deletes the raw tensor dump
after verification. That cost remains separate from steady-state service.

## Exact failure and successor boundary

`validate_probe` deliberately returns a compact summary without raw cases.
`summarize_configuration` incorrectly indexed `probe["cases"]` instead of the
already retained and validated cell probe object. The exception occurs only
after every measured process and cleanup step completed.

A successor may make that one data-flow repair and regenerate the hash that
binds the ingester. It must repeat the native experiment
without changing the model, source/loader patch series, service flags, order,
repetitions, requests, mechanism checks or any acceptance threshold. This run
remains invalid regardless of the successor result.

## Reproducibility

Artifact `e16b-repack-sidecar-loader-30841531260-1` (ID `8867253168`, digest
`1ffde82b…37e35`) retains 188 regular files totaling 22,810,367 bytes; their
ordered extracted-file inventory hashes to `b73d6933…3482`. The compact
[`manifest`](../manifests/e16b-30841531260.json) hashes to
`5ef05b79…de07` and explicitly forbids promotion.
