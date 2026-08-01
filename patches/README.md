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
byte-identical. Native E6b then passed the upstream quantizer tests and showed
2.001x–2.029x paired throughput across all three tested sizes. Native emitted
assembly removed all 32 scalar byte stores, all frozen Qwen task outputs stayed
identical, real-model inference stayed within its 0.98 guardrail, and peak RSS
was unchanged. The exact evidence and claim boundary are in
[`../results/reports/e6b-q8-vector-store.md`](../results/reports/e6b-q8-vector-store.md).

## llama.cpp reasoning-budget forced-token guard

[`llama.cpp/0003-reasoning-budget-forced-token-guard.patch`](llama.cpp/0003-reasoning-budget-forced-token-guard.patch)
targets current tag `b10208` / commit
`9d9a6d29f6b981cc7f41983d26e56485c6af1811`. E3e showed that Qwen3.5 budget 0
incorrectly consumed its entire output cap as reasoning instead of forcing an
immediate end. The sampler advanced its forcing position for an unrelated
prefill newline without checking the accepted token.

The patch adds that equality guard and one exact regression test. On the
untouched source, the new test aborts at the expected forcing-state assertion;
with the guard, all 13 upstream reasoning-budget tests pass. This is local
functional preflight only. E6c now freezes the native source and real-model
correctness obligations; it must pass before the patch is considered validated.
No external pull request has been opened.

## Current llama.cpp rebase series

[`llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch`](llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch)
rebases the feature-selection correction onto tag `b10216` / commit
`876a4321163249c43ca4e986818fab5ab081f282`. The change is semantically
identical; only surrounding KleidiAI SME source-list context changed upstream.

The Q8 vector-narrowing patch and reasoning-budget guard apply to `b10216`
byte-for-byte with no rebase. E6d freezes the three-patch current-upstream
applicability, source-correctness, unit-test, assembly, and direct-performance
obligations. Native run `30675654688` passed all of them: both upstream
quantizer targets and all 13 reasoning tests passed after the complete series,
the invalid SVE selection disappeared, and all twelve paired direct Q8 rounds
improved. This is the current validated series; no external pull request has
been opened, and the broader upstream CI matrix has not yet run.
