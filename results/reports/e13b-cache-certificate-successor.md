# E13b calibration-known cache-certificate successor

Native Arm run
[`30833985784`](https://github.com/Arshgill01/Arm/actions/runs/30833985784)
passes every separately frozen gate. On the reversed 165-request temporal trace,
the exact-fingerprint controller reproduces every all-uncached response byte,
routes 146 requests through certified caching, routes 19 through calibrated
uncached fallback, and encounters no unknown fingerprint. The policy is admitted
only for this retained certificate and workload boundary.

## Result

| Metric | All uncached | Certificate | Ratio |
| --- | ---: | ---: | ---: |
| Aggregate throughput | 0.42323 req/s | 0.78364 req/s | **1.85158x** |
| Median HTTP latency | 2,198.79 ms | 1,088.65 ms | 0.49512x |
| p95 HTTP latency | 3,340.46 ms | 3,154.30 ms | **0.94427x** |
| Server CPU/request | 9.38197 s | 5.06003 s | **0.53934x** |
| Maximum RSS | 4,529,320 KiB | 4,529,268 KiB | −52 KiB |
| Requests / failures | 330 / 0 | 330 / 0 | exact |

Both baseline repetitions and both controller repetitions are internally
byte-identical. The controller-versus-uncached comparison also has zero byte
mismatches. Throughput CV is 0.0218% for all-uncached and 0.0917% for the
certificate. Readiness is 2,528.40 ms versus 2,426.38 ms. All frozen quality,
mechanism, decision-count, native-architecture, throughput, p95, CPU, startup,
RSS, stability, and failure gates pass.

## Why this is distinct from rejected E13a

E13a remains rejected. Its contract guessed that six point-transition warmups
would be certified even though their exact fingerprints were absent from the
retained calibration set. The fail-closed runtime correctly sent them through
unknown fallback, violating E13a's frozen count.

E13b did not edit that result or threshold. Before observing E13b, it froze a
new reversed temporal sequence whose 165 prompt hashes and decisions were all
mechanically derived from E9c calibration records. Transition warmups duplicate
calibration-known requests. The acceptance object—including the 1.70x
throughput floor, p95 and CPU non-regression, exact-output and zero-failure
requirements—was copied unchanged. Both controller traces then produced the
predeclared 146 certified, 19 calibrated-fallback, and zero unknown decisions.

The measured fallback rate is 11.515%. Any prompt fingerprint not in the 44
certified or four fallback entries still fails closed to uncached execution.
This is not a semantic classifier or a universal prompt-cache safety claim.

## Reproducibility

Artifact `e13b-cache-certificate-30833985784-1` (ID `8864695008`, GitHub digest
`81c00b49…752b8`) retains the exact E9c binary and dependency closure,
calibration inputs, frozen 165-request fingerprints, direct recipes, host state,
all 660 raw request records, process counters, logs, and runner summary.
Independent local ingestion reproduced the workflow summary byte for byte at
SHA-256 `5b8d9ce8…5b984`. All 87 runner-inventoried files were rehashed; the
inventory SHA-256 is `b3e2fb1c…07955`. The compact
[`manifest`](../manifests/e13b-30833985784.json) has SHA-256
`570b8deb…02a19`.
