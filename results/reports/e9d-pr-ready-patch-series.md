# E9d — local PR-ready patch-series validation

Status: **strict sanitizer gate failed; inherited b10216 test UB confirmed**.

## First native result

[Native Arm run 30772783697](https://github.com/Arshgill01/Arm/actions/runs/30772783697)
applied all three unpublished mail patches to exact llama.cpp b10216 commit
`876a4321163249c43ca4e986818fab5ab081f282`. The applied full-index diff was
byte-identical to the retained source diff at SHA-256
`e11cdd41091d5d76b973c67ffcc04429760fbef58c7a2bc971947b80900a9893`.
No upstream PR or mail submission was opened.

GCC 14 and Clang 18 both built and ran `test-quantize-fns` and the complete
13-test reasoning-budget suite successfully on the native two-core Neoverse N2
runner. Both compilers also passed the frozen KleidiAI
`armv8.6-a+sve2+nosve` feature-stress build without selecting
`sve_dotprod_asm.S`.

The strict Clang 18 ASan+UBSan build succeeded and the patched reasoning suite
again passed 13/13 with no ASan or leak diagnostic. `test-quantize-fns` exited
1, however, because UBSan reported a call to `ggml_vec_dot_f32` through an
incompatible function-pointer type at upstream `tests/test-quantize-fns.cpp:115`.
That test file is not in the four-file patch series. The strict gate therefore
remains failed; the result is retained as `invalid_pr_ready_patch_series` and
the series is not claimed sanitizer-clean.

## Harness defects and bounded diagnostic

The failed run also exposed two evidence-harness defects: CMake records
command-line compiler paths as `STRING`, not the frozen `FILEPATH` cache type,
and the ingester expected an object where the workflow emitted the three-entry
commit array. Provenance was also written too late to enter the failed raw
artifact. The retained first-run manifest records the immutable artifact and
locally reconstructed GitHub provenance explicitly; it does not relabel the
failure.

Contract revision 2 repairs those three evidence-path defects without removing
or changing any strict acceptance criterion. It additionally freezes one
pristine-b10216 run of the exact failing strict sanitizer target and one
non-gating patched run that excludes only UBSan's function-type check. The
first determines whether the strict diagnostic predates the patch series; the
second reports remaining ASan/UBSan coverage but cannot make the strict gate
pass. The revision-2 contract SHA-256 is
`0716dc065fc10b5eb2435b88ac83dcebd60fc16e549aa051b06482650a84b745`.

The raw first-run artifact is `e9d-pr-ready-patches-30772783697-1`, artifact ID
`8841260783`, 92,781 compressed bytes, retained until 2026-10-31. Its compact
record is
[`../manifests/e9d-30772783697.json`](../manifests/e9d-30772783697.json),
SHA-256 `9814c115e177a6bf87856f2df28d10e4ebdf71d0d093c2132dc68295ecc25016`.
This result adds no performance, energy, full-platform, later-source, review,
or merge-readiness claim.

## Diagnostic result and final decision

[Native Arm run 30773922751](https://github.com/Arshgill01/Arm/actions/runs/30773922751)
completed the revision-2 evidence path in 27m11s. A separate local ingestion
replay reproduced the runner's manifest byte for byte at SHA-256
`c6b29cf315cb921974cba1b1ea182014627ea74a053f8af9e6728201a72e6153`.

All non-sanitizer gates passed: exact three-way mail application, aggregate
diff identity, exact compiler binding, GCC and Clang native builds and tests,
and both forced feature-selection builds. The strict patched sanitizer lane
again built successfully, passed reasoning 13/13, and had no ASan or leak
diagnostic. It failed only the function-type UBSan check in
`test-quantize-fns`.

The pristine b10216 control then built the same target with the same Clang 18,
ASan+UBSan, native, leak-detection, and halt-on-error settings. It produced the
same upstream `ggml_vec_dot_f32` function-type diagnostic and exit 1. Because
`tests/test-quantize-fns.cpp` is absent from the applied four-file diff, the
manifest attributes the strict failure to inherited pristine-b10216 test UB.

The predeclared supplemental patched lane excluded only UBSan's function-type
check and retained AddressSanitizer, LeakSanitizer, and all remaining undefined
checks. Both targets passed, including reasoning 13/13, with no sanitizer
diagnostic. This is useful bounded evidence but is explicitly non-gating; it
does not replace the failed strict result.

E9d therefore closes as `invalid_pr_ready_patch_series`. The mail series is
prepared and exact, but it is not described as fully sanitizer-clean or ready
for publication. The diagnostic artifact is
`e9d-pr-ready-patches-30773922751-1`, artifact ID `8841707316`, 107,544
compressed bytes, retained until 2026-11-01. The retained diagnostic manifest
is [`../manifests/e9d-30773922751.json`](../manifests/e9d-30773922751.json).
