# E22c repeated Axion maximum-density comparison

## Decision

**Retain the repeated steady-state fixed-memory result, but do not promote the
full all-lifecycle claim.** Four order-balanced repetitions of normal-6 and
shared-8 passed every validity, correctness, throughput, p95, density, memory,
mapping, PMU, and dispersion gate. The only failed advance gate was readiness:
the median paired shared/normal readiness ratio was 2.0817x versus the frozen
maximum of 2.0x. The gate is not relaxed after the result.

The narrower result is strong and repeatable: on one 16,723,460,096-byte Google
Axion node, shared-8 delivered a median paired **1.3525x** the aggregate exact
inference throughput of normal-6. Every pair was at least 1.3457x. Shared p95
was 0.9780x control, per-worker throughput was 1.0144x, and throughput per GiB
of summed PSS was 3.3345x. These are warm same-host steady-state results, not an
all-lifecycle deployment win.

## Repetitions

The frozen `N6/S8/S8/N6/S8/N6/N6/S8` order gives both modes two first-in-pair
runs and places each mode twice in each half. Every normal cell completed 180
measured requests; every shared cell completed 240. All 1,680 requests
succeeded, reproduced the retained response map, and counted every frozen PMU
event.

| Repetition | Order | Normal-6 req/s | Shared-8 req/s | Shared/normal req/s | Shared/normal p95 | Shared/normal readiness | Throughput/GiB ratio |
| ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | N then S | 1.9899 | 2.6779 | 1.3457x | 0.9849x | 1.3456x | 3.3194x |
| 2 | S then N | 1.9904 | 2.7023 | 1.3577x | 0.9803x | 1.2250x | 3.3439x |
| 3 | S then N | 1.9827 | 2.6886 | 1.3560x | 0.9669x | 4.0925x | 3.3381x |
| 4 | N then S | 1.9894 | 2.6838 | 1.3491x | 0.9756x | 2.8177x | 3.3309x |
| **Median paired ratio** |  |  |  | **1.3525x** | **0.9780x** | **2.0817x** | **3.3345x** |

Normal throughput had a 0.1577% coefficient of variation; shared throughput had
a 0.3344% coefficient of variation. The paired throughput ratio's coefficient
of variation was 0.3628%. The repeated result is not driven by one favorable
cell or order.

Median summed PSS was 15,727,791 KiB for normal-6 and 6,380,921.5 KiB for
shared-8. The candidate therefore served two additional workers while using
9,346,869.5 KiB, or 59.43%, less summed PSS. Median post-workload
`MemAvailable` was 1,632,493,568 bytes for normal and 13,855,219,712 bytes for
shared. Every cell remained above the frozen 512 MiB reserve with zero OOM and
zero swap.

## Readiness boundary

Shared readiness was bimodal. It was 5.11 seconds when a shared cell immediately
followed another shared cell, but about 17 seconds in three other positions.
Normal readiness ranged from 4.13 to 12.79 seconds. The repeated median paired
ratio exceeded the contract by 4.08%, so Pareto64 does not claim a full
deployment-lifecycle improvement or faster readiness.

The behavior is consistent with a visible product cost: every fresh shared
deployment performs a complete integrity verification of the 2.139 GB sidecar,
and memory-pressure/page-residency state varies after normal private repacking.
This is an interpretation, not a proven microarchitectural cause. The raw
readiness, page-fault, PMU, and host-state evidence is retained. Skipping
integrity verification after observing this result would change the product
security boundary and was not done.

## Claim boundary and operational cost

The valid claim is exact aggregate steady-state request throughput and density
under the measured fixed physical-memory cap on a stable native Arm host. It
does not cover cold page cache, energy, billing cost, other models, or other
Arm systems. PMU counters are retained as bounded telemetry and do not by
themselves authorize kernel-causality claims.

The single `c4a-highcpu-8` VM existed from 09:21:48 to approximately 10:36 UTC
and was explicitly deleted and verified absent. At the contract's published
US$0.30296/hour compute estimate, roughly 1.24 hours is about US$0.37 compute,
plus a small prorated disk charge. This is a safety estimate, not a billing or
product-cost claim. The temporary project SSH key was uniquely removed while a
pre-existing key was preserved.

## Evidence

The compact [manifest](../manifests/e22c-axion-20260806.json) retains every cell,
pair, distribution, gate, response map, PMU count, memory reading, construction
cost, and claim boundary. Three independent ingestions reproduced the summary
byte for byte at SHA-256
`1df07171f09c780ca33c1d6f7d1049bf2f8094908dc75537bdd486fe477a55b8`.

The sealed raw bundle is `e22c-evidence-15ca91b.tar.gz`, 10,317,998 bytes,
SHA-256
`4ec1589ddb986667a710d8b049b2ce3d37fc6ea8c2caee656bc2d6c428b58246`.
Its inventory rehashes 554 regular files; six runtime library symlinks are
validated against exact targets. The 2 GB model and generated sidecar are
excluded, while their hashes, receipt, source/build identity, construction
recipe, and exact 20 MB runtime closure are retained.
