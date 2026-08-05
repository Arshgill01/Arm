# E21a full online transition certificate: safety success, invalid promotion

## Decision

The full native Arm64 matrix is retained as
`invalid_online_transition_certificate`. The online policy is **not promoted**,
and no generalized cache-performance claim is made. The existing exact retained
certificate boundary remains authoritative.

This is not a missing-data outcome. GitHub run `30980957266` completed all eight
fresh-process cells and all 960 served requests before the frozen ingester
raised on an observed-count difference. The uploaded 143-file artifact was
replayed twice byte-for-byte without adding a native measurement or changing a
contract or gate.

## Frozen contract outcome

Every online response exactly matched its paired all-uncached response, all 960
requests succeeded, no unknown cached attempt was served, and every mechanism
gate outside the predeclared transition counts passed. However, two tasks
returned `C` instead of the frozen `B` in every control and online cycle:
`arithmetic-04` and `systems-04`. Each cell therefore scored 84/120, or 21/30
per cycle, rather than the frozen 92/120 and 23/30.

The online controller also encountered two unsafe cached transitions beyond the
expected non-reusing start state. It failed closed: each online cell certified
28 transitions and denied 3, then served 84 certified cached routes, 31
shadow-then-oracle routes, and 5 denied uncached fallbacks. The frozen contract
expected 30 certifications, 1 denial, 89 cached routes, and no denied fallback.
The observed safety behavior is retained; the post-result count gate is not
weakened.

## Diagnostic performance only

All seven numerical promotion gates passed, but they are diagnostic because the
quality and frozen-count validity gates failed first.

| Metric | All uncached | Online | Online / uncached |
| --- | ---: | ---: | ---: |
| Served throughput | 0.60379 req/s | 0.97208 req/s | 1.60995× |
| Median user latency | 1,604.09 ms | 664.66 ms | 0.41436× |
| Lifecycle p95 latency | 2,442.58 ms | 3,006.71 ms | 1.23095× |
| CPU / served request | 6.56973 s | 4.07469 s | 0.62022× |
| Maximum RSS | 4,506,556 KiB | 4,506,660 KiB | 1.00002× |
| Median readiness | 2,529.71 ms | 2,583.76 ms | 1.02137× |
| Certified steady-state p95 | 2,450.96 ms | 1,090.60 ms | 0.44497× |
| Synchronous first-use p95 | 2,437.33 ms | 4,081.57 ms | 1.67461× |

Every repetition reached cumulative break-even in cycle 3. The first-use tail
is intentionally preserved beside the much faster certified steady state.

## Causal and harness boundary

The artifact does not isolate the response drift. E21 used `/completion` with
pre-rendered tokens and the retained E9c-built binary, while the frozen reference
map came from the earlier OpenAI-compatible quality path and another build. The
two-task native preflight included neither drifting task. A successor would need
to prove full 30-task API and binary identity equivalence before it could be
authorized; this result cannot be repaired by relabeling the observed 21/30 map.

The online controller's three denials are directly observable, but the entire
1.60995× diagnostic ratio is not attributed to a single mechanism or generalized
beyond this frozen lifecycle.

## Reproducibility

Source run [`30980957266`](https://github.com/Arshgill01/Arm/actions/runs/30980957266)
remains failed: measurement succeeded, source ingestion failed at
`e21a_full_ingest.py:148`, and artifact upload succeeded. Artifact
`e21a-online-certificate-30980957266-1` is ID `8920582060`, digest
`sha256:c66adef1…90c52`, and is retained until 2026-11-03. All 143 files and
36,028,075 uncompressed bytes hash to independent canonical inventory
`92b558de…5920`.

The retained [machine manifest](../manifests/e21a-30980957266.json) includes the
exact answers, all raw observed counts, throughput, latency distributions,
process CPU, RSS, readiness, recipes, source/runtime/dependency identity,
break-even traces, frozen gates, artifact identity, and the unchanged negative
decision. Its SHA-256 is `e18d3bbc…15ca`.
