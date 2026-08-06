# Pareto64

**Tagline:** Proof-carrying Arm64 inference: eight exact shared workers where
the private representation could sustain six.

**Track:** Cloud AI

**Source:** <https://github.com/Arshgill01/Arm>

**Public evidence report:** <https://pareto64-arm-evidence.arshgill01.chatgpt.site>

**Interactive demo:** <https://pareto64-arm-evidence.arshgill01.chatgpt.site/demo/index.html>

**Raw Axion evidence:** <https://github.com/Arshgill01/Arm/releases/tag/e22-axion-evidence-20260806>

**Supplemental 76-second walkthrough (direct MP4):** <https://github.com/Arshgill01/Arm/releases/download/e22-axion-evidence-20260806/pareto64-demo.mp4>

## Project overview

The fastest AI configuration is often the wrong one. Quantization, backend
selection, batching, and low-level kernels can all improve a benchmark while
quietly reducing answer quality, breaking a target architecture, or shifting
cost into memory and tail latency.

Pareto64 is an evidence-first deployment planner for CPU inference on Arm64. It
takes native experiment evidence plus an explicit quality/SLO policy, rejects
invalid or quality-ineligible candidates, computes the non-dominated frontier,
and emits a reproducible deployment plan. Once a candidate passes, a fail-closed
launch adapter verifies its exact model hash, source revisions, policy, runtime
contract, and llama.cpp commit before starting the OpenAI-compatible server.

The final result is an independently replicated fixed-memory systems result.
On two fresh 16.72 GB Google Axion c4a-highcpu-8 instances, the normal
Arm-packed representation sustained six workers; normal-8 reached an OOM
boundary before admission. Pareto64 mapped one verified read-only Arm-packed
sidecar into eight workers. Across eight balanced pairs, shared-8 delivered a
median 1.3568x the aggregate throughput of normal-6 with 59.32% lower summed
PSS and zero response drift across 3,360 measured requests.

The claim deliberately stops at same-provider, same-machine-class steady-state
density. Combined median shared readiness was 2.2138x normal and remained
unfavorable, so Pareto64 does not claim a full lifecycle or fleet improvement.
The original selection story remains
equally important: our faster 2.05 GB KleidiAI model lost because it scored 70%.
The 2.15 GB Q4_K_M package scored 76.67% and became the only admitted model.

## Optimization at a glance

Each row is a separately frozen native Arm experiment; the effects are not
summed. Every promoted service change preserved the selected task predictions.

| Front | Baseline → change | Measured result | Decision |
| --- | --- | --- | --- |
| Fixed-memory worker density | Normal-6 → shared-8 on two independent 16.72 GB Axion instances | 1.3568x median aggregate throughput; 59.32% lower summed PSS; 3,360 exact requests | Promote independently replicated steady-state density only |
| Lifecycle boundary | Normal-6 → shared-8 readiness | 2.2138x combined median; still unfavorable | Do not promote full lifecycle claim |
| Product deployment | Separate planner/sidecar/controller → one deploy command | Six product cells; 420/420 exact requests; shared-inode proof and receipt | Integrate gateway + workers + registry |
| Model/quality | Faster Q4_0 → gated package search | 70% → 76.67%; selected model is slightly larger | Reject speed without quality |
| Prompt work | Cache off → shared-prefix reuse | 1.672x throughput; median latency 1,807 → 1,062 ms | Promote cache |
| KV memory | 2,048/f16 → 256/f16 context | 183.36 MiB RSS saved at 99.62% throughput | Promote; reject q4_0 drift |
| Prompt graph | 256/256 → 64/64 batch | 75% smaller compute buffer; 14.48 MiB RSS saved | Promote 64/64 |
| Arm layout | Repack on → measured no-repack tier | 1.98 GiB RSS saved at 48.47% throughput | Route fast and ≤3-GiB envelopes separately |
| Thread efficiency | 4 threads → measured 3/2-thread profiles | Only 0.11%/1.36% CPU-time savings while throughput falls 24.48%/48.82% | Keep four threads; CPU time is not energy |
| Arm kernel | 32 scalar stores → NEON narrows/vector stores | 5.09 → 10.33 GB/s, 2.029x, bit-identical | Accept hot-path win only |
| Source robustness | Historical pins → llama.cpp b10216 | Complete native build and 47/47 tests passed | Validate one upstream-equivalent Arm CPU lane |
| Application runtime | Clean b10208 → patched b10216 | Exact 23/30 twice; 1.0028x throughput; +100 KiB RSS | Accept an exact-service upgrade candidate |
| Product integration | Manual command risk → evidence-bound adapter | Native adapter launch reproduced 23/30 with zero drift or failures | Admit only the exact measured service |
| Final compounded service | Earliest admitted E5b → exact E7c | 1.7168x throughput; 41.5% lower median latency; all 240 answers exact | Accept the end-product delta; attribute through isolated lanes |
| Online cache safety | Empty registry → exact-response transition certificate | 1.72776x lifecycle throughput; cycle-two break-even; first-use p95 1.66468x | Promote only for the exact identity/workload |
| Persistent Arm weights | Private per-process repacks → one verified read-only sidecar | 62.03% lower warm readiness; 1.995 GiB less two-worker summed PSS | Keep warm/PSS claims separate from cold/RSS |
| Product lifecycle | Manual sidecar handling → prepack/verify/launch/cleanup CLI | 14/14 unchanged gates; 23/30 on both workers | Promote through E16e; retain E16d reader failure |

