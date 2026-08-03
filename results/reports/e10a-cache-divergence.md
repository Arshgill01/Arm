# E10a cache-divergence calibration

Status: **valid calibration; cached top-1 margin is not separable; no guard or
holdout promoted**.

Native run
[`30792707822`](https://github.com/Arshgill01/Arm/actions/runs/30792707822)
passed the frozen contract/input checks, pinned and hashed the selected model,
and built the exact patched b10216 E7c OpenSSL-off service on the native
`ubuntu-24.04-arm` runner. The first fresh cache-off cell completed its warmup
and all 16 measured requests, but the probe rejected at least one required
timing field after its candidate-distribution parser had already converted the
underlying request into an error record.

No E10a calibration summary, separation result, threshold, holdout result, or
performance promotion was produced. The always-uploaded artifact
`e10a-cache-divergence-30792707822-1` retains the contract, source/build/binary
closure, host capture, launch recipe, full server log, readiness, and process
record for the failed cell. Probe revision 1 returned before writing its
per-request error records, so the exact response-shape exception was not
retained; this is itself a harness retention defect.

The retry changes only failure retention: the probe writes raw failed responses
and error messages before returning nonzero. The A/B/C/D grammar, task sequence,
cardinalities, repetitions, cache states, probability semantics, separation
gate, and claim boundary remain unchanged. Results will be appended here; the
failed run remains part of the experiment history.

Native retry
[`30793244346`](https://github.com/Arshgill01/Arm/actions/runs/30793244346)
retained the missing response detail from the same first cache-off cell. Pinned
b10216 emitted an A/B/C/D grammar-constrained sample, but its `top_probs` list
contained the pre-grammar vocabulary distribution even though the request and
response both recorded `post_sampling_probs=true`. All four exact candidate
tokens were present for every request; non-candidates such as `The`, `To`, and
`**` explained the parser rejection. No cache-on cell or separation result was
observed.

Revision 3 freezes the API-compatible representation before retrying: require
all four A/B/C/D entries in the returned top 32, aggregate exact-byte duplicate
tokens, and renormalize only their raw probability mass. Conditioning the raw
softmax on the grammar's complete support preserves candidate ordering and
produces the intended four-choice distribution. Raw candidate mass and the
discarded top-entry count are retained. No task, request order, cache state,
repetition, signal direction, separation gate, or claim boundary changes.

## Native calibration outcome

Native run
[`30793728347`](https://github.com/Arshgill01/Arm/actions/runs/30793728347)
completed all 12 fresh-process cells on a four-logical-CPU Neoverse N2
`ubuntu-24.04-arm` runner. It retained 192 measured requests and 96 paired
cache-off/cache-on comparisons with zero request failures. The cache mechanism,
exact E7c service/source/model identity, raw candidate probabilities, input
hashes, process isolation, binary and dependency closure, and predeclared scope
all validated. Local independent re-ingestion produced a byte-identical summary
with SHA-256
`c511ec9ef0aec72d0f2481ab89998a5e4d9a721b4397b93ab1ec6127b1837d53`.

| Prefixes | Off req/s | On req/s | Speedup | Off/on p95 HTTP (ms) | Off/on CPU s/request | Drift pairs |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.3593 | 1.1092 | 3.0869x | 2986.3 / 1071.9 | 11.0291 / 3.5566 | 4 / 32 |
| 2 | 0.3569 | 0.8298 | 2.3254x | 3000.0 / 1729.5 | 11.1000 / 4.7494 | 0 / 32 |
| 4 | 0.3571 | 0.8434 | 2.3618x | 3000.6 / 1734.3 | 11.0875 / 4.6788 | 0 / 32 |

Every drift was the repeat-stable `logic-02` request shape at one prefix: its
candidate top-1 changed from B uncached to D cached. The diagnostic paired
Jensen-Shannon divergence separated that shape from the stable pairs, with a
minimum drifted value of 0.00130494 nats versus a maximum stable value of
0.00112812. It is not a serving-time guard because computing it requires the
uncached shadow result.

The frozen cache-only signal failed its global separation gate. The maximum
cached top-1 margin among drifted pairs was 0.0279410, while a stable pair had a
smaller margin of 0.0122079, giving a negative strict gap of -0.0157331. A
threshold that catches every observed drift would therefore also reject at
least one stable request, and no predeclared policy permits tuning that
tradeoff. The result status is `valid_cache_margin_not_separable` and
`proceed_to_frozen_holdout` is false.

## Decision and claim boundary

E10a rejects a margin-only cache guard for this scope. It does not select a
threshold, inspect an independent holdout, promote cached alternating-prefix
serving, or support energy, PMU, fleet, concurrency, cost, local-device, or
other-runtime claims. The 2.33x–3.09x performance opportunity and repeat-stable
drift are evidence for continued mechanism work, not permission to weaken the
quality gate. The retained result is
[`e10a-30793728347.json`](../manifests/e10a-30793728347.json); complete cell logs,
raw responses, process captures, build products, and runtime files are in the
90-day artifact `e10a-cache-divergence-30793728347-1`.
