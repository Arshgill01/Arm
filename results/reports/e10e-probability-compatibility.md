# E10e native probability compatibility preflight

Native Arm run
[`30827797407`](https://github.com/Arshgill01/Arm/actions/runs/30827797407)
passes the separately frozen two-case compatibility contract. It reproduces the
two exact Q4_0 E10d failures, then completes both continuations twice by forcing
a serialization-safe sampled token while requesting the original target's raw
pre-sampling log probability. This permits a separately named full-holdout
successor; it does not make E10d valid or establish external task quality.

## Why this preflight exists

E10d received HTTP-200 responses that omitted the single
`completion_probabilities` entry required by its scorer. The failures occurred
at HellaSwag ordinal 44, choice 1, token index 28 (target ID 1194), and ordinal
70, choice 1, token index 13 (target ID 27043). The second case appeared only
in Q4_0; Q4_0 therefore exposes both compatibility edges in one bounded job.

The exact E10b primitive reads caller-requested token probabilities from the
raw model softmax. Its sampled output is not used for scoring. E10e tests
whether the server can always serialize that probability record when sampling
an already verified complete one-byte token instead of a token whose emitted
piece may remain incomplete in a one-token response.

Before native execution, the contract fixed token ID 1046 (`.`), byte 46,
logit bias `+100.0`, seed 424242, `n_predict=1`, the two full prompt/candidate
token sequences, three fresh processes, and `1e-6` equivalence tolerances. The
safe token was selected because it already occurs in both frozen continuations,
and native E10d raw records encode it as one byte with a complete probability
entry. No task, case, token, repeat, or tolerance changed after results.

## Result

| Variant | Ordinal 44 | Ordinal 70 | Process outcome |
| --- | ---: | ---: | --- |
| Original | Missing entry at attempt 29 / token index 28 | Missing entry at attempt 14 / token index 13 | Exact E10d failures reproduced |
| Forced safe, repeat 1 | 42/42 target scores | 29/29 target scores | Complete; every sampled token was 1046 |
| Forced safe, repeat 2 | 42/42 target scores | 29/29 target scores | Complete; every sampled token was 1046 |

Across the 41 original successful requests before the two failure points, the
maximum original-versus-forced requested log-probability delta was exactly
`0.0`. Across all 71 requested target scores, the maximum forced-repeat delta
was also `0.0`. Every forced raw response contained token 1046 and content
`.`. The ingester validates the selected target ID and score against each raw
response, so sampling `.` is not confused with scoring `.`.

All 185 attempted responses—including the two reproduced missing-entry
responses—were gzip-compressed before probability parsing and independently
validated. Their compressed inventory contains 270,692 bytes, 556,404
uncompressed bytes, and SHA-256
`be98e588b528f585443a352083b61c63a93eb44365cd1fed5509841a0d3d1694`.

The three fresh Q4_0 server processes reported 1.82–1.83 second readiness and
4,054,828–4,056,284 KiB maximum RSS. These process counters are retained only
as validity evidence. E10e is not a performance comparison, and no timing or
memory improvement is claimed.

## Decision and boundary

The frozen gates pass:

- both original missing entries reproduce exactly;
- both safe-token variants complete all 71 requested target scores;
- all 142 forced sampled tokens are exactly token 1046 with text `.`;
- original-prefix and repeat log-probability deltas are both `0.0`;
- exact source, model, E7c service, E10b patch, native architecture, readiness,
  process, recipe, runtime-closure, and raw-response gates pass.

E10e therefore allows E10f: a new full run with the unchanged E10d models,
tasks, sample map, harness construction, metrics, and zero-failure rule, while
forcing the same safe sampled token for every score and retaining every raw
response before parsing. E10f must be frozen before observation and must remain
distinct from failed E10d. Stock or generated quantization frontiers remain
blocked until a full successor independently validates.

## Reproducibility

Artifact `e10e-probability-preflight-30827797407-1` (ID `8861819016`) retains
the frozen plan and cases, source diff and patches, compiler/build commands,
CMake cache, binary/runtime closure, exact model hash, recipes, host capture,
three process logs, all raw responses, and workflow summary. Local independent
ingestion reproduced that summary byte for byte at SHA-256
`44d07878e00520836ec9283d2b06724c402c832ff55c3424791262181abc4170`.
The compact
[`manifest`](../manifests/e10e-30827797407.json) has SHA-256
`3e689b52e59edb2eb6b523152ec54dfc0cf31a87200555aacc9bd608f7b7e167`.