## What it does

- runs checksum-pinned AI experiments on native Neoverse N2 hosts and records
  the exact CPU topology for every claim;
- preserves raw per-request/per-round data and independently re-ingests it;
- enforces stable quality before comparing latency, RSS, load time, or size;
- builds a Pareto frontier without a hidden weighted score;
- serves the decision through a bounded standard-library HTTP API;
- verifies and launches the exact selected GGUF with pinned llama.cpp settings;
- launches normal or shared workers plus an OpenAI-compatible exact-transition
  gateway from one receipt-producing command;
- verifies one read-only Arm-packed inode across workers and bounds registry
  revalidation/revocation;
- retains negative results and near-misses instead of rewriting thresholds; and
- packages reports, manifests, source patches, CI workflows, and an interactive
  judge demo in one Apache-2.0 repository.

## Run and validate on Arm64

The compact judge package uses only Python's standard library and needs no model
download:

```bash
git clone https://github.com/Arshgill01/Arm.git
cd Arm
python3 scripts/verify_submission.py
python3 -m unittest discover -s tests -v
python3 -m pareto64 plan \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json
```

To exercise the browser demo locally, run
`python3 -m http.server 4174 --directory demo` and open
`http://127.0.0.1:4174`. The public copy is linked above.

Live inference requires Linux Arm64, the exact hash-pinned Ministral GGUF and
the measured llama.cpp build. The public
[`docs/product.md`](https://github.com/Arshgill01/Arm/blob/main/docs/product.md)
gives the complete `pareto64 deploy` command for normal or shared workers,
sidecar paths, certificate registry, gateway and receipt. Every mismatch in
model, runtime, source, policy, CPU identity, sidecar or mapping fails before
admission.

## Native Arm results

### Repeated fixed-memory density on Google Axion

E22b froze the physical `/proc/meminfo` total of 16,723,460,096 bytes as the
cap on one standard eight-core Neoverse V2 Axion host with no SMT and no swap.
It measured the complete 1/2/4/5/6/8-worker curve with exact requests, mapping
identity, PSS, MemAvailable and standard Arm PMU counters. Shared-8 completed at
2.6760 requests/s. Normal-8 failed before readiness with one OOM kill; normal-6
was the largest admitted private configuration.

E22c then froze normal-6 versus shared-8 before running four repetitions of each
in reverse-balanced order. Median aggregate throughput was 1.9897 versus 2.6862
requests/s, a 1.3525x ratio; every paired ratio exceeded 1.20 and coefficient of
variation was 0.00363. Median p95 latency improved slightly to 0.9780x. Median
summed PSS fell from 15,727,791 to 6,380,921.5 KiB, while per-worker throughput
remained 1.0144x. All 1,680 requests completed without failures or output drift.

The median all-worker readiness ratio was 2.0817x and failed the frozen <=2.0
gate. Pareto64 therefore retains a repeated steady-state fixed-memory density
claim, not a full lifecycle promotion. It makes no cold-cache, energy, billing,
kernel-causality or fleet claim from this campaign.

E22d froze the same comparison on one fresh instance with a different provider
ID and no permission to reroll readiness. All four second-host pairs passed;
their median throughput ratio was 1.3613x and median PSS saving was 58.96%.
Combined across both instances, eight balanced pairs and 3,360 exact requests
retain a 1.3568x median throughput ratio, a 1.3457x minimum pair, 59.32% median
PSS saving and 0.6449% ratio CV. Combined median readiness is 2.2138x and stays
outside the promoted claim. Both setup stops, the successful 606-file evidence
set, and VM cleanup are public in the raw-evidence release.

### Quality-per-byte selection

Ministral 3 3B Instruct Q4_K_M scored 23/30 (76.67%) in both quality
repetitions. Its 2,146,497,824-byte package loaded in 2.73 seconds, used
4,696,108 KiB peak RSS, and completed the same-text workload in a 1.80-second
median. It was the only candidate to clear the unchanged 75% quality floor and
all Cloud AI SLOs.

The Q4_0/KleidiAI alternative was smaller (2.05 GB) and faster (1.28-second
median), but stable at 70%. Pareto64 rejected it before resource ranking.

### Exact inference serving

The product launch path served 120 measured OpenAI-compatible requests across
four fresh-server cells. Every response was HTTP 200, an exact standalone answer
letter, normally terminated, and identical to the selected experiment. Every
cell reproduced 23/30 with zero failures or drift. Readiness stayed below 4.1
seconds and maximum RSS below 4.91 million KiB.

A two-slot tuning candidate improved repeated median throughput only 1.019x,
below its predeclared 1.10x gate, and nearly doubled median request latency.
Pareto64 retained one slot rather than marketing a marginal concurrency win.

We then tested shared-prefix prompt caching in a separate frozen A–B–B–A
experiment. Upstream warns that cache-dependent prompt batch sizes can alter
logits, so all 120 responses had to match before speed counted. They did.
Caching reused at least 25 tokens per request, raised repeated median throughput
from 0.538 to 0.899 requests/s (1.672x), and cut pooled median HTTP latency from
1.807 to 1.062 seconds with only about 6.2 MiB additional maximum RSS.

Finally, we retested concurrency after enabling the cache rather than assuming
the two optimizations would compose. Cached two-slot serving preserved all 120
answers and prefix reuse, but improved throughput only 1.0619x while raising
median latency 93.3% and maximum RSS by about 239 MiB. It missed the frozen
1.10x promotion gate, so the product still defaults to one slot.

We then profiled the service's KV memory against the real application envelope.
The workload needed at most 127 prompt tokens plus an eight-token output cap,
yet the server reserved 2,048 tokens. A frozen 2×3 context/K-precision
factorial showed that a 256-token f16 profile reduced the runtime KV allocation
from 208 to 26 MiB and maximum process RSS by 183.36 MiB while preserving every
answer, 99.62% of throughput, and essentially identical latency. q8_0 also
qualified, but the precision-first selector kept f16. q4_0 reproducibly changed
one correct answer in all four cells, so its larger memory and speed gains were
rejected. A clean promoted-default run then repeated the full matrix with the
selected cells using no context/KV overrides; 23/30, throughput retention, and
the memory win all reproduced.

With the context fixed, we profiled the remaining prompt compute-graph
reservation. The effective 256/256 logical/physical batch allocated a 40.13
MiB CPU compute buffer. A frozen forward/reverse 256/128/64 study promoted
64/64 as the launcher default: all 60 measured answers remained exact, the
compute buffer fell to 10.03 MiB, maximum RSS fell 14.48 MiB, and throughput
rose 2.26%. The 128/128
profile was not promoted because its maximum-RSS reduction missed the frozen 8
MiB process gate despite a smaller reported buffer. A clean promoted-default
run repeated all six cells with no Pareto64 batch flags on the 64/64 cells: all
180 answers matched again, throughput retention was 1.0240x, and maximum RSS
fell 17,264 KiB.

We then tested the next boundary without opening an arbitrary sweep. Batch 32
halved the remaining compute buffer to 5.02 MiB, preserved every answer, and
retained 1.0116x throughput, but maximum RSS increased by 660 KiB. It failed
the frozen process-memory gate, so 64/64 remains the default. The staged
contract allowed testing batch 16 only if 32 passed; we stopped instead of
searching past a negative result.

The remaining large allocation was Arm-specific weight repacking. In a frozen
A–B–B–A test, the default exposed a 2,038.92 MiB `CPU_REPACK` buffer and
reached 0.9295 requests/s at 4,453,532 KiB maximum RSS. Disabling repack
preserved all 120 answers and cached-prefix reuse while lowering maximum RSS by
2,072,268 KiB to 2,381,264 KiB. The cost was explicit: throughput fell to
0.4505 requests/s, or 48.47% retention. Pareto64 keeps repack as the fast
default and exposes the qualified no-repack path only as an opt-in memory tier.

We then removed the remaining manual choice. A second fail-closed planner reads
that same native manifest and a deployment envelope. The throughput policy
selects `repack_on`; an at-most-3-GiB policy selects `repack_off` and emits
`--no-weight-repack`; an impossible at-most-2-GiB policy refuses deployment.
As with model selection, every metric, rejection, input hash, Pareto member, and
runtime argument is recorded without a weighted score. The verified launcher
consumes that exact evidence/policy pair, binds both hashes into its recipe, and
applies the selected repack mode; contradictory manual flags fail closed.

We also ablated the runtime's resolved Flash Attention auto graph rather than
crediting the default without evidence. All 120 answers remained exact. Auto
improved throughput only 1.0322x—below the frozen 1.05x gate—and worsened p95
latency 6.03%, despite better median latency and RSS. We retain the measurement
and bounded mode control, but make no material Flash Attention speed claim.

We then challenged the assumed four-thread serving default using the live
`llama-server` process counters sampled after warmups and around only the 30
measured requests. All profiles preserved every selected answer and cached
prefix. Three threads reduced CPU seconds per request only 0.11% while losing
24.48% throughput; two threads reduced CPU time 1.36% while losing 48.82%.
Both also missed the frozen latency gates, so four threads remains the default.
We explicitly do not translate CPU time into an energy or power claim.

### Arm-specific source work

We fixed a llama.cpp/KleidiAI feature-selection defect where a substring search
could compile SVE assembly even after the final compiler flags disabled SVE.
The source now uses the build's validated feature probes. A native clean build,
functional model test, runtime-buffer proof, and real inference all passed.

We then optimized the Arm `quantize_row_q8_0` hot path. The baseline extracted
and stored 32 individual byte lanes. The patch narrows values in NEON registers
and emits two 128-bit stores:

- 155 → 98 static instructions;
- 32 → 0 scalar byte stores;
- 0 → 6 vector narrowing instructions;
- 0 → 2 vector stores; and
- 5.09 → 10.33 GB/s, a 2.029x repeated median direct speedup.

The standalone output was bit-identical, upstream quantization tests passed,
and every real-model response remained unchanged. Whole-model inference was
neutral, so we claim the measured quantizer win—not a model-wide speedup.

We then rebased all three Arm source contributions onto llama.cpp `b10216`.
The Q8 and reasoning patches applied byte for byte; the feature fix needed only
surrounding SME-list context refreshed. A fresh native run reproduced both
source failures, passed all targeted tests after the complete series, and
measured 1.950–1.958x direct Q8 throughput across all three sizes. This is a
frozen current-revision result, not a claim that the full upstream CI matrix or
whole-model inference improved.

Finally, we ran the complete series through an upstream-equivalent native Arm
CPU lane. The full fatal-warnings default target built with KleidiAI and RPC,
then all 46 upstream `main` tests plus the required fixture passed—47/47 total,
with no failures, errors, or skips. This validates one Arm CPU lane, not the
full cross-platform and accelerator matrix.

We then challenged the historical application pin directly. In one matched
native job, four fresh clean-`b10208` and patched-`b10216` servers ran the exact
selected Ministral service in reverse-balanced order. Current source reproduced
23/30 twice, retained 100.28% throughput, slightly improved median/p95 latency,
used 99.93% of baseline CPU seconds/request, and added 100 KiB maximum RSS.
Every frozen gate passed. This is an upgrade candidate for one exact service,
not an energy, model-wide, full-matrix, or automatic-promotion claim.

We then exercised the product boundary itself. E6g rebuilt the exact patched
source, verified the E6f decision, full-index diff, CMake build, server binary,
model, and arguments, and launched through `python -m pareto64 launch` on native
Arm. All 30 requests succeeded, reproduced 23/30 without drift, and observed
cached-prefix reuse. This validates the one exact explicit integration—not other
models, no-repack, lower threads, more slots, alternate graphs, energy, or the
full upstream matrix.

We then evaluated the separately measured no-repack memory tier across the same
runtime boundary. Four fresh historical/current servers reproduced 23/30 twice
with zero drift or failures. Patched b10216 retained 100.24% throughput, used
99.85% of baseline CPU seconds/request, added 180 KiB RSS, and stayed below
3 GiB in every cell. E6h therefore qualifies an exact memory-tier upgrade
candidate, while leaving product launch disabled until a separate adapter
integration is executed.

E6i executes that integration. The adapter binds the E6h result, dedicated
memory runtime contract, full-index patched source diff, CMake build, binary,
model, and explicit no-repack recipe before launch. On native Arm it reproduced
23/30 with zero drift or failures, reused the cached prefix on every request,
and used 2,381,040 KiB maximum RSS. The fast and memory services now have
separate current-runtime launch evidence instead of inheriting one another's
claims.

We also challenged the untouched compiler/build front. E7a built the exact
selected fast service twice with `GGML_LTO=OFF` and `ON`, proved the mechanism
from full Ninja commands, and retained hashed copies of both transitive local
runtime closures. LTO preserved 23/30 twice and every common guardrail, but
gained only 0.137% throughput and reduced the closure only 0.775%. It missed
both frozen benefit branches, so the default remains off.

E7b used that runtime inventory to challenge a different deployment default.
The selected service is plain loopback HTTP, but upstream HTTPS support linked
OpenSSL. A matched native Arm build removed exactly `libssl.so.3` and
`libcrypto.so.3`, added no dependency, preserved 23/30 twice and every
guardrail, retained 99.981% throughput, and reduced the hashed local closure
1.003%. It qualifies only an HTTP-only dependency-pruned launch candidate;
HTTPS and security claims are explicitly out of scope.

E7c then executes the separate product proof. The adapter binds the E7b result,
OpenSSL-off CMake cache, full-index patched source diff, binary, model, exact
repacked HTTP recipe, and a fresh dependency inventory before launch. On native
Arm all 30 requests reproduced 23/30 with zero drift or failures and prefix
reuse throughout. A second raw `ldd` capture matched all 13 dependency names;
neither OpenSSL library was present. HTTPS remains outside this contract.

E9a closes with the deliberately compounded end-product comparison judges can
read directly. One native two-logical-CPU Arm job ran the exact earliest E5b
service and exact final E7c service four times each in reverse-balanced order.
All 240 measured answers matched with zero failures or drift. The final service
reached 1.7168x throughput, 0.5846x median latency, 0.7056x p95 latency, and
0.5806x CPU seconds/request, while maximum RSS fell to 0.9575x. One baseline
readiness outlier reached 10.13 seconds and remains included. We do not assign
the compounded delta to one mechanism; the isolated E5c/E5e/E5f/E6f/E7b
experiments remain the causal evidence.

E9c then tests the cache claim outside its original repeated-prefix workload,
without changing the final service. A predeclared one/two/four-prefix by
16/32/64-token matrix completed 576 requests with zero HTTP failures. Cache
reuse and every performance gate passed, including 1.9406x–2.4007x throughput
ratios, but the extended prompts produced 252 reference mismatches, 204
non-standalone answers, and 12 cache-state output mismatches. Pareto64 therefore
disables all three generalized policies. The result does not rewrite E5c; it
makes E5c's exact workload boundary explicit.

The independent-holdout and final fallback lanes also stop honestly. E9b
reached tokenizer parity against exact E7c, but b10216 could not return the
echoed prompt logprobs required by the pinned lm-evaluation-harness API; no
external task result was observed. E9d's unpublished three-patch mail series
passed native GCC and Clang lanes, while strict UBSan reproduced an inherited
test-function mismatch on pristine b10216, so publication readiness remains
rejected. E9e then found no defensible speculative or cross-runtime measurement:
the exact runtime's draft loader uses the target path, all frozen completions
are only two tokens, and independent LLM-Runner backends cannot consume the
selected GGUF Q4_K_M identity. No benchmark was launched after those gates
failed.

The next campaign kept the same stop discipline. E10a calibrated cached top-1
margin as a possible guard for E9c's semantic drift. Four drifted pairs
reproduced, but their margins overlapped stable requests, so the strict
separation gate failed and no threshold or holdout was selected. E10b moved to
the narrower candidate-scoring API bottleneck. A bounded b10216 server patch
selects four caller-known token IDs from the same pre-sampling softmax instead
of serializing all 131,072 vocabulary entries. In one native four-process
reverse-balanced job, all A/B/C/D probabilities matched within 3.58e-7,
candidate ranking and sampled output were identical, median response fell from
12.57 MB to 2.78 KB, and median HTTP latency fell 18.6%. The primitive is now
eligible for a separately frozen multi-token evaluator; no external quality or
complete-scorer claim is inherited.

E10c then tests a faster one-request forked scorer and rejects it when all three
frozen numerical parity gates fail despite matching predictions. E10d returns
to the validated serial primitive for the full preselected 300-sample holdout.
Both Q4_K_M and Q4_0 cells complete their sample loops on native Arm, but one
Q4_K_M and two Q4_0 HellaSwag samples receive HTTP-200 responses without the
required one-token probability entry. The zero-failure gate rejects both cells
and skips the aggregate. All 28,490 retained raw responses and the exact
breakpoints remain published, but incomplete task metrics are not compared and
the original stock/generated frontier prerequisites remain unsatisfied.

E10e isolates that response boundary without consuming a new task result. The
two exact Q4_0 breakpoints reproduce natively; two fresh repeats then complete
all 71 target-token scores by sampling a one-byte full stop while reading each
original target's raw pre-sampling probability. Original-prefix and repeat
deltas are both exactly zero. This authorizes only a separately frozen full
successor and leaves the failed E10d comparison unchanged.

E10f applies that mechanism to the complete, unchanged 300-sample holdout for
both exact quantizations. All 28,748 token-score responses succeed and every
sample log is retained. Q4_K_M scores 73%/49%/57% raw accuracy on ARC Easy,
HellaSwag, and WinoGrande versus Q4_0's 72%/48%/60%; normalized ARC Easy and
HellaSwag are 59%/72% versus 61%/71%. This is deliberately reported as mixed
supplemental robustness evidence, not a new admission threshold or a post-hoc
task selection. E10d remains failed.

E13a returns to the cache-safety opportunity with a fail-closed exact-prompt
certificate derived from every retained E9c pair. On a fresh 660-request
temporal holdout, controller outputs match uncached bytes exactly, aggregate
throughput rises 1.84765x, p95 latency falls to 0.90716x, and CPU
seconds/request falls to 0.54068x. The result is still rejected: six transition
warmups are absent from calibration and correctly fall back as unknown, while
the frozen trace predicted zero unknown fallbacks. We preserve the count-gate
failure rather than rewriting an otherwise attractive result.

E13b is a separately frozen successor, not a repaired score. Its reversed
temporal trace uses only transition fingerprints mechanically present in the
pre-existing calibration record. Across 660 requests it matches every uncached
output byte, produces the exact frozen 146/19/0 certified, calibrated-fallback,
and unknown decisions twice, and reaches 1.85158x throughput with 0.94427x p95.
We admit only that exact certificate boundary; unseen fingerprints remain
uncached. E14b likewise changes only E14a's uniform log verbosity. The resulting
four-point selective-repack frontier is valid, but neither selective candidate
passes the predeclared combined throughput/RSS target. Full repack stays the
fast tier, and the experimental exclusion hook is not promoted.

E16a next tests whether persistent Arm-packed weights are even a sound source
mechanism. Two fresh native processes serialize all 183 repacked Q4_K_M tensors
at arena-relative offsets and produce the same complete 2,139,013,120-byte
sidecar SHA-256 despite different absolute allocations. Both preserve 23/30
with zero failures. This is a passing feasibility boundary, not a loader or
performance result; those claims require the separately frozen E16b comparison.

E16b supplies that fail-closed loader comparison. Every sidecar tensor must
match the model, source diff, CPU identity, layout, and hash before the server
can become ready. It preserves exact quality and 1.0029x throughput while
reducing same-job median warm readiness from 2,530.23 to 960.75 milliseconds,
or 62.03%. RSS and PSS remain unchanged in one process, and Linux page cache was
not flushed, so this is not a cold-start claim.

E16c measures the missing multi-process boundary. Two simultaneous workers map
one verified read-only sidecar and preserve all 480 answers. Summed PSS falls by
2,091,714 KiB, or 1.995 GiB, at 1.00044x aggregate throughput. Per-process RSS
still counts the shared pages, so we claim physical attribution through PSS—not
an RSS saving.

E16d then runs the complete product lifecycle from a clean native checkout:
prepack all 183 tensors, independently verify them, reject a corrupted index,
launch two verified workers, reproduce 23/30 on both, stop them, and clean up
only receipt-bound files. Every product step completed, but the frozen final
reader decoded raw llama.cpp tokenizer diagnostics as UTF-8 and failed before
gate evaluation. E16d remains a failed workflow. E16e changes only that reader,
replays the exact 61-file artifact twice, and passes all 14 unchanged gates
without adding a measurement. The one-time construction took 12.602 seconds;
using E16b's warm medians gives an estimated break-even after nine warm worker
starts. Cold storage, energy, money, maintenance, and fleet economics remain
outside the claim.

The final cache result follows the same pattern. E21b begins each process with
an empty registry, shadows unknown transitions, certifies only exact response
reuse, and denies the unsafe start transition. Four reverse-balanced
repetitions preserve 23/30 and every paired response, reach 1.72776x lifecycle
throughput and 0.57752x CPU per served request, and break even in cycle two.
Synchronous first-use p95 regresses to 1.66468x while certified steady-state p95
improves to 0.43302x. The promotion is therefore exact-identity/workload-bound;
it does not claim arbitrary-prompt semantics or periodic revocation.

## How we built it

Pareto64 uses standard-library Python for schemas, evidence ingestion, Pareto
selection, the decision API, and the launch adapter. Native workflows build
immutable Arm LLM-Runner or llama.cpp revisions with KleidiAI, download exact
Apache-2.0 model packages, execute balanced experiments, retain raw results, and
run a second validator that recomputes every statistic and decision.

The opt-in current-runtime adapter keeps model selection immutable while binding
E6f fast, E6h memory, and E7b HTTP evidence through separate contracts. It
checks the exact four-file patched git diff, CMake source and build cache,
executable version and binary hash, model bytes, and only the service profile
named by that evidence.
Missing provenance or a different profile aborts before launch. E6g, E6i, and
E7c verify all three measured contracts as executed product paths, not only
static schemas.

The historical selected runtime is llama.cpp `b10208` at commit
`9d9a6d29f6b981cc7f41983d26e56485c6af1811`; E6f separately accepts patched
`b10216` commit `876a4321163249c43ca4e986818fab5ab081f282` as an exact-service
upgrade candidate. Both use native Arm and KleidiAI. The selected model is
Apache-2.0 Ministral 3 3B Instruct at pinned source and GGUF revisions.

## Challenges

The hardest work was keeping evidence stronger than the story. Several
promising directions failed honestly: a 7B model missed the quality floor by one
task; Qwen quantization sweeps left empty frontiers; a documented zero-reasoning
budget exposed a real sampler state bug; its source fix passed all 13 tests but
the unchanged eight-token application contract still rejected verbose final
answers; two inference slots failed to create a meaningful throughput win; and
whole-program LTO missed both its service-speed and runtime-footprint gates.

We also found and corrected mechanical evidence assumptions—non-UTF-8 diagnostic
bytes, changing upstream commit abbreviations, and INFO-level buffer records—
without changing measured inputs or post-observation thresholds.

## Accomplishments

- first deployable quality/SLO frontier after multiple valid empty frontiers;
- exact model-to-runtime launch with cryptographic fail-closed checks, exercised
  end to end on the current patched runtime;
- stable end-to-end native Arm inference service with zero response drift;
- quality-gated prompt reuse delivering 1.672x serving throughput and 41% lower
  median HTTP latency;
- a cross-layer cache/concurrency test that rejected a marginal 1.0619x gain;
- a bounded alternating-prefix cache test that preserved its negative output
  regression and disabled every generalized policy despite faster execution;
- a cache-confidence calibration that rejected an overlapping margin guard
  before consuming a holdout;
- a native exact-token probability primitive that preserves scores and sampled
  output while cutting the four-ID response payload 99.9779%;
- a pinned native external-holdout attempt that retains both failed model cells,
  28,490 raw responses, and exact API breakpoints without presenting partial
  task metrics as a valid model comparison;
- context right-sizing that saves 183.36 MiB without KV quantization or drift;
- prompt-batch right-sizing that cuts the compute buffer 75% and saves another
  14.48 MiB maximum RSS without answer drift;
- an explicit no-repack tier that saves 2,072,268 KiB maximum RSS while the
  2.06x-faster repacked layout remains the default;
- current-source qualification of that exact memory tier at 1.0024x historical
  throughput, +180 KiB RSS, and below 3 GiB in every cell;
- a measured service-profile planner that automatically routes throughput and
  at-most-3-GiB envelopes while refusing unmeasured capacity assumptions;
- an HTTP-only build and launch integration that removes two unused OpenSSL
  runtime edges, adds none, and reproduces exact quality through the E7b-bound
  adapter;
- a final same-job comparison that retains all 240 raw request records and
  measures 1.7168x throughput with 41.5% lower median latency against the exact
  earliest admitted service;
- an adaptive fail-closed cache certificate that reaches 1.72776x lifecycle
  throughput while retaining its 1.66468x first-use p95 regression;
- a persistent Arm-packed sidecar that saves 1.995 GiB of two-worker summed PSS
  and passes a 14-gate clean-checkout product lifecycle;
- a process-bound thread-efficiency study that rejects lower thread counts
  instead of confusing fewer active cores with less total CPU work;
- three reviewable Arm source patches revalidated on current llama.cpp with
  bounded correctness evidence and a 47/47 upstream-equivalent Arm CPU lane;
- roughly 2x direct NEON quantizer throughput;
- a reusable no-weighted-score planner, HTTP API, experiment schema, reports,
  and clean-checkout validation workflow; and
- focused correctness tests plus native Arm workflows for the final evidence path.

## What we learned

Optimization is a sequence of obligations, not a leaderboard. Quantization can
save time and lose the task. A locally dramatic kernel win can be invisible at
model level. More server slots can divide fixed compute rather than increase
throughput, while removing redundant shared-prefix work can produce a large win
with almost no memory cost. Even then, caching and concurrency did not compose
enough to clear the deployment gate. Workload right-sizing can remove reserved
memory without changing precision, while KV quantization can alter a stable
answer. The reusable contribution is the machinery that makes those limits
visible before deployment.
The same discipline applied to prompt batches: a reported allocation reduction
was insufficient until process RSS, quality, throughput, and latency all
cleared their independent gates.
Weight repacking showed the complementary tradeoff: a two-gigabyte allocation
can be removed safely, but doing so gives up more than half of serving
throughput. A product should expose both qualified operating points and route
explicit deployment envelopes to them instead of pretending one profile
dominates every use case.
Persisting the packed representation changes that tradeoff again: the repack
cost can be paid once and physically shared, but only after identity binding,
full verification, corruption rejection, safe cleanup, and explicit warm-versus-
cold boundaries. Cache reuse taught the same lesson in time rather than memory:
steady-state gains do not erase first-use cost or justify semantic generalization.

## What's next

- resolve or isolate the inherited strict-UBSan test-function mismatch before
  considering the prepared three-patch series for maintainer review, then extend
  beyond the proven Arm CPU lane to sanitizer, platform, and backend jobs;
- expand the workload beyond the compact deterministic acceptance suite;
- add cost and energy evidence on a host with available counters;
- evaluate additional LLM-Runner backends only after binding an exact or
  separately quality-qualified model artifact and a genuinely independent
  runtime; and
- package more planner policies for common Graviton, Cobalt, Axion, and Ampere
  deployment envelopes.

## Significant challenge-period updates

This repository and Pareto64 implementation were created during the challenge
period. The complete commit history records the research dossier, native
baseline, every frozen contract, failed and successful runs, planner/API,
runtime launcher, Arm source patches, interactive demo, and submission package.
