# E21a online certificate native preflight

## Decision

The bounded native Arm64 preflight passed every frozen correctness, identity,
artifact-shape and cache-mechanism gate. It authorizes a separately frozen full
experiment. It does **not** authorize a performance claim.

## What ran

GitHub run `30979498751` used one fresh all-uncached process and one fresh
online-policy process on `ubuntu-24.04-arm` (Neoverse N2). Both used the exact
selected Ministral 3B Q4_K_M model and retained E7c OpenSSL-off b10216 service.
The six-request trace alternated two prompt fingerprints absent from E13b.

An unknown transition always ran a cached attempt as shadow, then served an
uncached oracle. Exact output plus at least eight reused tokens certified the
transition. The start transition, which could not reuse tokens, was denied.

## Frozen-gate outcome

- All 14 frozen gates passed.
- Online and uncached answers were byte-exact; both scored 3/6 against the
  frozen expected labels and both matched all retained reference predictions.
- Both policies had zero request failures.
- Three unknown shadow/oracle routes were observed; no shadow output was
  served. Two transitions were certified, one was denied, and three later
  requests used a certified cached route.
- Every certified route demonstrated at least the frozen minimum token reuse.
- Source, recipe, binary/dependency closure, raw calls, process CPU, RSS,
  readiness, `/slots` array and complete workflow inventory were retained.

## Diagnostic timings only

| Metric | Uncached | Online | Online / uncached |
| --- | ---: | ---: | ---: |
| Served throughput | 0.76867 req/s | 0.92199 req/s | 1.19946× |
| Median user latency | 1292.48 ms | 820.89 ms | 0.63513× |
| p95 user latency | 1438.48 ms | 2766.81 ms | 1.92343× |
| CPU / served request | 5.07167 s | 4.29167 s | 0.84620× |
| Peak RSS | 4,290,296 KiB | 4,290,288 KiB | 1.00000× |
| Readiness | 2529.51 ms | 2528.70 ms | 0.99968× |

The p95 regression is the expected but material cost of synchronous first-use
shadow plus oracle calibration. The small two-prompt trace is deliberately not
used as a speed claim. The full experiment must measure lifecycle and
steady-state tails separately, preserve the first-use cost, and establish an
explicit break-even boundary.

## Reproducibility

The 60-file runner inventory was independently rehashed; the six materialized
shared-library aliases and post-inventory disk record were separately verified.
Independent ingestion reproduced `summary.json` byte for byte at SHA-256
`5b3ce1e5…55587f`. The GitHub artifact is
`e21a-online-certificate-preflight-30979498751-1`, ID `8919581630`, digest
`sha256:24ee6f5e…cb741`.

The machine-readable retained result is
[`e21a-preflight-30979498751.json`](../manifests/e21a-preflight-30979498751.json).
