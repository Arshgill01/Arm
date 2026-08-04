# E17b frozen 16K long-context failure

Native GitHub Arm64 run
[`30857705994`](https://github.com/Arshgill01/Arm/actions/runs/30857705994)
attempted all nine frozen 14.5K-token retrieval cells on a four-vCPU
Neoverse-N2 runner. The result is a retained contract failure, not a valid
quality or performance comparison.

## Result

All six four-slot cells and both quantized eight-slot cells reached readiness,
then every one of their eight requests exceeded the unchanged 600-second
per-request limit. Four-slot cells used two request waves and ran for
1,236.65--1,301.26 seconds; eight-slot quantized cells used one wave and ran
for 656.94--669.37 seconds. No probe summary was written, so no answer,
throughput, or comparative latency result is inferred from the partial work.

| Configuration | Slots | Attempts | Observed KV allocation | Terminal outcome |
| --- | ---: | ---: | ---: | --- |
| f16/f16 | 4 | 2 | 6,656 MiB | Both timed out |
| q8_0/q8_0 | 4 | 2 | 3,536 MiB | Both timed out |
| q4_0/q4_0 | 4 | 2 | 1,872 MiB | Both timed out |
| q8_0/q8_0 | 8 | 1 | 7,072 MiB | Timed out |
| q4_0/q4_0 | 8 | 1 | 3,744 MiB | Timed out |
| f16/f16 | 8 | 1 | allocation failed | 13,312 MiB KV request exceeded the 15 GiB process ceiling |

The quantized KV configurations substantially reduced allocation, but this
run cannot promote either one: the frozen contract required exact answers and
service gates from completed requests. The failed contract remains failed and
no 16K viability claim is allowed. A separately frozen shorter-context study
may use this result only as its predecessor and must not be presented as 16K
evidence.

## Evidence boundary

The [retained failure manifest](../manifests/e17b-30857705994-failure.json)
binds run, job, commit, model, exact E9a runtime closure, artifact ID
`8876259597`, artifact digest
`sha256:0bb55a72d63b86825aba6d119a798f0b398045f5aa2302ff7183ec8d1b94c65b`,
all nine cells, and a 144-file independently hashed artifact inventory. It
establishes only the timeout and f16 allocation failures on this runner; it
makes no answer-quality, speed, energy, PMU, device, fleet, or cost claim.
