# E3f — Ministral 3 quality-per-byte frontier

Status: **valid selected frontier; first candidate to clear every frozen gate**.

## Result

[GitHub Actions run 30656151957](https://github.com/Arshgill01/Arm/actions/runs/30656151957)
completed the full native matrix in 12m38s on one four-core Neoverse N2 job.
Both quantizations produced identical predictions across two repetitions. The
Q4_K_M candidate reached 23/30 (76.67%), clearing the unchanged 75% floor by one
task; Q4_0 reached 21/30 (70.00%) and was rejected.
All 120 responses were exact standalone option letters and ended normally.

| Candidate | Stable score | Package | Load | Median model time | Peak quality RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Q4_0 | 21/30 | 2,046,375,200 B | 1,179.3 ms | 1,282.2 ms | 4,446,724 KiB |
| Q4_K_M | **23/30** | 2,146,497,824 B | 2,731.7 ms | 1,798.7 ms | 4,696,108 KiB |

Q4_K_M passes the independently frozen limits of 75% accuracy, 5 seconds
same-text latency, 8 GiB RSS, 5 GB package size, and 10 seconds load time. The
real Pareto64 planner therefore returns `selected` with
`ministral3_3b_q4_k_m` as the only feasible candidate and frontier member. No
weighted score is used.

## Quality and runtime tradeoff

The quantization change is consequential rather than cosmetic. Q4_K_M fixed
two Q4_0 errors (`arithmetic-03` and `data-01`) and crossed the quality floor,
but the directly proven Q4_0 KleidiAI path was faster:

| Synthetic 128-prompt/64-generation median | Q4_0 | Q4_K_M |
| --- | ---: | ---: |
| Prompt throughput | 75.635 tokens/s | 48.989 tokens/s |
| Decode throughput | 16.844 tokens/s | 15.505 tokens/s |
| Combined time | 5,496.1 ms | 6,743.8 ms |

Q4_0 used a `CPU_KLEIDIAI` model buffer. Q4_K_M used `CPU_REPACK` and
`CPU_Mapped` buffers. The faster Arm-accelerated option remains correctly
ineligible because Pareto64 does not trade away the quality floor for speed.

## Evidence handling

The native workflow captured every quality and benchmark cell, then failed in
post-processing because a llama-bench metadata log contained one non-UTF-8
byte. The workflow's runtime gate had already read the same log with replacement
decoding and passed. The ingester now applies that byte-tolerant treatment to
diagnostic logs; its frozen hashes, model inputs, tasks, policy, and acceptance
rules are unchanged.

Independent Python 3.10 ingestion of the untouched artifact produced the
retained manifest at SHA-256
`54adb3d4317e7a33c08c3bc59a4d534c5b5c6952a1dcc9a01b93e87a445aff9c`.
The derived selected plan has SHA-256
`657188c8ae583e88c8f3907e3a8d16650a16a7b56c0ddfd5b467821b071866de`.
Raw evidence remains in the 90-day artifact
`e3f-ministral3-frontier-30656151957-1`.

Clean reproducibility run
[`30657209779`](https://github.com/Arshgill01/Arm/actions/runs/30657209779)
then passed the corrected workflow end to end in 11m44s from retained-result
commit `7fe068d`. It reproduced both stable scores and the selected candidate.
Independent ingestion matched the uploaded summary byte for byte at SHA-256
`268cc0ec71e3396758c49b1405025ef6b13a0652029d15d5b027ddd046fa6932`.

## Decision

Accept Q4_K_M as Pareto64's first deployment-eligible runtime package and
unlock the previously deferred inference launch/serving gate. Retain Q4_0 as a
measured speed/size near-miss and as direct proof that KleidiAI acceleration
alone cannot override application quality.

The compact records are
[`../manifests/e3f-30656151957.json`](../manifests/e3f-30656151957.json) and
[`../plans/e3f-cloud-quality.json`](../plans/e3f-cloud-quality.json).
