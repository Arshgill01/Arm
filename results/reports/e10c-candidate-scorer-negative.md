# E10c candidate scorer: retained native negative result

Native Arm run
[`30812791972`](https://github.com/Arshgill01/Arm/actions/runs/30812791972)
completed the full frozen four-process E10c matrix. The shared-prefix scorer
showed a large efficiency signal and preserved every task prediction, but it
failed all three pre-registered numerical parity gates. It is not promoted.

## Frozen experiment

The exact b10216 E7c OpenSSL-off service plus the E10b `probability_ids` patch
and E10c `/score` patch ran on a four-logical-CPU Neoverse N2 GitHub Arm64
runner. The selected Ministral 3B Q4_K_M model, 30 retained tasks, prompt
template, candidate IDs, cache-disabled requests, fresh processes and
serial/forked/forked/serial order were fixed by contract SHA-256
`a8196cf4958e0c93589c11e1a721dd79a912cb6e0af6ce6525b8c3ddf544db19`.

The promotion tolerances were frozen before the run: at most `1e-6` absolute
single-token error, at most `3e-6` multi-token sum error, at most `1e-6`
per-token multi-token error, exact predictions and prompt identity, zero
failures, median latency and CPU ratios no greater than `0.7`, prompt-evaluation
ratio exactly `0.25`, and RSS ratio no greater than `1.05`.

All four cells completed before independent ingestion rejected the first parity
gate. The retained negative-result ingester validates the same contract,
source/build closure, recipes, process evidence, tasks and all 368 compressed
HTTP responses, but treats finite out-of-tolerance values as failed gates
rather than malformed evidence.

## Result

| Metric | Serial reference | Shared-prefix scorer | Ratio |
| --- | ---: | ---: | ---: |
| Accuracy | 70% | 70% | 1.000x |
| Median HTTP latency/task | 6,180.85 ms | 1,555.45 ms | 0.2517x |
| p95 HTTP latency/task | 9,499.87 ms | 2,395.31 ms | 0.2521x |
| Median CPU seconds/task | 25.3367 s | 6.3615 s | 0.2511x |
| Median throughput | 0.15668 task/s | 0.62203 task/s | 3.9701x |
| Maximum RSS | 4,525,004 KiB | 4,523,824 KiB | 0.9997x |
| Median readiness | 2,597.27 ms | 2,628.87 ms | 1.0122x |
| Prompt evaluations | 240 | 60 | 0.2500x |

There were zero request failures. Every prompt hash and all 120 task
predictions matched across mode and repetition. Both modes scored 21/30. The
efficiency, prediction, prompt-identity, failure, latency, CPU, evaluation-count
and RSS gates therefore passed.

The exactness gates did not:

| Frozen gate | Limit | Observed | Status |
| --- | ---: | ---: | --- |
| Single-token absolute delta | `1e-6` | `0.0012346844351860398` | Fail |
| Multi-token summed delta | `3e-6` | `0.09551615749218456` | Fail |
| Multi-token per-token delta | `1e-6` | `0.13800942582795983` | Fail |

The roughly 4x efficiency signal is real for this compounded endpoint, but it
cannot be reported as an exact reusable scorer. Identical predictions do not
override the frozen probability contract.

## Diagnosis and bounded repair investigation

Two defects explain the large native discrepancy. First, the initial scorer
implemented a direct double-precision log-softmax, while the serial E10b
reference uses the server's float probability representation and logarithm
helper. Second, continuations copied from one prefix advanced together in a
decode batch; the native backend did not reproduce independent serial-prefix
logits at the required tolerance.

A local correctness investigation matched the float probability path, then
serialized candidate continuation decoding. A further version rewound one
sequence to the same shared prompt between candidates. The targeted tiny-model
test still found a `0.00048065185546875` second-token difference from the
frozen reference. That local result is diagnostic only, not Arm performance
evidence.

The remaining difference is structural: the frozen serial reference
re-prefills the complete growing prefix for each continuation token, whereas a
cache-sharing scorer advances continuation tokens incrementally. Those paths
can use different kernels and accumulation shapes. Re-prefilling every prefix
would reproduce the reference by abandoning the reuse the experiment is meant
to test, and would not support the frozen 0.7 latency/CPU hypothesis. The gates
were not relaxed and another expensive native run was not dispatched after the
local preflight disproved the repair.

## Reproducibility and decision

The 90-day artifact `e10c-candidate-scorer-30812791972-1` has GitHub artifact
ID `8855844452`, archive SHA-256
`ca1014614f2c9dd02f34304378b6bcdc461c99676d0746c654e5d7900be7d855`,
and expiry `2026-11-01T12:14:46Z`. It retains the contract, five patches,
combined source diff, source revision, CMake cache and build commands,
compiler and host capture, binary/dependency closure, model hash, exact
commands and recipes, four process records, server logs, raw responses and
probe results.

Independent negative ingestion produced a deterministic summary at SHA-256
`e6c3c7698f58ff4f506f6054f9a2d684957410c34b7cec312e6a8cf73655d538`.
The compact machine-readable
[`manifest`](../manifests/e10c-30812791972.json) records the raw probe hashes,
metrics, failed gates, diagnosis and claim boundary.

Decision: do not promote `/score`, do not use it for an external holdout, and
do not attribute its compounded efficiency to one mechanism. Any holdout work
must use a separately validated API path, such as the exact E10b serial
probability selector, and retain its own compatibility preflight and contract.
