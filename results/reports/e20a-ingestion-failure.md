# E20a graph-node profile ingestion failure

Native GitHub Arm64 run
[`30863505489`](https://github.com/Arshgill01/Arm/actions/runs/30863505489)
built the exact instrumented OpenSSL-off runtime, completed all six frozen
control/timed benchmark cases, and reproduced exact selected-service quality.
The workflow remains **invalid** because independent ingestion stopped before
writing its summary or inventory.

## Exact failure

`llama-bench` reported 2,138,615,808 model bytes—the tensor-data size—while the
validator compared it with the already SHA-256-verified 2,146,497,824-byte GGUF
file size. That metadata-semantics mismatch rejected `pp512_control`. After
correcting the assumption, deterministic replay exposed a second parser issue:
one legitimate skipped `GET_ROWS` node had extent `3072,0,1,1` and zero elapsed
microseconds. The fixed parser accepts non-negative extents while retaining the
frozen requirement for at least 100 positive timing records per timed case.

The source artifact `e20a-cpu-node-timing-30863505489-1` (ID `8875743768`,
digest
`sha256:8b7da293603cb229e0d0aa1164c19d1d3521ab0f6353ae56f2a6a90524a53247`)
contains 90 independently hashed files and 46,815,191 uncompressed bytes. The
[failure manifest](../manifests/e20a-ingestion-failure-30863505489.json) binds
the failed run/job/artifact, exact contract, completed steps, raw controls,
timed traces, quality pass, traceback, and full extracted-file inventory.

## Frozen recovery boundary

A local Python 3.12 deterministic replay produced summary SHA-256
`24d3ca5b8b5014ec2d0095f0a6fc44ac5db93ef3fea081481d362b4b6a36c823`.
It previewed exact 23/30 quality with zero failures and mechanically selected
the FFN gate/up family: 31.43% software-timed share at pp512, 10.85% at pp4096,
and 26 shared-activation layers in both shapes. Attention Q/K/V missed the
long-prompt share gate at 4.00%. This preview does not authorize source work.

The separately frozen
[recovery contract](../../experiments/e20a_ingestion_recovery_contract.json)
may only verify the exact 90-file artifact and run the corrected selector under
Python 3.12.13. It forbids builds, model downloads, server or benchmark
launches, repeated quality requests, and threshold changes. The timed traces
remain diagnostic—not performance, PMU, cache, energy, fleet, or cost evidence.
