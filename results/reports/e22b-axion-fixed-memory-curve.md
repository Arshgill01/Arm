# E22b stable Axion fixed-memory curve

## Decision

**Promote the shared packed-weight mechanism and freeze a clean repeated
normal-6 versus shared-8 comparison.** On one on-demand Google Axion
`c4a-highcpu-8` node with an exact 16,723,460,096-byte physical memory cap,
the normal repack path admitted six one-thread workers and the shared sidecar
path admitted eight. The shared-8 cell delivered 2.6760 exact requests/second,
1.3545x the normal-6 cell's 1.9757 requests/second, with no response drift or
request failures.

This is native stable-host performance evidence, not an energy, billing,
cold-cache, or broad microarchitectural-causality claim. The contract required a
separate clean repeated comparison before the maximum-density number becomes
the final headline.

## Fixed-memory curve

Every valid cell ran the complete 30-task reference trace once per worker after
two explicit warmups. Workers used one inference thread on an eight-core
Neoverse V2 host with no SMT or swap. All valid cells reproduced the retained
response map, completed every request, counted all five frozen PMU events, and
retained at least 512 MiB `MemAvailable` after measurement.

| Workers | Normal req/s | Shared req/s | Shared/normal req/s | Normal PSS | Shared PSS | PSS saved | Shared/normal p95 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.3474 | 0.3461 | 0.9963x | 4,447,512 KiB | 4,448,035 KiB | -523 KiB | 1.0022x |
| 2 | 0.6843 | 0.6837 | 0.9991x | 6,811,264 KiB | 4,724,340 KiB | 2,086,924 KiB | 1.0046x |
| 4 | 1.3498 | 1.3860 | 1.0269x | 11,538,432 KiB | 5,276,579 KiB | 6,261,853 KiB | 0.9745x |
| 5 | 1.6680 | 1.7237 | 1.0334x | 13,901,717 KiB | 5,552,672 KiB | 8,349,045 KiB | 0.9671x |
| 6 | 1.9757 | 2.0657 | 1.0456x | 15,524,606 KiB | 5,828,648 KiB | 9,695,958 KiB | 0.9495x |

At each common admitted count, shared throughput remained at least 99.63% of
control and p95 remained within 0.47% at one and two workers before improving at
higher counts. At four workers, the sidecar saved 6,261,853 KiB summed PSS,
clearing the predeclared 5,242,880 KiB gate by 1,018,973 KiB.

At the maximum admitted counts, shared-8 used 6,380,746 KiB summed PSS versus
15,524,606 KiB for normal-6 while serving two additional workers. That is 58.90%
less summed PSS, 1.3333x worker density, 1.3545x aggregate throughput, and
3.2955x throughput per GiB of summed PSS. Shared-8 retained 13,839,196,160 bytes
`MemAvailable`; normal-6 retained 1,612,726,272 bytes.

## Measured normal-path boundary

The frozen rule permitted normal-8 only because normal-6 was valid, recorded no
OOM kill during its workload, and retained more than the 512 MiB reserve.
Normal-8 then failed before readiness. Four workers became ready, one worker was
killed with signal 9, and the independently captured `/proc/vmstat` state moved
from `oom_kill 0` to `oom_kill 1` with no swap traffic. The failed cell and all
worker logs are retained. This is a measured fixed-memory admission boundary,
not an inferred projection.

The failure-path kernel-journal command used a `journalctl --kernel` spelling
unsupported by this Ubuntu build, so that file contains the tool error rather
than kernel messages. The pre/post host snapshots independently preserve the
OOM counter transition; the retainer explicitly validates it.

## Lifecycle costs and limitations

One verified native sidecar is 2,139,013,120 bytes plus an 82,016-byte index.
Construction took 15.7072 seconds and temporarily required 4,276,977,664 bytes
for raw repacked tensors plus the sidecar. Full verification took 2.4797
seconds, and 183 raw tensors totaling 2,137,964,544 bytes were deleted after the
sidecar was sealed.

Shared/control readiness at the clean four-worker matched point was 1.2694x,
so E22b does **not** claim faster worker readiness. Shared-6 readiness also rose
after the memory-pressured normal-6 cell. The repeated successor balances order
and reports readiness rather than hiding this cost.

The node had standard Google Axion PMU access. Every valid cell retained
`cpu_cycles`, `inst_retired`, `l1d_cache`, `l1d_cache_refill`, and `l2d_cache`
over the exact measured worker-process window. E22b uses these as mechanism
telemetry only; it does not claim that any one counter proves broad causality.

## Evidence

The compact [manifest](../manifests/e22b-axion-20260806.json) preserves the
contract, all cells, exact response maps, gates, construction/storage costs,
host identity, PMU counts, and the independently proven OOM boundary. Three
independent ingestions reproduced the raw summary byte for byte at SHA-256
`06d921ad37bfb19969ab4a5a564937f3176fe556d25f28f0df61fd30bd6e09c9`.

The corrected sealed raw bundle is `e22b-evidence-a0c539f-v2.tar.gz`,
10,255,094 bytes, SHA-256
`a415ac6ad262911a98b38c6fe136bd4dfbe74d2e815531a80d2037d884af5ec0`.
Its inventory rehashes 628 regular files; six runtime library symlinks are
validated against exact targets. The model and generated 2.14 GB sidecar are
excluded from the bundle, while their hashes, construction recipe, receipt,
index identity, source, binary closure, and runtime are retained. The earlier
inventory packaging attempt is preserved inside the v2 evidence as a corrected
negative operational record.
