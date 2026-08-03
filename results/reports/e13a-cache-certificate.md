# E13a fail-closed cache certificate

Native Arm run
[`30830903248`](https://github.com/Arshgill01/Arm/actions/runs/30830903248)
completed the frozen four-process temporal holdout with byte-exact outputs and a
large performance benefit, but it is **not admitted**. Six point-transition
warmup prompts were absent from the E9c calibration set and correctly failed
closed; the contract had predicted zero unknown fallbacks. That exact decision-
count gate fails, so the result remains `valid_cache_certificate_rejected`.

## Frozen controller

The complete retained E9c calibration classified an exact tokenized-prompt
SHA-256 as cache-safe only when every cache-off and cache-on response byte was
identical. This produced 44 certified fingerprints and four denied
fingerprints. Anything else was required to run uncached. No example was
selected manually and the rule was frozen before this run.

The holdout concatenated the complete 21-point E9c order into one 165-request
trace: 144 measured requests and 21 point-transition warmups. Four fresh E7c
Q4_K_M servers ran all-uncached, certificate, certificate, and all-uncached in
A–B–B–A order, for 660 total requests. The source, OpenSSL-off binary closure,
model, service arguments, workload, process counters and raw per-request
records are retained.

## Result

| Metric | All uncached | Certificate | Ratio / delta |
| --- | ---: | ---: | ---: |
| Aggregate throughput | 0.430143 req/s | 0.794752 req/s | **1.84765x** |
| p95 HTTP latency | 3,343.90 ms | 3,033.45 ms | **0.90716x** |
| Server CPU seconds/request | 9.22730 | 4.98903 | **0.54068x** |
| Maximum process RSS | 4,538,440 KiB | 4,538,476 KiB | +36 KiB |
| Maximum readiness | 2,535.73 ms | 2,534.44 ms | −1.29 ms |
| Request failures | 0 | 0 | exact |

Both baseline repetitions were byte-identical. Both controller repetitions
were byte-identical, and all 330 controller responses matched their uncached
counterparts byte for byte. Certified measured requests achieved a 100% cache-
hit fraction. Throughput CV was 0.0537% for the baseline and 0.0444% for the
controller, comfortably below the frozen 5% ceiling.

The observed controller decision counts were identical in both repetitions:

| Decision | Frozen expectation | Observed |
| --- | ---: | ---: |
| Certified cache | 149 | 143 |
| Calibrated fallback | 16 | 16 |
| Unknown fallback | 0 | 6 |

The six differences were point-transition warmup fingerprints, not failed or
misrouted measured requests. The controller behaved safely: every unknown ran
uncached, as did every calibrated denial. The actual total fallback rate was
22/165, or 13.33%, versus the frozen 16/165 expectation.

## Decision

Every quality, failure, cache-mechanism, throughput, latency, CPU, stability,
startup and RSS gate passed. Only `frozen_decision_counts` failed. The gate is
not edited after observation and the policy is not promoted from E13a.

A defensible successor may use a separately frozen temporal trace whose
transition warmups are themselves calibration-known fingerprints, or may
predeclare the mechanically derived unknown fallback count. It must retain the
same byte-exact output requirement, 1.70x throughput floor, latency/CPU non-
regression gates, fail-closed unknown policy and fresh native execution. E13a
will remain a negative result regardless of any successor.

## Reproducibility

Artifact `e13a-cache-certificate-30830903248-1` (ID `8863474213`, SHA-256
`9ab64a27b3ecd62b147dc60af5dc0f5e041850f0b5268e05a63fdcbfb0718b5b`)
contains 95 uploaded entries, including the contract, exact calibration,
source/build/binary/dependency closure, four fresh-process cells and every raw
request. Independent local ingestion reproduced the workflow summary byte for
byte at SHA-256
`495e0c4202302db380ab3fafb5da534fbdafac40dccd5588821e738b65c609db`.
The retained machine-readable
[`manifest`](../manifests/e13a-30830903248.json) records the artifact digest,
file inventory and exact rejection.
