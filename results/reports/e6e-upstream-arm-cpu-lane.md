# E6e — upstream-equivalent native Arm CPU lane

Status: **valid upstream-equivalent Arm CPU lane**.

## Result

[GitHub Actions run 30676413765](https://github.com/Arshgill01/Arm/actions/runs/30676413765)
completed in 6m16s on a native four-core Neoverse N2. It applied the frozen
three-patch series to llama.cpp tag `b10216`, commit
`876a4321163249c43ca4e986818fab5ab081f282`, then mirrored the upstream
`build-cpu.yml` `ubuntu arm64` lane with GCC/G++ 14. KleidiAI was explicitly
enabled so the Arm-specific source path remained in scope.

The complete Release default target built with fatal warnings, native tuning,
RPC, and all tests enabled. CTest then passed all 46 tests carrying the upstream
`main` label plus its required model-download fixture: **47/47 total**, with
zero failures, errors, or skips. The three patch-adjacent tests were present and
clean:

- `test-reasoning-budget`;
- `test-quantize-fns`; and
- `test-quantize-perf`.

The test lane completed in 35.03 seconds. Timing is diagnostic only; E6e has no
performance threshold or model-inference claim.

## Independent verification

The downloaded artifact was passed through a separate local invocation of
`experiments/e6e_ingest.py`. It reproduced the uploaded compact summary byte
for byte at SHA-256
`63c0e450d967208e3eb81d21571c73354e8520940933434914920db5d63c27f1`.
Every frozen criterion is true and no weighted score is used.

## Decision and limits

Accept one upstream-equivalent native Arm CPU build/test lane for the frozen
current three-patch series. This materially broadens the targeted E6d result,
but it is not the full llama.cpp cross-platform, sanitizer, accelerator,
packaging, or release matrix. It adds no whole-model quality, throughput,
energy, or cost claim, and no external pull request has been opened.

Raw evidence remains in the 90-day artifact
`e6e-upstream-arm-cpu-lane-30676413765-1`; the permanent compact record is
[`../manifests/e6e-30676413765.json`](../manifests/e6e-30676413765.json).
