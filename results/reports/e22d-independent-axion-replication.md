# E22d independent Axion replication

## Decision

**Promote the fixed-memory density result across two independent Google Axion
instances.** E22d repeated the frozen E22c normal-6/shared-8 comparison on a
fresh `c4a-highcpu-8` instance with a different provider instance ID. All four
balanced pairs passed every predeclared validity and advance gate. No E22c
threshold, runtime, model, workload, response map, or memory boundary changed.

Across E22c and E22d, eight balanced pairs and **3,360 exact measured
requests** give a median shared/normal aggregate-throughput ratio of
**1.3568x**. The minimum pair is 1.3457x, the maximum is 1.3762x, and the
combined ratio coefficient of variation is 0.6449%. Median per-worker
throughput is 1.0176x, median p95 latency is 0.9727x, median summed-PSS saving
is 59.32%, and median throughput per GiB of summed PSS is 3.3345x.

This promotes an independently replicated same-provider, same-machine-class
steady-state density result. It does not create a cross-provider, heterogeneous
fleet, energy, billing, cold-cache, or full-lifecycle claim.

## Independent host and frozen boundary

The source instance ID was `5558962151178759364`; E22d ran on fresh instance ID
`5259602977892141423` in `us-central1-a`. The second host exposed eight
Neoverse V2 cores, one thread per core, 16,723,460,096 physical bytes, no swap,
and the standard Arm PMU event source. Automatic deletion was frozen at four
hours with a US$3 experiment ceiling beneath the entrant-authorized US$40
ceiling.

The exact certified 20 MB runtime closure was recovered from the sealed E22c
bundle and rehashed before use. The 2,146,497,824-byte model and rebuilt
2,139,013,120-byte sidecar also passed their existing identity and full-content
verification. This avoided treating a locally rebuilt but binary-different
runtime closure as the same experimental input.

## Second-instance repetitions

The frozen `N6/S8/S8/N6/S8/N6/N6/S8` order again balances mode position. Each
normal cell served 180 measured requests and each shared cell served 240.

| Repetition | Normal-6 req/s | Shared-8 req/s | Aggregate ratio | p95 ratio | Readiness ratio | PSS saved |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.9617 | 2.6653 | 1.3587x | 0.9814x | 2.4604x | 58.71% |
| 2 | 1.9633 | 2.6779 | 1.3640x | 0.9691x | 1.1333x | 59.22% |
| 3 | 1.9597 | 2.6541 | 1.3544x | 0.9699x | 4.2652x | 57.86% |
| 4 | 1.9614 | 2.6992 | 1.3762x | 0.9676x | 1.9673x | 59.27% |
| **Median** | **1.9616** | **2.6716** | **1.3613x** | **0.9695x** | **2.2138x** | **58.96%** |

All 1,680 E22d requests succeeded, exactly reproduced the E22c response map,
and counted every frozen PMU event. Normal throughput CV was 0.0654% and shared
throughput CV was 0.6259%. Median summed PSS was 15,549,565 KiB for normal-6
and 6,380,777.5 KiB for shared-8.

Normal-8 again failed before admission. `/proc/vmstat` recorded one additional
OOM kill and zero swap-in/out, while shared-8 completed. This is a retained
resource-boundary failure, not a throughput sample.

## Readiness remains outside the promoted claim

E22d was explicitly frozen as an independent density replication, not a reroll
of E22c's missed lifecycle gate. Its median shared/normal readiness ratio was
2.2138x. The combined two-instance median is also 2.2138x. These values remain
unfavorable and visible; the full all-lifecycle claim is still rejected.

The representation therefore changes how many exact workers fit and the
aggregate steady-state service rate under the fixed cap. It does not establish
faster startup. Complete sidecar integrity verification remains part of the
product boundary and was not skipped after observing the result.

## Fail-closed setup and resource cleanup

Two premeasurement setup attempts were retained separately. The first stopped
when Ubuntu reported `perf_event_paranoid=4`, outside the frozen PMU policy. A
pinned host-preparation step then set the permitted value before measurement.
The second stopped when a fresh source build produced a runtime closure whose
shared-library hashes differed from E22c. The final setup recovered and rehashed
the exact certified closure instead. Neither stopped attempt served a measured
request or weakened a gate.

The paid instance existed for 1,851.573 seconds (0.5143 hours) and its deletion
operation completed successfully. At the frozen US$0.30296/hour estimate, that
is approximately **US$0.1558 compute**, plus a small prorated boot-disk charge.
This is a safety estimate, not a cloud bill or product-cost claim. Post-delete
checks found no matching instance, disk, or address, and project SSH metadata
was restored to its preexisting state.

## Evidence

The compact [manifest](../manifests/e22d-axion-20260806.json) retains the host,
cells, pairs, distributions, gates, cleanup record, two-instance aggregate, and
claim boundary. Three independent ingestions reproduced the workflow summary
byte for byte at SHA-256
`ffc5c7587ac72d6c84c7c025a52141ce1300ec770743bb7773c5f4d4ceb75e1f`.

The sealed [successful raw bundle](https://github.com/Arshgill01/Arm/releases/download/e22-axion-evidence-20260806/e22d-evidence-4ad5ef4.tar.gz)
is 19,382,837 bytes with SHA-256
`7216dd6e0df5281116af85597b6a1edf7b6fccaa4a532fe8e57baed663c09db6`.
Its inventory rehashes 605 regular files plus the root inventory; six runtime
symlinks resolve to exact retained targets. Generated model/sidecar bytes and
raw tensors are excluded while their identities and construction receipts are
retained.

The sealed [setup-failure bundle](https://github.com/Arshgill01/Arm/releases/download/e22-axion-evidence-20260806/e22d-setup-failures-4ad5ef4.tar.gz)
is 9,101,132 bytes with SHA-256
`21ecb6913c16c4b4c862507fca5df0b08b69398b2dc65f70d9182568a82ff715`.
It preserves both premeasurement stops rather than silently discarding them.
