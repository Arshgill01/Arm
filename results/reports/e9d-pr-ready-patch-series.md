# E9d — local PR-ready patch-series validation

Status: **strict sanitizer gate failed; diagnostic rerun frozen**.

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
