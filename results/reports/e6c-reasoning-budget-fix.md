# E6c — reasoning-budget forced-token correctness fix

Status: **source fix validated; frozen real-model application gate rejected**.

## Result

[GitHub Actions run 30654805236](https://github.com/Arshgill01/Arm/actions/runs/30654805236)
completed the frozen native experiment in 6m41s on a four-core Neoverse N2
runner. The untouched pinned source reproduced the new regression with exit
134 at the exact forcing-state assertion. Applying the one-condition source
guard made the complete upstream target pass all 13 tests. The reconstructed
two-file diff matched the frozen patch byte for byte at SHA-256
`2c0c611f325fd036eadaa0b7dc5615898f1ded3f770b0cf8eacb3a472a613783`.

The real Qwen3.5 Q4_0 application run then emitted zero reasoning characters
in all 60 requests, proving that the erroneous pre-generation state transition
was removed on native Arm. It did not pass the separately frozen completion
gate:

| Per 30-task repetition | Count |
| --- | ---: |
| Zero reasoning characters | 30 |
| Standalone A-D response with `stop` | 5 |
| Eight-token response ending by `length` | 25 |

Both repetitions were text-identical. In the 25 rejected cases the model had
entered final-channel content, but began an explanation such as `The
calculation is as follows:` and exhausted the predeclared eight-token cap before
returning a standalone letter. This is a real miss against E6c's contract, not
an ingestion or source-build failure. The validator was not relaxed and no E6c
manifest or planner candidate is accepted.

## Native evidence

The pinned server loaded the exact 2,583,221,408-byte model through a
`CPU_KLEIDIAI` buffer. Readiness took 1,976.6 ms and the server reached
7,829,944 KiB maximum RSS. For the first repetition, median encode, decode, and
combined model time were 1,584.9 ms, 562.9 ms, and 2,142.3 ms respectively.
These are diagnostic measurements from a rejected application run.

The shared quality scorer reported 6/30 because it extracts the first isolated
A-D anywhere in a response, including the article `A` in one truncated
explanation. E6c's stricter application validator counted only the five exact
standalone responses. Neither diagnostic result approaches or changes the 75%
deployment floor.

## Decision

Retain the patch as validated source-level correction evidence: the baseline
failure, exact diff, full upstream unit target, native KleidiAI execution, and
zero-reasoning behavior all reproduced. Do not claim that E6c passed as a
complete application fix, because its predeclared final-answer obligation did
not.

The failed first native attempt `30654443116` was a representation-only harness
failure: GitHub rendered diff object IDs with nine characters while the frozen
patch used seven. Attempt 2 pinned seven-character rendering without changing
the patch, model, tasks, or acceptance gates. The retained 90-day raw artifact
is `e6c-reasoning-budget-fix-30654805236-1`; its diagnostic quality-summary
SHA-256 is
`b4b32309a255a84956a68082cbcaa4f8075671e21df79f822d83e593c4bf73fe`.
