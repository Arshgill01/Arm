# E6d — current-upstream Arm patch revalidation

Status: **valid current-upstream rebase**.

## Result

[GitHub Actions run 30675654688](https://github.com/Arshgill01/Arm/actions/runs/30675654688)
completed the frozen E6d contract in 6m59s on a native four-core Neoverse N2.
It checked llama.cpp tag `b10216`, commit
`876a4321163249c43ca4e986818fab5ab081f282`. A separate invocation of the
ingester reproduced the uploaded summary byte for byte at SHA-256
`32e01c0baf21de4679ace516a1ef61f7520dbbbc641d218aa454380e0c9767fa`.

The Q8 vector-store and reasoning-budget patches applied byte for byte. The
validated-feature correction needed only surrounding context refreshed after
upstream added SME source lists; the flag-substring defect itself remained.

## Source correctness and mechanism

The unpatched feature build under `armv8.6-a+sve2+nosve` exited 1 after selecting
an invalid SVE source. With the validated-feature correction, SVE remained
disabled, the invalid source disappeared, and the target built. The reasoning
baseline aborted with exit 134 at the exact regression assertion; the complete
series passed all 13 tests. Baseline and patched trees both passed the upstream
quantizer target.

| Emitted assembly measure | Baseline | Patched |
| --- | ---: | ---: |
| Static instructions | 157 | 100 |
| Scalar byte stores | 31 | 0 |
| Vector narrowing instructions | 0 | 6 |
| 128-bit vector stores | 0 | 2 |

## Direct Q8 performance

Four balanced 20,000-iteration rounds ran for each size. All twelve paired
rounds improved, and every frozen threshold passed.

| Values | Baseline range | Patched range | Median paired ratio | Improved rounds |
| ---: | ---: | ---: | ---: | ---: |
| 4,096 | 5.14–5.15 GB/s | 10.03–10.08 GB/s | **1.956x** | 4/4 |
| 65,536 | 5.17–5.18 GB/s | 10.07–10.11 GB/s | **1.950x** | 4/4 |
| 655,360 | 5.14–5.15 GB/s | 10.07–10.10 GB/s | **1.958x** | 4/4 |

## Decision and limits

The three-patch series is accepted as applicable to the frozen current upstream
revision with targeted source correctness, upstream unit-test, emitted-assembly,
and direct Q8 hot-path evidence. No model ran in E6d, so this result does not add
a whole-model inference, quality, energy, or upstream-CI-matrix claim. E6a,
E6b, and E6c retain the separate native model evidence and its limits.

The first native attempt, `30675615101`, stopped before a build because a second
tree was cloned from a partial promisor clone and could not resolve an absent
object. The workflow then copied the already verified pinned tree; experiment
inputs, patch order, measurements, and gates were unchanged. The retained raw
artifact is `e6d-current-upstream-patches-30675654688-1`; the compact record is
[`../manifests/e6d-30675654688.json`](../manifests/e6d-30675654688.json).
