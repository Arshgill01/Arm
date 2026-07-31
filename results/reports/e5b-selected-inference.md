# E5b selected inference serving

E5b validates Pareto64's end-to-end selected-model launch path on native Arm.
It also tests whether two continuous-batching slots materially improve
throughput over the single-slot default without changing quality.

## Result

Clean run
[`30659829983`](https://github.com/Arshgill01/Arm/actions/runs/30659829983)
passed the workflow and independent ingester end to end in 10m38s. The result is
`valid_selected_inference_no_concurrency_win`: inference serving is validated,
but the two-slot optimization is not promoted.

All four fresh-server cells recomputed the selected plan, verified the exact
2,146,497,824-byte Q4_K_M package at SHA-256
`fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4`,
checked llama.cpp commit `9d9a6d29f`, and emitted a hashed launch recipe. The
unmeasured verbose runtime probe observed both `CPU_REPACK` and `CPU_Mapped`
model buffers.

Every one of the 120 measured requests returned HTTP 200, terminated by
`stop`, contained an exact standalone A-D letter, and matched the selected E3f
prediction for its task. Every cell therefore reproduced 23/30 (76.67%) with
zero failures or prediction mismatches.

| Metric | Baseline: 1 slot/client | Concurrent: 2 slots/clients |
| --- | ---: | ---: |
| Repeated median throughput | 0.5371 req/s | 0.5472 req/s |
| Throughput ratio | 1.0000x | 1.0189x |
| Pooled median HTTP latency | 1,813.6 ms | 3,571.6 ms |
| Pooled p95 HTTP latency | 2,650.0 ms | 4,564.3 ms |
| Median deployment readiness | 3,952.3 ms | 3,989.3 ms |
| Maximum process RSS | 4,649,448 KiB | 4,901,032 KiB |

Both configurations passed the 5-second median, 10-second p95, 15-second
readiness, and 8 GiB RSS ceilings. The two-slot throughput ratio missed the
predeclared 1.10x minimum, however, and nearly doubled per-request latency. The
four-core host is already compute-saturated by the quality-selected Q4_K_M
prompt path; overlapping two requests mostly divides the same compute rather
than creating useful batch efficiency.

Pareto64 therefore retains one slot as the deployment default. The service
claim is allowed; a two-slot optimization claim is not.

## Mechanical first attempt

Run `30659025892` completed the same four measured cells, with the same stable
quality and a similar 1.0186x throughput ratio, but its post-processor expected
INFO-level model-buffer records in default-level server logs. Those records are
only emitted by the verbose runtime path. The correction added the same
unmeasured `llama-bench --verbose` proof already used by E3f and taught the
ingester to retain a valid negative hypothesis result. It did not change the
contract, measured commands, execution order, or 1.10x gate.

## Reproduction

The retained manifest is
[`e5b-30659829983.json`](../manifests/e5b-30659829983.json). Independent Python
3.10 ingestion reproduced the uploaded summary byte for byte at SHA-256
`aa529b16094ab398bf1d7c6aa698b452eeea6217f8016c280a5f2b6f947bf66c`.
