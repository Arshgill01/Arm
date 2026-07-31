# Source patches

Patches are kept as reviewable experiment inputs, not silently embedded forks.
Every patch must identify the exact upstream revision, reproduce the unpatched
behavior, apply with `git apply --check`, and pass a native before/after workflow
before it can enter the product path.

## llama.cpp validated Arm feature selection

[`llama.cpp/0001-kleidiai-use-validated-arm-features.patch`](llama.cpp/0001-kleidiai-use-validated-arm-features.patch)
targets tag `b7870` / commit
`eed25bc6b052c363aa760d0055282cc2222ccf6e`, the llama.cpp revision pinned by
LLM-Runner commit `8ba39e40fa754b87deb99a998c31de3b850094d5`.

The upstream CMake already compiles authoritative `HAVE_DOTPROD`, `HAVE_SVE`,
`HAVE_MATMUL_INT8`, and `HAVE_SME` probes using the final architecture flags.
KleidiAI source selection ignores those results and searches flag text instead.
On the native Neoverse N2 runner, the final flags contain SVE2 modifier names
but end in `+nosve`; the substring search nevertheless includes SVE assembly,
which the final compiler flags reject.

The patch uses the existing validated feature results directly. It adds no new
runtime branch, dependency, or feature assumption. Native E6a validation passed;
no external pull request has been opened.

## llama.cpp Arm Q8 vector narrowing stores

[`llama.cpp/0002-arm-q8-vector-narrowing-stores.patch`](llama.cpp/0002-arm-q8-vector-narrowing-stores.patch)
targets the same pinned llama.cpp revision. In `quantize_row_q8_0`, the existing
NEON path extracts four lanes from each of eight `int32x4_t` values and writes
32 scalar bytes. The patch uses narrowing intrinsics and two vector stores while
leaving scale calculation and float-to-integer conversion unchanged.

GCC 15 cross-assembly preflight reduced static instructions from 124 to 69 and
stores from 36 to 3. An Arm-emulated finite-input equivalence test was
byte-identical. Native performance, upstream tests, emitted assembly, Qwen task
outputs, and end-to-end inference remain governed by the frozen E6b workflow;
the preflight alone does not authorize a speedup claim.
