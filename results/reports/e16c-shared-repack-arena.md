# E16c two-worker shared Arm repack arena

## Result

Native GitHub Arm64 run
[`30851609576`](https://github.com/Arshgill01/Arm/actions/runs/30851609576)
independently validated as `valid_shared_sidecar_workers_promoted`. Every frozen
gate passed.

The comparison launched two simultaneous workers per cell on one four-core
Neoverse N2 host. The baseline let both workers build private runtime repacks.
The candidate mapped the same verified 2,139,013,120-byte Arm-packed sidecar
read-only into both workers. Four reverse-balanced groups per configuration
produced 480 measured requests across 16 fresh server processes.

| Two-worker configuration | Median aggregate throughput | Median / p95 HTTP | Median CPU/request | Median group readiness | Median summed PSS | Median summed RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| normal runtime repack | 0.8699 req/s | 2,236.7 / 3,941.7 ms | 4.5073 s | 2,892.0 ms | 6,815,078 KiB | 8,904,516 KiB |
| shared read-only sidecar | 0.8703 req/s | 2,234.2 / 3,957.1 ms | 4.4997 s | 1,320.0 ms | 4,723,364 KiB | 8,900,774 KiB |

Candidate-to-baseline ratios were:

- aggregate throughput: **1.00044x**;
- median HTTP latency: **0.99889x**;
- p95 HTTP latency: **1.00389x**;
- server CPU seconds/request: **0.99832x**;
- group readiness: **0.45641x**;
- summed post-workload PSS: **0.69308x**.

The shared arena saved **2,091,714 KiB (1.995 GiB, 30.69%)** of summed PSS while
preserving throughput and all exact answers. Both workers proved the same
read-only device/inode mapping. Every worker reproduced 23/30 with zero request
failures or reference mismatches.

## Decision and boundary

Promote the exact identity-bound shared-sidecar configuration as a two-worker
deployment tier. It establishes real physical page sharing on this native Arm
host.

Do **not** claim lower per-process RSS. Summed RSS was nearly unchanged because
RSS counts a shared mapped page once in each process; PSS is the correct metric
for host physical-memory attribution. Sidecar construction was measured
separately (5.57 seconds for the builder process and 6.56 seconds to builder
readiness) and is not included in steady-state throughput. This same-job run is
not a cold-storage, cross-host portability, fleet, cost, energy, or PMU claim.

The final verifier reproduced sidecar SHA-256
`037a8697ad16ef8200a238d7005278ef15fe9db78b2200ca7517fa73fd649dc2`
and all 183 tensors before the 2,139,013,120-byte scratch sidecar was deleted.
No generated model or sidecar is retained in the uploaded artifact.

## Evidence

The retained [manifest](../manifests/e16c-30851609576.json) contains all eight
dual-worker groups, raw requests, process counters, mappings, PSS/RSS snapshots,
source/build provenance, verification, and cleanup evidence. Independent local
ingestion reproduced the workflow summary byte for byte at SHA-256
`b30088f378ea042b239fcd6ee5f61290fbb91aac9c839a2648bd2a908d189cf0`.
All 325 runner-inventoried files were rehashed.

The complete artifact is `e16c-shared-repack-arena-30851609576-1` (ID
`8871236545`, digest
`sha256:e29d3a4440dafd42364fb586f9d5f8adb2c6c69b3bd312a10ffd10761312db02`).
