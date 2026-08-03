# E19a composed cache certificate and shared Arm arena

Native GitHub Arm64 run
[`30859673434`](https://github.com/Arshgill01/Arm/actions/runs/30859673434)
passes every frozen quality, mechanism, service, memory, stability, startup, and
cleanup gate. The bounded composed tier is promoted.

## Result

Both policies used two simultaneous, prefix-affined workers mapping the same
verified 2.14 GB read-only Arm-packed sidecar. The only comparison variable was
request policy: all uncached versus E13b's exact 48-fingerprint certificate.

| Measure | All uncached | Certificate | Candidate/control |
|---|---:|---:|---:|
| Throughput | 0.3934 req/s | 0.7392 req/s | **1.8789x** |
| Median HTTP latency | 4,610.6 ms | 2,232.5 ms | **0.4842x** |
| p95 HTTP latency | 7,376.3 ms | 6,343.7 ms | **0.8600x** |
| CPU seconds/request | 9.9554 | 5.2927 | **0.5316x** |
| Summed PSS | 4,620,326 KiB | 4,620,324 KiB | **1.0000x** |
| Median two-worker readiness | 1,475.8 ms | 1,325.0 ms | 0.8979x |

The two certificate repetitions each made exactly 146 certified-cache decisions,
19 calibrated uncached fallbacks, and zero unknown fallbacks. Every measured
certified request reused cache tokens. Both repetitions matched the all-uncached
response bytes exactly; there were zero baseline-repeat, certificate-repeat, or
certificate-versus-baseline mismatches and zero request failures.

The simultaneous measurement-start skew was at most 0.146 ms. Throughput CV was
0.077% for the baseline and 0.366% for the controller, well inside the frozen 5%
gate. The same sidecar inode/mapping proof, 16-byte SVE vector length, source/model
hashes, and fail-closed identity were retained. Final verification passed and the
generated sidecar was deleted by the runner.

## Boundary

This is a compounded end-product result. It does not attribute the full gain to
either prompt caching, prefix affinity, or shared repacking in isolation; E13b
and E16c remain the causal evidence for those mechanisms. Promotion is limited
to the exact retained 48-fingerprint certificate, two workers, one trace, and
one four-core Neoverse N2 host. Unknown prefixes still route uncached.

The [machine-readable manifest](../manifests/e19a-30859673434.json) was reproduced
byte for byte from the 194-file workflow inventory and binds artifact
`e19a-composed-cache-arena-30859673434-1` (ID `8874428293`, digest
`sha256:233b45f5ad4f878a9abdb2f41fcceb88dbeabee8826d42aa7cf3f45403c0e0a2`).
