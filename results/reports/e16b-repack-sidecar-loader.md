# E16b fail-closed read-only repack-sidecar loader

Native Arm run
[`30842925537`](https://github.com/Arshgill01/Arm/actions/runs/30842925537)
passes every frozen identity, quality, mechanism, performance, stability and
cleanup gate. The exact E7c service may use the identity-bound sidecar loader
on the measured Neoverse N2 boundary. Its material benefit is same-job
readiness; the run shows no material RSS/PSS reduction.

## Exact comparison

Four normal-repack and four loader processes run in the frozen ABBA/BAAB order,
with 30 unchanged tasks per fresh process:

| Evidence | Normal repack | Sidecar loader | Loader / normal |
| --- | ---: | ---: | ---: |
| Correct / failures per repetition | 23/30, 0 | 23/30, 0 | exact |
| Median requests/s | 0.92993 | 0.93260 | 1.0029x |
| Median HTTP latency | 1,062.91 ms | 1,048.15 ms | 0.9861x |
| p95 HTTP latency | 1,864.25 ms | 1,855.39 ms | 0.9952x |
| Median CPU seconds/request | 4.25683 | 4.25117 | 0.9987x |
| Maximum RSS | 4,451,968 KiB | 4,450,056 KiB | 0.9996x |
| Median post-workload PSS | 4,449,111 KiB | 4,447,239 KiB | 0.9996x |
| Median readiness | 2,530.23 ms | 960.75 ms | **0.3797x** |

Every prediction is stable across all eight cells. Throughput CV is 0.6853%
for normal repacking and 0.1517% for the loader. The loader retains steady-state
throughput, latency and CPU/request, while median readiness is 62.03% lower and
clears the predeclared 0.80x material-benefit gate. Peak RSS and PSS remain
essentially unchanged and do not support a memory-saving claim.

## Mechanism and failure behavior

The one-time construction path serializes all 183 packed tensors into a
2,139,013,120-byte sidecar with SHA-256 `4add52d6…a6af`. Every loader process
rehashes the complete file, maps its arena `r--s` at offset `00100000`, validates
all GGUF-derived tensor layouts, and logs that it loaded all tensors without
runtime repacking. A deliberately incorrect source-model hash aborts with exit
134 before readiness.

Construction itself is not free: the instrumented construction server reaches
readiness in 4.340 seconds and the sidecar builder takes 6.24 seconds. Those
one-time operations are retained separately and excluded from steady-state
request metrics. The sidecar is reverified after all cells and deleted; no
model, raw tensor dump or deployable sidecar is uploaded or committed.

## Decision boundary

The loader is promoted only for the exact selected model, b10216 five-patch
source diff, Arm feature identity, 16-byte SVE vector length and single-process
service recipe exercised here. The job does not flush Linux page cache, so the
readiness result is an observed-cache same-job comparison, not cold-storage
startup. This run establishes neither multi-process physical sharing nor
cross-CPU portability, energy, construction break-even or memory reduction.

The earlier run `30841531260` remains invalid because its frozen ingester failed
after measurement. Its descriptive values showed the same readiness pattern,
but they are not used to promote E16b.

## Reproducibility

Independent local ingestion reproduces the 545,766-byte workflow summary byte
for byte at SHA-256 `6503f1de…ae1d`. All 189 runner-inventoried files were
rehashed; the inventory SHA-256 is `a7d0e43c…12d5`. Artifact
`e16b-repack-sidecar-loader-30842925537-1` (ID `8867796505`, digest
`acffa293…dddfb`) is bound to frozen commit `ec51891`. The retained
[`manifest`](../manifests/e16b-30842925537.json) has SHA-256
`fc5500c3…6ddc`.
