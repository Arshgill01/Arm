# E9c — prompt-cache alternating-prefix boundary

Status: **valid output regression; cache disabled for every tested policy**.

## Result

[Native Arm run 30770403695](https://github.com/Arshgill01/Arm/actions/runs/30770403695)
completed the frozen 36-process, 576-request matrix in 48m9s on a two-core
Neoverse N2 runner. The workflow ingester accepted the complete artifact, and a
separate local replay reproduced its summary byte for byte at SHA-256
`29b075b605e5d84d6de66b07fb4ab3c1562236c9aa4e7fd43d51e0ff7932eed4`.

The cache mechanism and every frozen performance/resource gate passed at all
nine points. The output gate did not. Across the complete matrix there were
zero HTTP failures, but 252 reference-prediction mismatches, including 204
responses that were not a standalone `A`, `B`, `C`, or `D`. Twelve paired
cache-off/cache-on answers also differed. No point is eligible, so the emitted
policy disables cache for one, two, and four alternating prefixes.

## Frozen matrix and gates

The exact E7c OpenSSL-off b10216 Q4_K_M service was held fixed. Each of the
predeclared one/two/four-prefix by 16/32/64-token points used two cache-off and
two cache-on fresh servers in A–B–B–A order. Each cell retained 16 measured
requests after one warmup per active prefix. The table reports cache-on divided
by cache-off except prompt encoding, which is the cache-off/cache-on speedup.

| Prefixes | Shared tokens | Throughput | Encode speedup | p95 latency | CPU/request | Paired drift | Eligible |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 16 | 2.3056x | 2.2446x | 0.5629x | 0.4330x | 0 | No |
| 1 | 32 | 2.0353x | 2.2059x | 0.5784x | 0.4903x | 0 | No |
| 1 | 64 | 2.4007x | 3.0000x | 0.4446x | 0.4137x | 4 | No |
| 2 | 16 | 1.9406x | 1.8943x | 0.5659x | 0.5144x | 0 | No |
| 2 | 32 | 2.1702x | 2.2005x | 0.4952x | 0.4579x | 4 | No |
| 2 | 64 | 2.0405x | 2.7253x | 0.6289x | 0.4875x | 4 | No |
| 4 | 16 | 1.9423x | 1.8916x | 0.5627x | 0.5143x | 0 | No |
| 4 | 32 | 2.0925x | 2.2036x | 0.5750x | 0.4764x | 0 | No |
| 4 | 64 | 2.1401x | 2.7851x | 0.6266x | 0.4655x | 0 | No |

Both repetition CVs stayed below 0.48%, far inside the frozen 5% ceiling.
Cache-off reported exactly zero reused tokens. Cache-on minimum reuse ranged
from 41 to 89 tokens, clearing the point-specific 16/32/64-token obligations.
Maximum process RSS stayed between 4,277,884 and 4,366,096 KiB, below the
8-GiB cap. The build retained the exact b10216 source and patches, used the E7c
OpenSSL-off arguments, and its 13-name dynamic dependency closure contained
neither `libssl.so.3` nor `libcrypto.so.3`.

## Output regression

The frozen request construction prepended controlled alternating prefixes and
added a stricter single-letter instruction to the original eight selected
tasks. Exact response strings are preserved in every manifest sample. The 576
responses comprised 180 exact `B`, 164 exact `C`, 28 exact `D`, and 204 longer
or truncated responses. Examples include `The correct answer is **C. ` and
`D. To reduce time-order and thermal`; the parser correctly rejected them
instead of extracting a convenient embedded letter.

This means the result cannot support a generalized cache-enablement rule even
though the cache path was mechanically active and faster. The performance
ratios are retained as diagnostic measurements only. They are not a promoted
optimization because the exact-output gate failed first.

## Decision and limits

The emitted policy is `disabled` for all three tested prefix cardinalities.
The earlier E5c default remains justified only for its exact quality-gated
shared-prefix workload; E9c does not broaden it to alternating-prefix traffic.
No prompt, task, parser, point, repetition, or acceptance gate was changed after
observing the result.

The raw artifact is `e9c-prompt-cache-30770403695-1`, artifact ID
`8840851593`, 9,551,133 compressed bytes, retained until 2026-10-31. The compact
machine-readable record is
[`../manifests/e9c-30770403695.json`](../manifests/e9c-30770403695.json); it
retains all responses, commands, host/build/source provenance, readiness, CPU,
RSS, token counters, and point gates. This experiment makes no energy, PMU,
local-device, concurrency, fleet, other-runtime, or untested-length claim.
