# E21b native full-quality online-certificate preflight

## Decision

**Valid preflight; the bounded repeated E21b matrix is authorized. No native
performance claim is authorized by this two-process run.**

GitHub Actions run
[`30983800871`](https://github.com/Arshgill01/Arm/actions/runs/30983800871)
completed successfully on a native `ubuntu-24.04-arm` runner at repository
commit `356d0143a6a6107c39cc95eb3633bfa724521ffe`. All 16 gates frozen before
measurement passed. The independently regenerated summary is byte-identical to
the workflow summary at SHA-256
`f66e4c7f78f33c1116fd8144a632f0c3cceff252b564d8adf9a527fef1bd6295`.

## What was tested

The exact E7c Q4_K_M service and binary served the original 30-task quality set
through `/v1/chat/completions`. One fresh all-uncached process and one fresh
adaptive-online process each served two complete cycles. The client used the
original system and user messages, temperature zero, seed `424242`, eight output
tokens, disabled thinking, and an explicit cache policy on every raw call.

The online policy knew none of these fingerprints from E13b. Every unknown route
was compared as a cached shadow plus an uncached oracle, the shadow was never
served, and only exact matching transitions became eligible for later reuse.

## Safety and quality result

| Frozen property | Native result |
|---|---:|
| Reference quality, both policies and cycles | 23/30 |
| Online-versus-uncached response mismatches | 0 |
| Request failures | 0 |
| First observations handled by shadow/oracle | 31 |
| Certified transitions | 30 |
| Denied transitions | 1 |
| Known routes served from certified cache | 29/29 |
| Unknown cached attempts served | 0 |
| Denied routes served uncached | 1/1 |

The adaptive ranges were frozen before these results: at least 24/30 repeating
transitions had to certify, at most seven could be denied, and at least 23/29
known routes had to be cached. The observed 30 certifications, one denial, and
29 certified known routes therefore pass without post-result gate changes.

## Diagnostic timing boundary

These measurements cover only one fresh process per policy and are not a
performance result:

| Metric | All uncached | Adaptive online | Ratio |
|---|---:|---:|---:|
| Served throughput | 0.593814 req/s | 0.600102 req/s | 1.010589x |
| Median user latency | 1608.264 ms | 1945.149 ms | 1.209471x |
| p95 user latency | 2480.410 ms | 3368.888 ms | 1.358198x |
| CPU/served request | 6.655833 s | 6.602500 s | 0.991987x |
| Peak RSS | 4,491,464 KiB | 4,491,456 KiB | 0.999998x |
| Readiness | 2524.524 ms | 2526.826 ms | 1.000912x |

The first-use shadow/oracle work creates an honest median and p95 regression in
this short run even though throughput and CPU/request are near parity. The full
matrix must expose repeated-cycle steady state, first-use cost, break-even, and
scheduler noise before any performance promotion.

## Reproducibility and retained evidence

The machine-readable [manifest](../manifests/e21b-preflight-30983800871.json)
binds the run, commit, exact contract, server binary, dynamic dependency closure,
model, client schema, raw calls, answers, process metrics, and artifact digest.
The retained artifact contains 68 files totaling 33,831,665 bytes. Its runner
inventory covers 60 regular files and independently verifies at SHA-256
`90ebdfac9c157c0fd99dc207589183c90da8b5ce21cc9b6dc7c8fda45684a160`;
the remaining files are the post-inventory disk snapshot and six reconstructed
runtime aliases whose bytes match their versioned targets.

Artifact `8921316583` is retained as
`e21b-openai-certificate-preflight-30983800871-1`, has archive digest
`sha256:61bd6165a886658ebb14f5bf3911ed4681846ad1c1e401138a0ed1ec4a784719`,
and expires on 2026-11-03.

## Claim boundary

This result proves full-workload API, binary, quality, adaptive-safety, and
timing-schema readiness for the bounded successor matrix. It does not establish
a performance benefit, arbitrary-prompt generalization, concurrency behavior,
energy, PMU, device, fleet, cost, Mac, model-portability, or runtime-portability
claim.
