# E22a product-path sidecar scaling preflight

## Decision

**Proceed to a separately frozen fixed-memory experiment on a stable Arm host.**
Native GitHub Arm64 run
[`31086439785`](https://github.com/Arshgill01/Arm/actions/runs/31086439785)
passed every predeclared advance gate across the actual `pareto64 deploy` product
path at one, two, and four workers. This is a retained preflight, not the final
performance authority or a fixed-memory throughput claim.

The run issued 420 measured requests across six fresh deployments. All requests
succeeded; all workers reproduced the retained 23/30 response map; and normal
and shared modes produced no response differences. Each shared worker proved
the expected sidecar inode in `/proc/PID/maps` with a read-only shared mapping.

| Workers | Shared/control throughput | Shared/control p95 | Normal summed PSS | Shared summed PSS | PSS saved | Throughput/GiB gain |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.0055x | 0.9970x | 4,446,548 KiB | 4,447,063 KiB | -515 KiB | 1.0054x |
| 2 | 1.0031x | 0.9998x | 6,809,956 KiB | 4,723,031 KiB | 2,086,925 KiB (30.65%) | 1.4464x |
| 4 | 1.0052x | 0.9969x | 11,536,520 KiB | 5,274,696 KiB | 6,261,824 KiB (54.28%) | 2.1986x |

The saving grows rather than collapsing: approximately 1.99 GiB at two workers
and 5.97 GiB at four. Aggregate throughput and p95 latency remain effectively
unchanged at every count. These results validate the scaling mechanism and
justify freezing a real memory cap after a stable host is selected.

## Lifecycle costs and readiness finding

The one-time product prepack took 12.8966 seconds, including 6.1117 seconds to
serialize the 2,139,013,120-byte sidecar and 2.3661 seconds for full
verification. Construction temporarily required 4,276,977,664 bytes for raw
repacked tensors plus the sidecar; all 183 raw tensor dumps totaling
2,137,964,544 bytes were then deleted.

Full-command readiness was worse for the shared path in this preflight:
shared/control all-worker readiness was 1.1695x, 1.9932x, and 3.5466x at one,
two, and four workers. Inspection identified a product-path cost rather than a
loader regression: launch planning performs one complete 2.14 GB sidecar
verification per worker before starting any worker. The older E16b warm-loader
claim remains separate. A successor may remove only the redundant repeated
verification while retaining one complete identity-bound verification and
post-launch mapping proof.

## Evidence and boundary

The compact [manifest](../manifests/e22a-31086439785.json) preserves all cells,
pairwise ratios, construction/storage costs, gates, host fingerprint, GitHub
job identity, and artifact identity. Independent local ingestion reproduced the
workflow summary byte for byte at SHA-256
`02228e33f4f295f1aa638b623c952f9aed7df406768f7810c4a948477bc3cf11`.
All 214 runner-inventoried files were rehashed; the six archive-expanded runtime
aliases matched their versioned targets. The complete artifact is
`e22a-sidecar-scaling-preflight-31086439785-1` (ID `8962040739`, digest
`sha256:112ac47bdffdf2ba5ad620f2e6d5b8c8f68392ae6b949c21d311680a1f8f5fe5`).

The ephemeral four-CPU GitHub runner is not a stable performance authority.
`perf_event_paranoid=4` blocked PMU access. Therefore this run permits no final
performance, fixed-memory, cold-cache, energy, cost, or microarchitectural
causality claim. Those claims require the separately frozen stable-host
successor.
