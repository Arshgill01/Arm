# E18a instrumented-training timeout

Native GitHub Arm64 run
[`30858852227`](https://github.com/Arshgill01/Arm/actions/runs/30858852227)
completed both compiler builds and all twelve fresh-process service cells, but it
is **not a valid PGO comparison**. Independent ingestion rejected the frozen
profile-generation prerequisite before reading the service result.

## Exact failure

The GCC `-fprofile-generate` server was far slower than the normal service. Both
warmups exceeded the frozen 30-second request timeout. Of the 30 measured
training requests, only `arithmetic-02` and `logic-01` returned successfully;
the other 28 timed out. The two completed responses were correct, but a 2/30
profile-training pass does not satisfy the exact workload or quality contract.

The run did produce 305 `.gcda` files totaling 4,668,884 bytes, built the PGO-use
binary in the same directory, and completed the reverse-balanced 12-process
matrix. Those later measurements are deliberately ineligible: they were trained
from an incomplete and timeout-distorted profile, so they cannot answer the
frozen hypothesis and are not reported as performance evidence.

## Retained boundary

The always-upload artifact
`e18a-workload-pgo-30858852227-1` (ID `8874332881`, digest
`sha256:a182313fe7a1c0fd2557daadcec71b043ada74de3446c173644974f00727dbf1`)
contains 497 independently hashed files and 48,167,886 uncompressed bytes. The
[machine-readable manifest](../manifests/e18a-training-timeout-30858852227.json)
binds the exact contract, run, job, artifact, native host, training requests,
profile inventory, completed-step boundary, and validation error.

A successor may change only the non-performance instrumented-training request
timeout. It must preserve the source, model, compiler flags, exact 30-task
training pass, service, build directories, twelve-cell order, repetitions,
acceptance gates, and claim boundary. This failed run is not rehabilitated.
