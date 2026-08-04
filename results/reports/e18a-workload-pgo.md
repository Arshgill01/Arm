# E18a workload-trained GCC PGO

Native GitHub Arm64 source run
[`30861416953`](https://github.com/Arshgill01/Arm/actions/runs/30861416953)
completed the exact patched b10216 OpenSSL-off comparison. Its workflow-level
ingester failed, so the source run remains invalid. Inspection-only recovery run
[`30865048163`](https://github.com/Arshgill01/Arm/actions/runs/30865048163)
then verified all 501 source-artifact files and replayed only the corrected
deterministic ingester. It did not rebuild, redownload the model, retrain, launch
the server, or repeat a measured request.

## Result

The 180-second training-only successor completed the exact 30-task pass and
produced 305 GCC `.gcda` files totaling 4,671,004 bytes. Both Release and PGO
then ran six reverse-balanced fresh-process repetitions and preserved the exact
23/30 selected predictions in every repetition with zero reference drift.

| Metric | Release control | Workload PGO | PGO / control |
| --- | ---: | ---: | ---: |
| Median throughput | 0.92302 req/s | 0.91603 req/s | **0.99243x** |
| Median HTTP latency | 1,060.91 ms | 1,069.63 ms | **1.00822x** |
| p95 HTTP latency | 1,871.65 ms | 1,866.37 ms | 0.99718x |
| Median CPU seconds/request | 4.28783 | 4.32017 | **1.00754x** |
| Median readiness | 2,635.82 ms | 2,484.65 ms | 0.94265x |
| Maximum RSS | 4,451,936 KiB | 4,451,700 KiB | 0.99995x |
| Runtime closure | 19,857,840 bytes | 21,225,056 bytes | **1.06885x** |

The PGO candidate missed throughput, median-latency, CPU/request, and closure
gates. Its small p95 and readiness improvements do not compensate for those
regressions under the frozen all-gates policy. Release remains selected; PGO is
not compounded with LTO or promoted.

## Evidence boundary

The [retained manifest](../manifests/e18a-30865048163.json) binds the exact
source run and artifact, failed-ingestion record, 501-file verification,
recovered summary SHA-256, recovery run/job/artifact, complete per-cell data,
binary closures, profile inventory, and unchanged decision gates. The compact
recovery artifact is
`e18a-ingestion-recovery-30865048163-1` (ID `8875767119`, digest
`sha256:6dc1e1f1d5b2d04db438e50d93e6101375591ed7dd5f06f40c201b035da68c83`).

This is a workload-specific GCC PGO no-win for one four-vCPU Neoverse-N2
runner, model, source revision, service, and prompt-heavy workload. It is not a
generic PGO, other-model, energy, PMU, local-device, fleet, or cost result.
