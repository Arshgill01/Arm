# Arm AI Optimization Challenge Lab

Research, experiments, and the eventual submission for the **Arm Create: AI
Optimization Challenge 2026**.

[![Native Arm submission validation](https://github.com/Arshgill01/Arm/actions/workflows/submission-validation.yml/badge.svg)](https://github.com/Arshgill01/Arm/actions/workflows/submission-validation.yml)

**[Open the public Native Arm64 evidence report ↗](https://pareto64-arm-evidence.arshgill01.chatgpt.site)**

The event asks entrants to create, migrate, or optimize an AI solution on Arm
architecture in one of three published tracks: Physical AI, Cloud AI, or Mobile
AI. The submission deadline is **August 14, 2026 at 4:00 PM PDT** (23:00 UTC;
August 15 at 04:30 IST).

## Final Cloud AI project

**Pareto64** is the final Cloud AI direction: a quality-constrained deployment
planner and verified launch path for Arm64 AI inference. Native feasibility,
quality, serving, and novelty gates have passed; rejected speedups and empty
frontiers remain part of the retained evidence.

The product core is now executable: it validates schema-1 E3, E3b, E3c, E3d,
E3e, or E3f evidence, applies explicit quality and SLO gates, recomputes the Pareto
frontier, and emits a hashed deployment decision without a hidden weighted
score.

The judge-facing package is available in [`submission/`](submission/), and the
dependency-free interactive evidence demo is in [`demo/`](demo/). Verify the
compact submission from a clean checkout with:

```bash
python3 scripts/verify_submission.py
python3 -m unittest discover -s tests -v
python3 -m http.server 4174 --directory demo
```

E3c and E3d measured exact quantizations of Apache-2.0 Qwen3-4B and Qwen3.5-4B.
Their best stable score was 66.67% under the unchanged 75% task floor, so no
inference adapter may launch from either result. E3e's predeclared bounded-
reasoning run was correctly rejected: budget 0 failed the runtime's documented
immediate-end mechanism. That failure exposed a reproducible upstream sampler
state bug; no E3e frontier or deployment plan is accepted. E6c validated the
exact source correction and zero-reasoning behavior on Arm, but its frozen
eight-token standalone-answer gate rejected the application run. E3f's
Ministral 3 Q4_K_M is the first candidate to clear the unchanged quality and
cloud SLO gates. A fail-closed launch adapter now binds that selection to the
exact model hash and pinned llama.cpp build. E5b validates native inference
serving with zero answer drift while rejecting a marginal two-slot tuning win.
E5c then preserves all 120 answers while quality-gated shared-prefix caching
raises repeated median throughput 1.672x and cuts median HTTP latency 41.3%.
E5d tests the combined cache-plus-concurrency setting and rejects two slots
again: only 1.0619x throughput with 93.3% higher median HTTP latency.
E5e then right-sizes the validated application context from 2,048 to 256 tokens,
reducing maximum process RSS by 183.36 MiB while preserving every answer and
99.62% of throughput. Lower-precision q4_0 KV cache was faster but changed a
stable answer, so the product promotes the f16 right-sized profile instead.
E5f then promotes a 64/64 logical/physical prompt batch: every answer remains
exact, the CPU compute buffer falls 75%, maximum RSS falls 14.48 MiB, and
throughput rises 2.26%. The intermediate 128/128 profile is rejected because
its process-RSS reduction misses the frozen 8 MiB gate.
E5g then tests the next staged boundary. A 32/32 batch halves the remaining
compute buffer and preserves every answer and performance gate, but maximum RSS
increases by 660 KiB. It is not promoted, 64/64 remains the default, and the
predeclared study stops before 16/16.
E5h then removes the Arm weight-repack buffer under a separate frozen contract.
The no-repack path preserves every answer and lowers maximum RSS by 2,072,268
KiB to 2,381,264 KiB, while throughput falls to 48.47% of the repacked service.
Repacking remains the fast default; `--no-weight-repack` is retained as an
explicit low-memory tier.
E5i finally ablates the selected service's resolved Flash Attention graph.
Auto preserves every answer, improves throughput 3.22% and median latency
6.18%, and saves 7,384 KiB RSS, but p95 latency rises 6.03%. It misses the
frozen 1.05x throughput and p95 non-regression gates, so no material Flash
Attention serving win is claimed.
E5j then challenges the four-thread serving default with measured-window Linux
server CPU counters. Three threads saves only 0.11% CPU seconds/request while
losing 24.48% throughput; two threads saves 1.36% while losing 48.82%. Both
preserve every answer but fail the frozen CPU-time, throughput, and latency
gates. Four threads remains the default, and CPU time is not presented as
energy.
E6d rebases the three Arm source contributions onto llama.cpp `b10216` and
revalidates them natively. The feature and reasoning failures reproduce before
their fixes, all targeted tests pass after the complete series, and all twelve
paired Q8 rounds improve by roughly 95%. Its claim remains bounded to this
frozen current revision, targeted correctness, and direct hot-path performance.
E6e broadens that proof through an upstream-equivalent native Arm CPU lane: the
complete fatal-warnings build passes with KleidiAI enabled, followed by 47/47
CTest executions without a failure, error, or skip. It is one validated Arm CPU
lane, not the full upstream platform and backend matrix.
E6f closes the selected-application gap with matched clean-`b10208` and
patched-`b10216` servers. Current source reproduces every selected answer twice,
retains 100.28% throughput, slightly improves median/p95 latency, and adds only
100 KiB maximum RSS. It passes the frozen upgrade gates for this exact service.
E6g then validates the explicit opt-in product path itself: on native Arm the
adapter verifies the retained E6f manifest, exact patched git diff, CMake
source/build relationship, server version and binary hash, launches the service,
and reproduces 23/30 with no drift or failures. Only the measured one-slot
repacked f16/256/64 four-thread profile is admitted; the unflagged historical
path and every unmeasured current-runtime profile remain unchanged.
E6h separately crosses the no-repack memory tier over that runtime boundary.
Patched b10216 reproduces 23/30 twice, retains 100.24% throughput, uses 99.85%
of baseline CPU seconds/request, stays below 3 GiB, and adds only 180 KiB RSS.
E6i then executes the separate evidence-bound product path: the adapter binds
E6h, the exact patched source/build/binary/model, and explicit no-repack recipe,
reproduces 23/30 with zero drift or failures, and stays at 2,381,040 KiB RSS.
Both measured current-runtime tiers are admitted only through their own exact
contracts. E7a then tests whole-program LTO on the exact fast service. It keeps
every answer and guardrail but gains only 0.137% throughput and shrinks the
transitive local runtime closure only 0.775%, so LTO remains off. E7b then
removes unused HTTPS support from the loopback-only build: exact quality and
99.981% throughput remain, while `libssl.so.3` and `libcrypto.so.3` disappear
without a replacement dependency. The HTTP-only profile now qualifies for a
separate evidence-bound launch integration. E7c executes that exact path on
native Arm: the adapter binds E7b, proves the OpenSSL-off cache and matching
13-library inventory, launches the service, and reproduces 23/30 with zero
drift or failures. HTTPS remains unchanged.
E9a finally compares that exact service against the earliest admitted E5b
one-slot recipe in one native Arm job. Across four reverse-balanced fresh
processes per profile, every answer stays exact while the final service reaches
**1.7168x throughput**, 0.5846x median latency, 0.7056x p95 latency, and
0.5806x CPU seconds/request. The runner exposed two logical CPUs, so these are
same-job ratios rather than cross-run absolute-throughput claims.
E9c then tests whether E5c's cache decision generalizes to one, two, and four
alternating prefixes at three frozen shared-prefix lengths. Cache reuse and all
performance gates pass at every point, with 1.9406x–2.4007x throughput ratios,
but the extended prompts produce 252 reference mismatches, including 204
non-standalone answers, plus 12 paired cache-state mismatches. Every generalized
policy is disabled; E5c remains bounded to its exact quality-gated workload.
E9d packages the exact b10216 source diff as an unpublished three-message mail
series and validates it under GCC 14 and Clang 18. Both native and forced
feature-selection lanes pass. Strict UBSan finds an incompatible function-call
test in upstream `test-quantize-fns`; the same failure reproduces on pristine
b10216, while a non-gating lane excluding that one check passes all remaining
ASan/UBSan/leak and reasoning tests. The strict result stays failed, so no
sanitizer-clean or publication-readiness claim is made.
E9e then stops the final speculative/cross-runtime fallback before measurement.
Exact b10216 loads the target path in its draft-model initializer, the frozen
service emits only two generated tokens per retained request, and LLM-Runner's
independent backends cannot consume the selected GGUF Q4_K_M identity. License
review passes, but mechanism, model-equivalence, and workload gates do not; no
benchmark or portability claim is manufactured.
E10a then asks whether cached top-1 margin can guard E9c's output drift. The
native calibration reproduces four drifted pairs, but their maximum cached
margin (0.02794) overlaps stable pairs down to 0.01221. The required strict gap
is negative, so no threshold or holdout is selected. E10b instead addresses the
candidate-scoring API boundary with a bounded exact-token probability selector.
On native Arm, A/B/C/D probabilities match the full 131,072-token response
within 3.58e-7, sampled output stays identical, median payload falls from 12.57
MB to 2.78 KB, and median HTTP latency falls 18.6%. This promotes only the
response primitive for a separately frozen multi-token evaluator.
E10c tests the tempting one-request forked scorer but rejects it: predictions
match the serial adapter, yet all three frozen numerical log-probability parity
gates fail. E10d therefore uses the validated serial primitive for the pinned
300-sample external holdout. Both model cells complete their sample loops but
fail the zero-request-failure gate when one-token responses omit a required
probability entry: one failed sample for Q4_K_M and two for Q4_0. The aggregate
is invalid, partial task metrics are non-comparable, and the original E11a/E12b
prerequisites remain blocked. Exact breakpoints and all 28,490 retained raw
responses are preserved for a separately frozen compatibility preflight.
E10e then reproduces both Q4_0 breakpoints on native Arm and completes their
42- and 29-token continuations twice by forcing sampled token 1046 (`.`) while
reading each original target's raw pre-sampling score. Both the maximum
original-prefix delta and 71-score repeat delta are exactly zero. This validates
only the compatibility mechanism and authorizes a separately frozen full
successor; failed E10d remains failed.
E10f runs that separately frozen safe-sampled successor over the full 300-sample
holdout for both quantizations. All 28,748 token-score responses succeed. On
ARC Easy, HellaSwag, and WinoGrande, Q4_K_M records 73%/49%/57% raw accuracy
versus Q4_0's 72%/48%/60%; normalized ARC Easy and HellaSwag are 59%/72% versus
61%/71%. The mixed result is supplemental robustness evidence, not a rewritten
admission gate. It satisfies only E10f's generated-quant prerequisite; E12a
must still pass independently.
E13a then tests a fail-closed exact-fingerprint cache certificate on a fresh
660-request temporal holdout. All controller outputs match uncached bytes,
throughput rises 1.84765x, p95 latency falls to 0.90716x, and CPU
seconds/request falls to 0.54068x. The contract is still rejected: six
point-transition warmup fingerprints correctly route through unknown fallback,
while the frozen decision inventory predicted zero. Every other gate passes,
but the count gate remains unchanged and the policy is not promoted.
E13b freezes a separate reversed temporal trace whose transition warmups are
all mechanically calibration-known. It reproduces every uncached byte, routes
the predeclared 146/19/0 certified/calibrated/unknown decisions in both traces,
and reaches 1.85158x throughput with 0.94427x p95 and 0.53934x CPU/request.
This admits only that exact certificate boundary; missing fingerprints still
fail closed. E14b then repairs only E14a's log verbosity and validates the
four-point selective-repack frontier. Both selective points miss the unchanged
joint 80%-throughput/40%-extra-RSS product target, so full repack remains the
selected service and the experimental hook is not promoted.
E16a then verifies the persistent-prepack prerequisite instead of assuming it:
two fresh native Arm processes independently produce the same complete
2,139,013,120-byte, 183-tensor sidecar from different runtime addresses and
preserve 23/30 exactly. The result authorizes a separately frozen fail-closed
loader experiment; it makes no loader, startup, RSS, PSS, or performance claim.
E16b's repaired loader retains exact single-process performance and cuts
same-job median readiness 62.03%, but leaves RSS and PSS unchanged. E16c then
tests the missing multi-process boundary: two workers sharing one read-only
sidecar save 2,091,714 KiB of summed PSS (30.69%) at 1.00044x aggregate
throughput with every answer unchanged. This is a physical-sharing claim, not
a per-process RSS or cold-storage claim. Separately, E15b's exact two-CPU
confirmation rejects asymmetric 2/4 scheduling: its 1.00427x throughput comes
with exactly 1.00000x CPU seconds/request and misses the frozen efficiency gate.

## Optimization map

The measurements below come from separate frozen native Arm contracts; effects
are not added together. Quality means exact selected-task predictions were
preserved unless the row explicitly describes a rejected candidate.

| Front | Baseline | Technical change | Measured result | Product decision |
| --- | --- | --- | --- | --- |
| Model/quality | 2.05 GB KleidiAI Q4_0, 70% | Quality/SLO-gated package search | Q4_K_M reached 76.67% at 2.15 GB; the 29%-faster model failed quality | Select Q4_K_M; reject speed without task quality |
| Prompt work | Cache disabled, 0.5378 req/s | Reuse the verified shared chat prefix | 0.8991 req/s (**1.672x**); median latency 1,807.0 → 1,061.6 ms | Enable prompt caching |
| KV memory | 2,048-token f16 context, 208 MiB KV | Bound context to the 135-token application maximum | 256-token f16 uses 26 MiB KV and saves **183.36 MiB RSS** at 99.62% throughput | Promote 256/f16; reject q4_0 answer drift |
| Prompt graph | 256/256 batch, 40.13 MiB buffer | Split prompt work into 64/64 batches | 10.03 MiB buffer (**75% lower**), 14.48 MiB less RSS, 1.0226x throughput | Promote 64/64; stop when 32/32 adds RSS |
| Arm weight layout | Repack on, 4,453,532 KiB RSS | Expose verified `--no-weight-repack` envelope | **2,072,268 KiB less RSS**, with throughput reduced to 48.47% | Keep fast default; route ≤3-GiB hosts to memory tier |
| Thread efficiency | 4 threads, 4.2682 CPU s/request | Test 3 and 2 threads with post-warmup process counters | Only 0.11% / 1.36% CPU-time savings; throughput falls 24.48% / 48.82% | Keep 4 threads; make no energy claim |
| Arm Q8 kernel | 32 scalar byte stores, 5.09 GB/s | NEON narrowing plus two vector stores | 10.33 GB/s (**2.029x**) with bit-identical output and neutral model inference | Accept bounded hot-path win |
| Source robustness | Historical pinned patches | Rebase all three fixes to llama.cpp b10216 | Targeted gates passed, then complete build plus **47/47** executed tests | Validate one upstream-equivalent Arm CPU lane |
| Application runtime | Clean b10208 selected service | Run and provenance-bind the exact service on patched b10216 | 23/30 twice in comparison, then 23/30 through the adapter with zero drift or failures | Admit only the exact E6g-validated integration |
| Memory-tier runtime | Clean b10208 no-repack service | Compare, provenance-bind, and launch the same ≤3-GiB tier on patched b10216 | 23/30 twice at 1.0024x throughput, then 23/30 through the adapter at 2,381,040 KiB RSS | Admit only the exact E6i-validated integration |
| Compiler/build | Patched b10216 fast service with LTO off | Enable upstream whole-program LTO and hash both transitive local runtime closures | Exact quality; **1.0014x** throughput; closure only **0.775% smaller** | Keep LTO off; retain the valid no-win |
| HTTP dependency surface | Patched b10216 loopback service with HTTPS support linked | Disable unused `LLAMA_OPENSSL`, inventory the full dynamic closure, then launch through the E7b-bound adapter | Removes exactly `libssl.so.3` + `libcrypto.so.3`; adds none; **0.9998x** throughput; E7c reproduces 23/30 with a matching 13-library inventory | Integrate only the exact OpenSSL-off HTTP service; keep HTTPS unchanged |
| Final compounded service | Earliest admitted E5b one-slot recipe | Exact E7c source/build/cache/context/batch/dependency recipe | **1.7168x** throughput; 0.5846x median latency; 0.5806x CPU seconds/request; exact answers in all eight cells | Accept the end-product delta; use isolated experiments for attribution |
| Alternating-prefix cache boundary | Exact E7c cache off/on over 1, 2, or 4 prefixes and 16/32/64 shared tokens | Frozen 36-process generalization matrix | 1.9406x–2.4007x throughput ratios, but 252 reference mismatches and 12 paired cache-state mismatches | Disable all generalized policies; keep E5c workload boundary |
| Unpublished patch-series hardening | Exact retained b10216 three-patch diff | Three-way mail replay, GCC 14, Clang 18, feature stress, strict and controlled sanitizers | Compiler lanes pass; strict UBSan failure reproduces on pristine b10216; non-gating scoped lane passes | Retain exact mail series; do not claim fully sanitizer-clean or publication-ready |
| Speculative / cross-runtime feasibility | Exact E7c model, runtime, and 30-task workload | Preflight exact mechanism, model identity, workload fit, licenses, and storage | License/storage pass; exact-runtime draft loading, two-token completions, and non-portable backend artifacts fail required gates | Stop before measurement; add no performance or portability claim |
| Cache-confidence guard | E9c-exposed 64-token cache drift | Calibrate cached top-1 margin before any threshold or holdout | Four drifted pairs reproduce, but margins overlap stable pairs; strict separation gap is −0.01573 | Reject a margin-only guard; select no threshold |
| Exact-token probability response | Full 131,072-entry pre-sampling response | Select four known token IDs from the same softmax | Maximum log-probability delta 3.58e-7; identical sample; response 0.000221x and median HTTP latency 0.8144x | Promote only the response primitive for a separately frozen evaluator |
| Forked candidate-scoring request | Validated serial exact-token adapter | Score all candidate continuations in one server request | Predictions match, but every frozen numerical parity gate fails | Reject the scorer; preserve the native negative result |
| Pinned external holdout | Exact serial scorer over 300 preselected samples per model | Evaluate Q4_K_M and Q4_0 on ARC Easy, HellaSwag, and WinoGrande | Both cells hit missing one-token probability entries; paired aggregate skipped | Reject the comparison; retain all partial/raw evidence and test compatibility separately |
| Probability serialization compatibility | Exact two failed Q4_0 continuations | Force one-byte sampled token 1046 while reading each original target's raw score | Both continuations complete twice; original-prefix and repeat deltas are 0.0 | Permit only a separately frozen full successor; do not rehabilitate E10d |
| Safe-sampled external holdout | Exact Q4_K_M and Q4_0 over the pinned 300-sample workload | Use E10e's one-byte safe sample while reading each target's pre-sampling score | Zero failures across 28,748 responses; Q4_K_M raw task scores 73%/49%/57% versus 72%/48%/60% | Admit as supplemental mixed robustness evidence; keep the original admission contract |
| Fail-closed cache certificate | All-uncached 165-request temporal trace | Certify 44 exact prompt fingerprints, deny four, and route unknowns uncached | Byte-exact outputs; 1.84765x throughput; 0.90716x p95; six safe unknown fallbacks differed from the frozen count | Reject E13a on the unchanged decision-count gate; retain the otherwise passing evidence |
| Calibration-known cache certificate | All-uncached reversed 165-request trace | Restrict transitions to fingerprints derived before E13b and fail closed otherwise | Byte-exact outputs; **1.85158x** throughput; 0.94427x p95; exact 146/19/0 decisions twice | Admit only the retained exact-fingerprint boundary; do not generalize semantically |
| Selective weight repack | Full-repack and no-repack memory/throughput endpoints | Leave two predeclared tensor families in mapped storage | Valid four-point frontier; selective points retain 78.06%/62.56% throughput and save 22.14%/46.11% of extra RSS | Retain E14a as invalid and E14b as a valid no-promotion result; keep full repack |
| Persistent packed-weight prerequisite | Runtime-only Arm-repacked Q4_K_M arena | Serialize all 183 packed tensors at arena-relative offsets with model/source/CPU binding | Two fresh processes produce the same 2,139,013,120-byte SHA-256 and preserve 23/30 | Admit only the representation feasibility; measure a fail-closed loader separately |
| Asymmetric prefill/decode scheduling | Exact E9a 4/4 pools inside strict two-CPU affinity | Reduce only decode threads to two across six reverse-balanced pairs | 1.00427x throughput, 0.99897x p95, but exactly 1.00000x CPU/request | Reject: no CPU-efficiency gain; keep 4/4 |
| Shared Arm-prepacked arena | Two simultaneous workers with private runtime repacks | Map one verified 183-tensor sidecar read-only into both workers | **2,091,714 KiB less summed PSS (30.69%)** at 1.00044x throughput and exact quality | Admit the exact two-worker physical-sharing tier; make no per-process RSS claim |

Rejected variants remain visible: two server slots, cached two-slot serving,
q4_0 KV, batch 32, Flash Attention, lower thread counts, and LTO all missed at
least one predeclared gate.
The evidence links below retain those negative results alongside the wins.

```bash
python3 -m pareto64 plan \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json \
  --output results/plans/e3f-cloud-quality.json
```

The selected model now has a second, measured decision stage. A throughput
policy selects the Arm-repacked service, while an at-most-3-GiB policy selects
the exact no-repack tier and emits its bounded launcher argument:

```bash
python3 -m pareto64 service-plan \
  --manifest results/manifests/e5h-30672633366.json \
  --constraints configs/service-memory.json
```

The retained result is `repack_off` with `--no-weight-repack`. Replace the
policy with [`configs/service-throughput.json`](configs/service-throughput.json)
to select `repack_on`; a policy no measured tier can satisfy returns
`no_feasible_profile` instead of guessing.

The verified launcher accepts the same evidence/policy pair through
`--service-manifest` and `--service-constraints`. It binds both hashes into the
launch recipe and applies the selected repack mode automatically. A manual
repack flag that conflicts with the plan is refused.

## Native evidence so far

| Gate | Outcome |
| --- | --- |
| [E0](results/reports/e0-native-arm.md) | Native four-core Neoverse N2 runner and repeatability characterized |
| [E1](results/reports/e1-llm-runner-smoke.md) | Pinned LLM-Runner built and executed end to end on Arm |
| [E2](results/reports/e2-kleidiai-ablation.md) | Primary KleidiAI threshold missed; smaller decode/latency benefits retained |
| [E3](results/reports/e3-qwen-frontier.md) | Three Qwen packages measured; frozen quality gate rejected all three |
| [E3b](results/reports/e3b-quality-anchor.md) | 7B improved to a stable 73.33% but missed the unchanged quality floor by one task |
| [E3c](results/reports/e3c-quality-per-byte.md) | Q4_K_M led a stable 4B quantization sweep at 66.67%; the unchanged quality gate rejected all variants |
| [E3d](results/reports/e3d-current-runtime.md) | Current Qwen3.5 Q4_0/Q8_0 both reached a stable 66.67%; Q8_0 was faster but exceeded load and RSS ceilings |
| [E3e](results/reports/e3e-bounded-reasoning.md) | Invalid mechanism run exposed a reproducible zero-budget forced-token state bug; no frontier was created |
| [E3f](results/reports/e3f-ministral-frontier.md) | Q4_K_M reached a stable 76.67% and passed every frozen quality, latency, load, RSS, and package gate |
| [E4a](results/reports/e4a-backlog-tuner.md) | Native bounded tuner selected backlog 64 with zero failures or tail breaches |
| [E5a](results/reports/e5a-planner-api.md) | Native fail-closed API passed load SLOs; one-second tail retained for tuning |
| [E5b](results/reports/e5b-selected-inference.md) | Exact selected-model serving reproduced 23/30 with zero drift; two slots missed the 1.10x throughput gate |
| [E5c](results/reports/e5c-prompt-cache.md) | Quality-gated shared-prefix caching preserved all 120 answers and raised throughput 1.672x while cutting median HTTP latency 41.3% |
| [E5d](results/reports/e5d-cached-concurrency.md) | Cached two-slot serving preserved all answers but reached only 1.0619x throughput while nearly doubling median latency; one slot remains the default |
| [E5e](results/reports/e5e-kv-context-profile.md) | A 256-token f16 context preserved all answers and saved 183.36 MiB maximum RSS; q4_0 drifted and was rejected |
| [E5f](results/reports/e5f-prompt-batch-profile.md) | A 64/64 prompt batch preserved all answers, cut the compute buffer 75%, and saved 14.48 MiB maximum RSS |
| [E5g](results/reports/e5g-prompt-batch-floor.md) | A staged 32/32 boundary preserved quality and speed but added 660 KiB maximum RSS; 64/64 remains the default |
| [E5h](results/reports/e5h-weight-repack-boundary.md) | No-repack preserved every answer and saved 2,072,268 KiB RSS; it is a slower explicit memory tier while repack stays default |
| [E5i](results/reports/e5i-flash-attention-ablation.md) | Resolved Flash Attention preserved quality but gained only 1.0322x throughput and worsened p95 6.03%; no material win is claimed |
| [E5j](results/reports/e5j-thread-efficiency-profile.md) | Three/two threads preserved quality but saved only 0.11%/1.36% CPU time per request while losing 24.48%/48.82% throughput; four stays default |
| [E6a](results/reports/e6a-native-feature-fix.md) | Reproduced and fixed invalid native KleidiAI SVE source selection |
| [E6b](results/reports/e6b-q8-vector-store.md) | NEON vector narrowing doubled isolated Q8_0 quantizer throughput with neutral real-model inference |
| [E6c](results/reports/e6c-reasoning-budget-fix.md) | Source fix passed 13 upstream tests and removed all reasoning output; the frozen final-answer gate still rejected the real-model run |
| [E6d](results/reports/e6d-current-upstream-patches.md) | All three Arm patches revalidated on llama.cpp b10216; targeted tests passed and direct Q8 throughput improved about 95% |
| [E6e](results/reports/e6e-upstream-arm-cpu-lane.md) | Complete upstream-equivalent native Arm CPU build passed, followed by 47/47 clean CTest executions |
| [E6f](results/reports/e6f-current-runtime-service.md) | Patched b10216 reproduced every selected answer and cleared all exact-service upgrade gates with 1.0028x throughput and +100 KiB maximum RSS |
| [E6g](results/reports/e6g-current-runtime-launch.md) | The fail-closed adapter launched that exact patched service on Arm and reproduced 23/30 with zero drift, failures, or missing prefix reuse |
| [E6h](results/reports/e6h-current-runtime-memory-service.md) | Patched b10216 cleared every no-repack upgrade gate with 1.0024x throughput, +180 KiB RSS, and every cell below 3 GiB |
| [E6i](results/reports/e6i-current-runtime-memory-launch.md) | The E6h-bound adapter launched that exact no-repack service on Arm: 23/30, zero drift/failures, prefix reuse throughout, and 2,381,040 KiB RSS |
| [E7a](results/reports/e7a-lto-service.md) | Whole-program LTO preserved exact quality but gained only 0.137% throughput and reduced the local runtime closure only 0.775%; LTO-off remains selected |
| [E7b](results/reports/e7b-openssl-service.md) | OpenSSL-off removed exactly two unused HTTPS dependency edges, added none, retained 99.981% throughput, and preserved exact quality and every guardrail |
| [E7c](results/reports/e7c-http-runtime-launch.md) | The E7b-bound adapter launched the exact OpenSSL-off HTTP service on Arm: 23/30, zero drift/failures, prefix reuse throughout, and both forbidden libraries absent |
| [E9a](results/reports/e9a-final-service-comparison.md) | Same-job final comparison preserved all 240 answers and reached 1.7168x throughput, 0.5846x median latency, and 0.5806x CPU seconds/request |
| [E9b preflight](results/reports/e9b-holdout-preflight-blocker.md) | Exact E7c built and tokenizer parity passed, but b10216 cannot return the echoed prompt logprobs required by lm-eval; no external task result was observed |
| [E9c](results/reports/e9c-prompt-cache-generalization.md) | All cache/performance gates passed across the bounded alternating-prefix matrix, but output regression disabled every generalized cache policy |
| [E9d](results/reports/e9d-pr-ready-patch-series.md) | Exact unpublished mail series passed GCC/Clang and feature lanes; strict UBSan failure reproduced on pristine b10216, so sanitizer-clean readiness remains rejected |
| [E9e](results/reports/e9e-speculative-cross-runtime-feasibility.md) | Bounded source/model/workload review failed three premeasurement gates; no speculative or cross-runtime benchmark was launched |
| [E10a](results/reports/e10a-cache-divergence.md) | Native calibration reproduced cache drift, but top-1 margins overlapped stable requests; no guard threshold or holdout was selected |
| [E10b preflight](results/reports/e10b-preflight-failure.md) | Native source/build/readiness passed before a retained path-type harness failure prevented all measurements |
| [E10b](results/reports/e10b-exact-token-probabilities.md) | Exact A/B/C/D log probabilities matched within 3.58e-7 with identical sampled output; median payload fell 99.9779% and HTTP latency fell 18.6% |
| [E10c](results/reports/e10c-candidate-scorer-negative.md) | One-request candidate scoring matched predictions but failed every frozen numerical log-probability parity gate |
| [E10d](results/reports/e10d-external-holdout-failure.md) | Both 300-sample model loops hit missing probability entries; the pair and all partial task metrics remain invalid |
| [E10e](results/reports/e10e-probability-compatibility.md) | A safe sampled-token path completed both retained compatibility failures twice with zero requested-score delta |
| [E10f](results/reports/e10f-safe-sampled-external-holdout.md) | Both exact quantizations complete the pinned 300-sample native holdout with zero failures; the mixed per-task result is supplemental and non-cherry-picked |
| [E11a successor first run](results/reports/e11a-successor-provenance-failure.md) | All eight stock cells stopped before model download because a historical E10f test hash was incorrectly compared with a legitimate later test addition; no model outcome or frontier claim exists |
| [E12a](results/reports/e12a-application-imatrix-timeout.md) | The exact native 32-chunk application-imatrix run reached its five-hour job ceiling; a valid 24-chunk checkpoint is retained, but the matrix is incomplete and no generated-quant dispatch is permitted |
| [E12a resume first run](results/reports/e12a-resume-python-environment-failure.md) | Checkpoint, corpus, native build, and BF16 identity passed, but the GGUF dumper used a Python environment without NumPy; matrix compute never started and no completed result exists |
| [E12a resume second run](results/reports/e12a-resume-statistics-invocation-failure.md) | All remaining chunks completed and wrote hash-bound bytes, but the following statistics command omitted required `--model`; the run remains invalid and a frozen inspection-only, no-recompute recovery is required |
| [E12a inspection recovery](results/reports/e12a-inspection-metadata-dependency-failure.md) | Corrected statistics passed for all 182 tensors with unchanged matrix bytes, but the metadata dumper lacked PyYAML; a frozen metadata-only recovery may add that dependency without repeating compute, statistics, build, or model download |
| [E12a complete matrix](results/reports/e12a-application-imatrix-complete.md) | The metadata-only successor accepts the exact 32-chunk, 182-entry matrix with byte-identical independent replay; computation and statistics were not repeated, and generated quantization is now authorized once E11a also passes |
| [E17a first preflight](results/reports/e17a-preflight-permission-failure.md) | Exact runtime and model checks passed, but the cell runner lacked executable permission; zero cache configurations or requests started, and a frozen shell-invocation-only successor retains every scientific control |
| [E17a second preflight](results/reports/e17a-subset-reference-probe-failure.md) | All three native servers reached readiness and exposed smaller quantized-cache allocations, but a full-map/subset reference mismatch stopped every cell before its first measured request; the run remains invalid and a hash-bound subset adapter changes no scientific control |
| [E17a](results/reports/e17a-quantized-v-compatibility.md) | The unchanged native preflight passes: q8/q8 and q4/q4 retain all nine diagnostic answers while reducing the 1K one-slot KV allocation 46.88% and 71.88%; both advance to long-context testing, with no performance or service promotion from the three-request diagnostic |
| [E13a](results/reports/e13a-cache-certificate.md) | Byte-exact fail-closed routing reached 1.84765x throughput, but six safe unknown warmup fallbacks violated the frozen decision-count expectation; the policy remains rejected |
| [E14a](results/reports/e14a-selective-repack-instrumentation-failure.md) | All eight native cells completed with exact quality, but missing verbosity-4 mechanism logs invalidate the frontier and forbid promotion |
| [E13b](results/reports/e13b-cache-certificate-successor.md) | A separately frozen calibration-known trace passes every gate at 1.85158x throughput with byte-exact output and exact decision counts; admission remains fingerprint-bounded |
| [E14b](results/reports/e14b-selective-repack-frontier.md) | The corrected four-point frontier is valid, but neither selective tier clears the unchanged joint target; full repack remains selected |
| [E16a](results/reports/e16a-repack-sidecar-feasibility.md) | Two fresh native processes produce a byte-identical complete repack sidecar with exact quality; only the separately frozen loader successor is authorized |
| [E16b first run](results/reports/e16b-repack-sidecar-loader-ingestion-failure.md) | All eight native loader cells complete with descriptive passing values, but a frozen post-measurement ingester error invalidates the run and forbids promotion |
| [E16b](results/reports/e16b-repack-sidecar-loader.md) | The repaired successor passes every frozen gate: exact quality and steady-state performance are retained while same-job median readiness falls 62.03%; RSS/PSS does not materially change |
| [E15b](results/reports/e15b-affinity-split-scheduler.md) | Strict two-CPU confirmation preserves exact quality but rejects split 2/4 scheduling: 0.43% throughput gain with no CPU/request reduction misses the unchanged efficiency gate |
| [E16c](results/reports/e16c-shared-repack-arena.md) | Two simultaneous workers share one verified read-only packed arena, saving 1.995 GiB summed PSS at 1.00044x throughput with all answers unchanged |

Negative results remain first-class evidence. No runtime is promoted into the
planner until it passes a predeclared quality/SLO contract.
The E5f through E5j, E6d through E6i, E7a through E7c, E9a/E9c, E10a through
E10f, E12a, E13a/E13b, E14a/E14b, E15a/E15b, E16a/E16b/E16c, and E17a results are retained under their exact frozen
contracts and independently re-ingested byte for byte. E9e separately retains its reproducible
premeasurement stop record.

## Repository map

- [`docs/hackathon-requirements.md`](docs/hackathon-requirements.md): rules,
  deliverables, judging, dates, and compliance checklist.
- [`docs/track-analysis.md`](docs/track-analysis.md): published track boundaries
  and cross-front optimization opportunities.
- [`docs/strategy.md`](docs/strategy.md): concept comparison and the leading
  single-project hypothesis.
- [`docs/product.md`](docs/product.md): executable planner behavior, policy
  contract, and current E2E boundary.
- [`docs/final-device-evidence.md`](docs/final-device-evidence.md): the bounded
  local Arm power, governor, thermal, and tariff-derived cost protocol.
- [`results/reports/service-tier-planner.md`](results/reports/service-tier-planner.md):
  measured E5h service-envelope decisions and refusal boundary.
- [`docs/experiment-plan.md`](docs/experiment-plan.md): ordered, gated benchmark
  program.
- [`docs/environment.md`](docs/environment.md): current host, native Arm routes,
  and measurement constraints.
- [`docs/relevant-resources.md`](docs/relevant-resources.md): vetted frameworks,
  profiling tools, starters, environments, and license traps.
- [`docs/competitive-landscape.md`](docs/competitive-landscape.md): prior winning
  patterns and current public competitor intelligence.
- [`docs/open-questions.md`](docs/open-questions.md): contradictions that require
  organizer clarification or a conservative working assumption.
- [`docs/source-registry.md`](docs/source-registry.md): URLs and source authority.
- [`experiments/README.md`](experiments/README.md): evidence contract for every
  benchmark.
- [`configs/cloud-balanced.json`](configs/cloud-balanced.json): explicit example
  quality/SLO and selection policy.
- [`configs/cloud-quality.json`](configs/cloud-quality.json): predeclared
  quality-first policy that independently rejected the E3b near-miss.
- [`configs/service-throughput.json`](configs/service-throughput.json) and
  [`configs/service-memory.json`](configs/service-memory.json): measured E5h
  service-envelope policies for the fast and at-most-3-GiB deployments.
- [`patches/README.md`](patches/README.md): reviewable source-patch inputs and
  validation status.
- [`logs/progress.md`](logs/progress.md): chronological project journal.
- [`ops/telegram.md`](ops/telegram.md): phone notification and decision workflow.
- [`ops/telegram_decisions.py`](ops/telegram_decisions.py): authenticated,
  bounded Telegram-to-Codex decision bridge.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
