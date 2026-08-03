# E10a cache-divergence calibration

Status: **preflight failure retained; calibration result not observed**.

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
