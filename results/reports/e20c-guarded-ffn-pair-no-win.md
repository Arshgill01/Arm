# E20c guarded FFN pair reuse: safety success, performance no-win

Native GitHub Arm64 run
[`30870229218`](https://github.com/Arshgill01/Arm/actions/runs/30870229218)
retested E20b's FFN gate/up activation-repack reuse after adding the exact-name
and monotonic-output-stride guards required by E20b's assertion. The safety
repair is valid, but the candidate does not clear the frozen performance gates
and is not promoted.

## What was tested

One patched b10216 OpenSSL-off binary exposed a default-off runtime toggle. A
diagnostic pp512 preflight verified 52 separate control nodes versus 26 fused
candidate pairs. The candidate then completed a full 30-task safety preflight
before any service measurement. Twelve fresh processes ran in reverse-balanced
order: six `reuse_off` and six `reuse_on` cells, each serving the unchanged
30-task Q4_K_M workload. Diagnostic timing was disabled during measurement.

## Result

| Metric | `reuse_off` | `reuse_on` | Candidate ratio | Frozen gate | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Exact quality | 23/30 in every repetition | 23/30 in every repetition | no drift | exact match | pass |
| Request failures | 0/180 | 0/180 | — | zero | pass |
| Throughput, median req/s | 0.935294 | 0.937739 | 1.002614x | at least 1.02x | **fail** |
| HTTP latency, median ms | 1,043.860 | 1,042.015 | 0.998233x | at most 0.99x | **fail** |
| HTTP latency, pooled p95 ms | 1,848.698 | 1,844.842 | 0.997914x | at most 1.00x | pass |
| CPU seconds/request, median | 4.236 | 4.225 | 0.997403x | at most 0.99x | **fail** |
| Readiness, median ms | 2,427.534 | 2,426.500 | 0.999574x | at most 1.02x | pass |
| Maximum RSS, KiB | 4,449,500 | 4,449,644 | 1.000032x | at most 1.01x | pass |

The candidate throughput coefficient of variation is 0.000818, so the small
positive direction is visible but far below the predeclared product threshold.
There is no optimization win to promote. Pareto64 retains `reuse_off`, closes
the FFN pair-fusion lane, and does not reinterpret E20b's failed service run.

## Evidence boundary

The [retained manifest](../manifests/e20c-30870229218.json) binds commit
`10dc5b02630e3950e5850da7db67d28c8cb68b83`, the exact six-patch source series,
model and workload, native Neoverse N2 host, build command, binary and transitive
dependency closure, raw cells, and the 195-file artifact inventory. Independent
ingestion reproduced the workflow summary byte for byte at SHA-256
`3a0a0d4af371a4336f493cabf754d824ac742d72030fcfb2f1846a8bf17b3734`.
The bound artifact is ID `8877825372`, digest
`sha256:22175f3be8da0c3009e9573a0a7385cf4ea9acec7343a4486ebd8d4f01f62fbb`.

This result applies only to the exact Q4_K_M b10216 service and runner. It makes
no other-model, other-backend, long-context, energy, PMU, fleet, or cost claim.
