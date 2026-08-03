# E15b exact two-CPU split-scheduler confirmation

## Result

Native GitHub Arm64 run
[`30851607665`](https://github.com/Arshgill01/Arm/actions/runs/30851607665)
completed all 12 fresh processes and independently validated as
`valid_affinity_split_scheduler_no_promotion`.

The run restricted the server, client, and every observed server thread to CPU
IDs 0 and 1 on the four-core Neoverse N2 host. It compared the exact E9a
`threads=4, threads-batch=4` service with only the decode pool reduced to two
threads. Six reverse-balanced repetitions made the small scheduler effect
visible.

| Exact two-CPU profile | Median throughput | Median / p95 HTTP | Median encode | CPU seconds/request | Throughput CV |
| --- | ---: | ---: | ---: | ---: | ---: |
| tied 4 / 4 | 0.4613 req/s | 2,118.7 / 3,735.8 ms | 1,978.5 ms | 4.2693 s | 0.265% |
| split 2 / 4 | 0.4632 req/s | 2,118.2 / 3,732.0 ms | 1,986.3 ms | 4.2693 s | 0.338% |

The split profile retained exact 23/30 answers in every repetition, had zero
request failures, and passed the frozen throughput, median latency, p95,
encode-latency, cache, and dispersion gates. Its ratios versus tied 4/4 were:

- throughput: **1.00427x**;
- median HTTP latency: **0.99977x**;
- p95 HTTP latency: **0.99897x**;
- median encode latency: **1.00393x**;
- CPU seconds/request: **1.00000x**.

## Decision

Do not promote the split scheduler. The contract required CPU seconds/request
at or below 0.98x, and the measured ratio was exactly 1.00x. A 0.43% throughput
change without CPU reduction is not a useful new operating point. The gate was
not changed after observation.

This also bounds the earlier descriptive four-CPU result rather than rewriting
it: the valid two-CPU confirmation shows no material benefit, while the invalid
four-CPU run showed a throughput regression. No default thread recipe changes.

## Evidence

The retained [manifest](../manifests/e15b-30851607665.json) contains every raw
request and all affinity snapshots. Its independent summary is byte-identical
to the workflow summary at SHA-256
`4fc3749dd4292e568897d9a57e236dc7d36025853062bbc5bade1258bb834949`.
All 237 runner-inventoried files were rehashed. The complete artifact is
`e15b-affinity-split-scheduler-30851607665-1` (ID `8871235428`, digest
`sha256:f25c9faf66e445d070613cabfed589091cd222d88496a40c5ae1c6745a43d5cd`).

The result supports only this exact selected model, E9a service, workload,
two-CPU affinity, and native runner. It supports no energy, PMU, fleet, device,
or general scheduler claim.
