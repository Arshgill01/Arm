# E10b first-run harness failure

Native run
[`30797017450`](https://github.com/Arshgill01/Arm/actions/runs/30797017450)
retained a recoverable failure before any E10b warmup or measured request. The
two-logical-CPU Neoverse N2 runner verified every frozen input, checked out exact
llama.cpp b10216, applied the retained four-patch diff, verified its hash,
downloaded the exact selected Q4_K_M model, built the OpenSSL-off service with
native GCC, captured its eight-file runtime closure, and reached readiness in
2,528.90 ms.

The first probe then passed the frozen E10a contract path to a shared JSON
loader as a string, although that loader requires `pathlib.Path`. Python raised
`AttributeError: 'str' object has no attribute 'read_text'` before the warmup.
No full-vocabulary response, selected-token response, latency, payload, or
parity result was observed, so this is a harness representation defect rather
than a source-primitive result.

The repair converts the already frozen path string to `Path` and adds a focused
regression test that loads the real prompt-construction input. The workload,
model, source patch, cell order, repetition count, response retention, and every
acceptance gate remain unchanged. The 90-day artifact
`e10b-exact-token-probabilities-30797017450-1` preserves the native build and
partial run; the compact
[`manifest`](../manifests/e10b-preflight-30797017450.json) records the blocker
and evidence hashes.
