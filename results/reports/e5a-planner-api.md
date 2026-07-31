# E5a — native Pareto64 planner API concurrency

Status: **valid decision-plane concurrency result; not inference serving**.

## Result

[GitHub Actions run 30638049776](https://github.com/Arshgill01/Arm/actions/runs/30638049776)
passed the frozen E5a contract in 11 seconds on a four-core Neoverse N2. The
independent ingester rechecked both input hashes, every raw HTTP response,
latency statistics, service counters, process measurements, bounded shutdown,
and all predeclared thresholds.

| Measurement | Native result | Frozen gate |
| --- | ---: | ---: |
| Valid measured responses | 400/400 | 400/400 |
| Failures | 0 | 0 |
| Throughput | 369.685 requests/s | at least 100 requests/s |
| Median HTTP latency | 3.361 ms | reported |
| p95 HTTP latency | 5.153 ms | at most 50 ms |
| Maximum HTTP latency | 1,053.691 ms | reported |
| Service maximum RSS | 23,868 KiB | at most 262,144 KiB |
| Service process exit | 0 | 0 |

All 400 responses remained HTTP 200 with `no_feasible_candidate` and no selected
deployment. The service's own pre-final-request snapshot recorded 421 requests,
zero errors, and 1.115 ms mean handler time. It shut down automatically after
the exact contracted request count.

## Protocol

- Runtime: Python 3.13.14 on native `ubuntu-24.04-arm`
- Inputs: checksum-pinned E3 manifest and `cloud-balanced` policy
- Sequence: one readiness request, 20 warm-ups, 400 measured requests, then one
  metrics request
- Load: eight concurrent clients alternating cached GET planning and recomputed
  POST policy evaluation
- Correctness: every body must preserve the E3 quality-gated empty selection

The complete product suite ran first and passed 30/30 tests. Raw evidence is in
the 90-day artifact `e5a-planner-api-30638049776-1`; the independently validated
record is
[`../manifests/e5a-30638049776.json`](../manifests/e5a-30638049776.json).

## Tail finding

Two POST requests measured 1,006.317 ms and 1,053.691 ms; every other request
was below 7 ms. They remain in every mean, deviation, maximum, and raw record.
The predeclared p95 gate still passes, but a judge-facing product should not
ignore a repeatable-looking one-second tail.

The step-like delay is consistent with TCP connection admission pressure: the
standard `ThreadingHTTPServer` accept backlog is five while the probe opens
eight concurrent fresh connections. This is a hypothesis from the observed
shape, not yet mechanism proof. A separately frozen paired experiment must vary
only backlog capacity and show whether the >50 ms tail disappears.

## Limits and decision

E5a validates Pareto64's small, deterministic HTTP decision plane. It does not
serve model tokens and therefore cannot satisfy the final inference E5 gate or
support TTFT/token-throughput claims.

Accept the declared E5a pass. Preserve both one-second outliers, then use them to
motivate a bounded backlog tuner with paired native rounds. Do not change the
current report or retroactively add a maximum-latency acceptance rule.
