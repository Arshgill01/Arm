# E6a — validated native Arm feature selection

Status: **valid source-correctness fix; not a speedup result**.

## Result

[GitHub Actions run 30636911078](https://github.com/Arshgill01/Arm/actions/runs/30636911078)
completed the frozen before/after contract in 6m03s on a four-core Neoverse N2.
The independent ingester accepted the exact source revisions, frozen contract,
patch checksum, failure signatures, clean-build evidence, functional test,
runtime-backend proof, and benchmark record.

| Gate | Evidence | Outcome |
| --- | --- | --- |
| Unpatched reproduction | Exit 2; `sve_dotprod_asm.S`; unsupported SVE instructions | passed |
| Patch identity | Applied diff exactly matches frozen SHA-256 | passed |
| Clean patched build | All generated objects cleaned, then full build exit 0 | passed |
| Source selection | DotProd/I8MM KleidiAI sources built; invalid SVE sources absent | passed |
| Functional behavior | Pinned upstream Phi-2 test, 1/1 | passed |
| Runtime backend | `CPU_KLEIDIAI model buffer size` observed | passed |
| Real inference | Three complete 32-token measurements, process exit 0 | passed |

## Root cause and patch

llama.cpp first compiles architecture-macro probes under its final flag set. In
the failing configuration, `HAVE_SVE` correctly failed and the final native flag
ended in `+nosve`. The later KleidiAI block discarded that result and searched
the flag text for `+sve`. Earlier modifiers such as `+sve2-sm4` satisfied the
substring search, so SVE assembly was added even though the final compiler state
disabled SVE.

The patch removes four text searches and uses the existing authoritative values:

- `HAVE_DOTPROD`
- `HAVE_MATMUL_INT8`
- `HAVE_SME`
- `HAVE_SVE`

It adds no new probe, dependency, runtime branch, or architecture assumption.
The exact patch is
[`../../patches/llama.cpp/0001-kleidiai-use-validated-arm-features.patch`](../../patches/llama.cpp/0001-kleidiai-use-validated-arm-features.patch).

## Patched inference smoke

The benchmark uses the same pinned Phi-2 artifact and 64-input/32-output,
four-thread contract as E1. Medians and nearest-rank p95 include all three
measured iterations.

| Metric | Median | p95 |
| --- | ---: | ---: |
| Prompt processing | 113.847 tokens/s | 113.920 tokens/s |
| Token generation | 22.748 tokens/s | 22.935 tokens/s |
| Time to first token | 605.278 ms | 613.691 ms |
| Total iteration | 1,977.464 ms | 2,075.659 ms |

Whole-process wall time was 8.95 s and maximum RSS was 3,243,392 KiB. These
numbers are a functional smoke measurement. The unpatched configuration cannot
build, so E6a has no paired performance baseline and makes no speedup claim.

## Limits

LLM-Runner deliberately applies an SVE-free `Armv8.6_1` target while this test
also enables llama.cpp native detection to reproduce the integration defect.
E6a proves source selection follows the final validated compiler state; it does
not establish whether SVE should be enabled for a different deployment target.

The legacy Phi-2 GGUF still emits the missing-pre-tokenizer quality warning, so
the successful functional test does not authorize a generation-quality claim.
Hosted-runner PMU, energy, and governor limitations also remain. Current
llama.cpp has evolved around the patch context, so an upstream contribution must
be rebased and retested at current HEAD before submission.

Raw evidence remains in the 90-day artifact
`e6a-native-feature-fix-30636911078-1`; the validated compact record is
[`../manifests/e6a-30636911078.json`](../manifests/e6a-30636911078.json).

## Decision

Accept the patch as a reproducible source-correctness contribution and retain it
in Pareto64's evidence pipeline. Do not count it as the performance-oriented E6
finish line: E6b still needs a stable hot path, paired native measurements,
mechanism or assembly evidence, and an unchanged quality result.
