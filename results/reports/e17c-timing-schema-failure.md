# E17c 8K-context density: terminal timing-schema failure

Native GitHub Arm64 run
[`30867998030`](https://github.com/Arshgill01/Arm/actions/runs/30867998030)
attempted all nine frozen four/eight-slot cells. Every cell's fresh server wrote
a successful readiness record, but every probe aborted before writing its
output because the retained response timing shape did not satisfy the probe's
required `encode_ms` contract.

## Failure

The job log contains the same terminal exception nine times:

```text
ValueError: invalid E17b encode_ms
```

Each cell therefore returned caller status 1 and contains no `probe.json`. The
final ingester correctly refused to treat the f16 four-slot controls as served:

```text
ValueError: E17c f16 four-slot control did not serve
```

This is an invalid experimental outcome, not a negative K/V performance result.
Partial server logs cannot establish exact answers, request failures,
throughput, latency, CPU efficiency, or four/eight-slot density. Readiness and
process files are retained only as execution evidence and are not compared.

## Decision

No K/V configuration is promoted. E17b remains invalid, E17c makes no 8K or
16K viability claim, and the current long-context K/V lane is parked. No rerun
or successor is authorized by this evidence-hardening phase.

## Retained evidence

The [failure manifest](../manifests/e17c-30867998030-failure.json) binds source
commit `4021e21d0d656685559933781e3eedc266eb0e3d`, exact E9a runtime and Q4_K_M
model identities, all frozen inputs and recipes, all nine caller failures, the
failure log, job `91863877220`, artifact ID `8879497249`, and artifact digest
`sha256:069ba1b3e79f21c2609b8478cf9e91607523852e6aa5c3c1098f97361610eb31`.
All 144 artifact files hash to canonical inventory
`5684d38c4e760fe0a5d34c9ea20fd85a32857f76d62962317667e198a44e28d2`.

The manifest makes no quality, throughput, latency, CPU, K/V density, 8K,
16K, energy, PMU, device, fleet, or cost claim.
