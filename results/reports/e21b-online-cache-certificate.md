# E21b adaptive online cache certificate

## Decision

**Promote the frozen adaptive online policy inside its exact identity and
workload boundary.** Native run
[`30985501097`](https://github.com/Arshgill01/Arm/actions/runs/30985501097)
passes all 17 validity gates and all seven predeclared promotion gates. Four
fresh processes per policy reproduce the exact 23/30 reference map, every one
of the 480 online served responses matches its paired uncached response, and no
request fails.

This is not an arbitrary-prompt or semantic cache claim. It is an online,
fail-closed transition certificate for the exact E7c Q4_K_M service, client,
identity, and four-cycle sequential workload.

## Frozen experiment

The contract was frozen at SHA-256 `d9486025…7b88` before any full-matrix
result was observed. It specifies eight native `ubuntu-24.04-arm` cells in
ABBA/BAAB order, four fresh processes per policy, 120 served requests per cell,
960 served requests overall, and 1,084 raw HTTP calls. Each online process starts
with an empty registry.

An unknown transition is never served from cache. The controller first runs a
cached shadow, then runs and serves an uncached oracle. It certifies only an
exact output signature with at least eight reused tokens; mismatch, absent reuse,
failure, registry corruption, or identity drift fails closed. A certified route
may be served subsequently. The policy does not periodically re-probe an
already certified transition.

## Native results

| Metric | All uncached | Adaptive online | Online / uncached |
| --- | ---: | ---: | ---: |
| Served throughput | 0.59721 req/s | 1.03184 req/s | **1.72776x** |
| CPU seconds / served request | 6.64094 s | 3.83529 s | **0.57752x** |
| Median user latency | 1,598.15 ms | 133.27 ms | **0.08339x** |
| Lifecycle p95 user latency | 2,475.43 ms | 2,962.68 ms | 1.19683x |
| Median readiness | 2,580.00 ms | 2,480.80 ms | 0.96155x |
| Maximum RSS | 4,512,972 KiB | 4,513,088 KiB | 1.00003x |

The lifecycle p95 includes synchronous certification and therefore regresses
19.68%. That regression is retained, not hidden. The predeclared bound was
2.25x because the passing preflight had already exposed this cost.

The separated tail explains the tradeoff:

- Synchronous first use: 2,630.86 ms median and 4,114.90 ms p95 online,
  respectively 1.64761x and **1.66468x** the uncached path.
- Certified steady state: 131.63 ms median and 1,072.58 ms p95 online,
  respectively **0.08232x** and **0.43302x** the uncached path.
- Cumulative user latency breaks even in cycle two in every one of the four
  reverse-balanced repetitions.

Every repetition independently certifies 30 transitions, denies the non-reusing
start transition, serves 31 unknown shadow-then-oracle routes, and later serves
89 certified routes. Observed revocations are zero, but periodic
post-certification revocation is not implemented and is not claimed. Any bound
identity change invalidates the complete registry.

## Quality and mechanism proof

- Exact expected-label score: 23/30 in every cycle and policy.
- Correct counts: 368/480 for both policies.
- Paired online-versus-uncached response mismatches: zero.
- Cross-repetition uncached response mismatches: zero.
- Reference-prediction mismatches and request failures: zero.
- Unknown cached attempts served: zero.
- Every denial falls back to an uncached served response.

The result advances beyond E13b's fully precomputed fingerprint boundary by
showing that a fresh registry can learn exact transitions online while failing
closed. E13b remains valid for its own retained trace; E21b does not establish
semantic equivalence or safety for arbitrary prompts.

## Reproducibility and retention

The 14,416,402-byte GitHub artifact is bound to commit
`48cadbca063a2ad3b541edddf9649eb8356d0511`, artifact ID `8922450721`, and digest
`sha256:dc4ffe0c…7fce`. Retention verifies all 138 workflow-inventoried files plus
the six extracted runtime aliases and post-inventory disk record. Two independent
replays are byte-identical to the workflow summary at SHA-256
`74b4ab3c…790ce`.

The machine-readable retained result is
[`e21b-30985501097.json`](../manifests/e21b-30985501097.json). Raw process logs,
requests, answers, timing fields, resource records, registry traces, exact
commands, source diff, runtime closure, and environment remain in the bound
90-day artifact.

## Claim boundary

The promotion applies only to the exact E7c OpenSSL-off Q4_K_M service and
binary, exact OpenAI-compatible client identity, exact sequential 30-task
four-cycle workload, fresh per-process registry, and native four-vCPU GitHub
Arm64 runner. It does not establish concurrency, semantic or arbitrary-prompt
equivalence, periodic post-certification revocation, another model or runtime,
energy, PMU, Mac, local-device, fleet, or cost behavior.
