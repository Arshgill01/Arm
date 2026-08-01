# E7a LTO service and runtime-footprint ablation

Native run [`30692292700`](https://github.com/Arshgill01/Arm/actions/runs/30692292700)
completed the frozen `GGML_LTO=OFF` versus `ON` comparison on a four-core
Neoverse N2. Both profiles used exact three-patch llama.cpp `b10216`, GCC 13.3,
native/KleidiAI Release settings, the selected Ministral Q4_K_M model, and the
same repacked f16/256/64 cached four-thread one-slot service. Four fresh servers
ran in off–on–on–off order.

## Result

This is a valid no-win. LTO reproduced exact quality and passed every common
guardrail, but cleared neither predeclared benefit branch. `GGML_LTO=OFF`
remains selected.

| Profile | Median throughput | Pooled median / p95 HTTP | Median server CPU seconds/request | Median readiness | Max RSS | Local runtime closure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LTO off | 0.92427 req/s | 1,063.07 / 1,866.12 ms | 4.27683 s | 2,508.39 ms | 4,453,472 KiB | 20,059,048 bytes |
| LTO on | 0.92554 req/s | 1,054.21 / 1,867.90 ms | 4.27483 s | 2,582.54 ms | 4,453,444 KiB | 19,903,600 bytes |

LTO delivered only 1.00137x throughput and reduced the eight-file transitive
build-local runtime closure by 155,448 bytes, or 0.775%. The performance branch
required at least 1.03x throughput; the footprint branch required at least a 5%
closure reduction while retaining 98% throughput. Neither threshold moved after
observation.

All shared protections passed: median latency improved 0.833%, p95 increased
only 0.096%, measured server CPU seconds/request improved 0.047%, readiness was
1.0296x baseline, and maximum RSS decreased 28 KiB. Both repetitions of each
profile reproduced the selected 23/30 prediction map with stable predictions,
zero reference mismatches or request failures, and prefix reuse in every
measured request.

## Build and footprint proof

The full Ninja command inventories show `-flto` only in the candidate. LTO-off
and LTO-on builds took 222.25 and 213.77 seconds respectively, a 0.9618x ratio;
build time is a promotion cost, not an optimization claim. Peak build-process
RSS was 2,726,624 and 2,805,348 KiB.

For each profile, the raw artifact retains the server and every unique shared
library that `ldd` resolved under that build root. It records the raw dependency
inventory, resolved paths, copied bytes, sizes, and SHA-256 values while
excluding system libraries. The independent ingester verified all eight copied
files and totals before making the decision.

## Validation boundary

E7a establishes only that whole-program LTO is not material for this exact
patched native Arm fast service under the frozen gates. It is not evidence about
another model, service, compiler, backend, energy, or the full upstream matrix.
No product launch integration is warranted for a rejected profile.

Python 3.10 independent re-ingestion reproduced the uploaded summary byte for
byte at SHA-256
`b48e6c129d1f3305c2b788b422bc5321cd415b2bc2b26460804063ebc3b46839`.

See the frozen [`E7a contract`](../../experiments/e7a_contract.json), retained
[`manifest`](../manifests/e7a-30692292700.json), and native
[`workflow`](../../.github/workflows/lto-service.yml).
