# E20b repack-pair candidate assertion

Native GitHub Arm64 run
[`30867317408`](https://github.com/Arshgill01/Arm/actions/runs/30867317408)
built one exact patched b10216 binary and passed the frozen mechanism preflight.
The subsequent service comparison is invalid because the candidate process
aborted in its first cell.

## Result

The diagnostic pp512 preflight proved the intended transformation: the control
trace contained 52 separate FFN gate/up nodes and the candidate contained 26
gate nodes, each marked as fusing one following node. Both preflight processes
completed successfully. The first control service cell then reproduced 23/30
answers with zero reference drift at 0.9249 requests/s.

The first candidate service reached readiness and processed most of the
30-task probe before aborting with signal 6 at:

```text
GGML_ASSERT(nb1 <= nb2) failed
```

The native backtrace binds the assertion to `compute_forward_pair` through
`ggml_cpu_extra_compute_forward_pair`. The original graph predicate admitted a
later same-source pair whose output stride layout did not satisfy the repack
kernel's monotonic-stride invariant. No candidate probe file was written; ten
remaining frozen service cells were never attempted. Therefore there is no
valid candidate quality, throughput, latency, CPU, or memory result and the
patch is not safe for service.

A separately frozen successor may add only the missing fail-closed FFN identity
and output-layout predicates, then must repeat the mechanism proof before any
service measurement. That successor cannot reinterpret or rehabilitate E20b.

## Evidence boundary

The [retained failure manifest](../manifests/e20b-30867317408-failure.json)
binds the exact source, five-patch series, model, native host, one-binary build,
runtime closure, both preflight traces, completed control, candidate assertion,
artifact ID `8876719286`, artifact digest
`sha256:ca94b2f2c8ee831ceb68ba62c99b2c8cfe5d135dbc46c7526d5a0106c5f95c57`,
and the independently hashed 76-file artifact inventory. It makes no candidate
performance, energy, PMU, fleet, or cost claim.
