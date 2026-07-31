# E4a — native Pareto64 accept-backlog tuner

Status: **valid tuner win; backlog 64 selected**.

## Result

[GitHub Actions run 30638730535](https://github.com/Arshgill01/Arm/actions/runs/30638730535)
completed the frozen nine-configuration E4a search in 18.088 seconds on a
four-core Neoverse N2. Independent ingestion of the downloaded raw artifact was
byte-identical to the workflow result and validated the input hashes, cyclic
execution order, every raw request, service counters, process evidence, and all
predeclared selection and acceptance rules.

| Backlog | Failures | Requests >50 ms | Pooled p95 | Max latency | Median-round throughput | Max RSS |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 19 | 76 | 1,033.810 ms | 1,270.126 ms | 310.349 req/s | 24,252 KiB |
| 16 | 0 | 44 | 16.755 ms | 1,070.248 ms | 365.142 req/s | 23,996 KiB |
| **64** | **0** | **0** | **21.862 ms** | **24.939 ms** | **1,560.048 req/s** | **24,372 KiB** |

Backlog 5 reproduced a breach in all three rounds (25, 25, and 26) and all 19
failures were connection resets. Backlog 16 eliminated failures but retained
14, 15, and 15 one-second tail requests; those 44 events are 3.67% of its 1,200
requests, which explains why its pooled p95 remains below 50 ms. Backlog 64 had
no failure or tail event in any round.

## Frozen decision

Selection minimized total failures, then total tail breaches, then backlog
capacity, then pooled p95. It did not use a weighted score. Backlog 64 passed
every additional win condition:

- default backlog 5 reproduced at least one breach in every round;
- the selected backlog was larger than 5 and had zero failures and breaches;
- selected pooled p95 was at most 50 ms;
- selected median-round throughput exceeded the 90%-of-default guardrail; and
- selected maximum RSS was only 120 KiB above default, within the 10 MiB guardrail.

The full validated record is
[`../manifests/e4a-30638730535.json`](../manifests/e4a-30638730535.json).
Raw evidence is retained for 90 days in artifact
`e4a-backlog-tuner-30638730535-1`.

## Product impact and limits

Pareto64 now uses 64 as its default accept backlog while preserving
`--backlog` as an explicit override. Under this fresh-connection stress, the
selected setting delivered 5.027 times the default candidate's median-round
request rate and bounded all observed latency below 25 ms.

This validates a small decision-plane admission optimization. It does not serve
model tokens and does not support claims about inference TTFT, decode throughput,
quality, or energy. Those remain separate end-to-end gates.
