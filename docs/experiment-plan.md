# Experiment program

No headline result is accepted until the experiment contract in
[`../experiments/README.md`](../experiments/README.md) is satisfied.

## Ordered gates

| ID | Question | Target | Pass condition |
| --- | --- | --- | --- |
| E0 | Can we obtain reproducible native Arm evidence in current infrastructure? | GitHub `ubuntu-24.04-arm` | Architecture/CPU/ISA captured; repeated timing noise characterized; artifacts retained |
| E1 | Does Arm LLM-Runner build and run a reference task? | Same E0 runner/job | Upstream tests pass; build metadata, dependency revisions, model hash, and backend are captured |
| E2 | Can generic/KleidiAI and at least two runtime paths be compared honestly? | LLM-Runner common API | Backend use is identified; task/input/output contract is fixed; unsupported comparisons are rejected explicitly |
| E3 | Which model/runtime/system variants lie on the quality/size/speed frontier? | Small permissively licensed model(s) | File size, RSS, prompt/decode speed, and task quality are measured under a declared equivalence policy |
| E4 | Can a bounded tuner beat defaults efficiently? | Native Arm workload | Selected configuration improves a declared objective without crossing quality/memory/SLO constraints; search overhead reported |
| E5 | Does the choice survive real E2E application or server concurrency? | HTTP service or reference voice app | TTFT/E2E latency, p50/p95, throughput, failures, and RSS are measured repeatedly |
| E6 | Can profiler/compiler evidence drive a source-level Arm improvement? | Stable hot path | Patch has tests, before/after result, assembly/profile evidence, and no quality regression |
| E7a | Can whole-program LTO improve the selected native Arm service or its shipped runtime footprint? | Exact patched `b10216` fast service | Repeated quality-gated service evidence clears a predeclared performance or footprint branch without crossing common guardrails |
| E7b | Can the loopback-only HTTP service drop unused HTTPS dependencies? | Exact patched `b10216` fast service | OpenSSL-off removes both frozen dependency edges, adds none, preserves quality, and clears every service/resource guardrail |
| E7c | Can the product launch that exact dependency-pruned service without broadening its claims? | E7b-bound Pareto64 adapter | Source/build/binary/cache/`ldd` provenance passes, then the live HTTP service reproduces quality, cache reuse, readiness, and RSS gates |
| E8a | Does shared-prefix reuse reduce real energy and tariff-derived cost on a stable local Arm device? | Exact E7c service and selected workload | Four valid cells per request policy preserve quality and environment state; cache-on reaches ≥1.10x throughput and ≤0.90x gross joules/request |
| E9a | How much better is the exact final service than the earliest admitted deployable service? | Historical E5b one-slot recipe versus exact E7c HTTP recipe | Four reverse-balanced fresh-process repetitions preserve every answer and dependency boundary; final reaches ≥1.25x throughput and ≤0.85x latency/CPU ratios |
| E9c | When does request-level prompt caching remain worthwhile as prefixes alternate? | Exact E7c one-slot service with 1, 2, or 4 prefixes sharing 16, 32, or 64 tokens | All nine predeclared points preserve exact outputs and expose scheduler noise; only points clearing every frozen throughput/encode/p95/CPU gate enter the bounded policy |
| E9d | Is the retained three-patch b10216 diff ready for local upstream review across compilers and sanitizers? | Exact unpublished three-commit mail series | `git am --3way` reproduces the retained diff; native GCC, native Clang, forced feature selection, and targeted ASan+UBSan correctness all pass |
| E9e | Is speculative decoding or an independent LLM-Runner backend ready for a defensible final-service experiment? | Exact E7c runtime, model, and quality workload | License/provenance, runtime mechanism, exact-model comparability, and meaningful quality-workload gates all pass before any measurement starts |
| E10a | Can an observable cache-only confidence signal separate E9c's known semantic drift before any guard is designed? | Exact E7c service, E9c-exposed tasks, 64 shared tokens, and A/B/C/D post-grammar probabilities | Drift reproduces with stable request-shape labels and every drifted cached top-1 margin is strictly below every stable cached margin |
| E7 | Is the whole project reproducible and judge-readable? | Clean native Arm job | One command emits manifest, raw data, summary, Pareto front, and demo assets |

## E2 frozen protocol

E2 uses one `ubuntu-24.04-arm` job and two builds from the same pinned source.
Every configuration value is identical except `USE_KLEIDIAI`. Both variants run
the same upstream functional test before measurement. Four benchmark rounds per
variant alternate order (`generic/KleidiAI`, then `KleidiAI/generic`) to reduce
time-order bias; each round includes one warm-up and three measured iterations.

The comparison must retain all 12 measured iterations per variant, process RSS,
and runtime proof that only the optimized build created a `CPU_KLEIDIAI` model
buffer. A speedup is accepted only from this paired evidence. The legacy Phi-2
artifact remains a performance-ablation workload, not a quality benchmark.

Before inspecting E2 results, prompt-processing throughput is declared the
primary metric because this Q4 matrix-multiplication path is the direct KleidiAI
target. A material primary win requires a median paired-round speedup of at least
1.05x, improvement in at least three of four paired rounds, and passing tests in
both builds. Decode rate, TTFT, total latency, wall time, and RSS are secondary
metrics and must all be reported even when their direction is unfavorable.

## E3 frozen protocol

E3 uses the Apache-2.0 Qwen2.5-1.5B-Instruct base model in three pinned 4-bit
packages: the official Q4_0 and Q4_K_M GGUF files through llama.cpp, and the
official MNN export through MNN. Both runtime builds use LLM-Runner's common API,
four threads, a 2,048-token context, greedy decoding, and KleidiAI enabled. Exact
repository revisions, file sizes, and SHA-256 values are frozen in
[`../experiments/e3_models.json`](../experiments/e3_models.json).

Quality uses 30 original multiple-choice tasks across arithmetic, logic, code,
data, systems, and evidence reasoning. The prompts and expected answers are
frozen in [`../experiments/e3_tasks.json`](../experiments/e3_tasks.json). Each
variant runs the full suite twice in a fresh process. The parser takes the first
standalone A-D option after case folding. A variant is quality-eligible only if
both repetitions produce identical parsed predictions, its worse repetition is
at least 75% accurate, and it finishes no more than one task behind the best
variant's worse repetition. Invalid or missing answers count as incorrect; no
task may be excluded after results are observed.

The primary cross-runtime comparison uses the same-text task suite: accuracy,
per-case wall latency, model-load time, whole-process maximum RSS, and package
size. The synthetic token benchmark is secondary because tokenizers can encode
different text for the same nominal token count. It uses 128 input tokens, 64
output tokens, one warm-up and three measured iterations in each of three cyclic
rounds: `Q4_0/Q4_K_M/MNN`, `Q4_K_M/MNN/Q4_0`, and `MNN/Q4_0/Q4_K_M`.

Only quality-eligible variants enter the quality/latency/size/RSS Pareto set. No
weighted aggregate score will be invented after measurement: a variant is
excluded from the frontier only when another eligible variant is at least as
good on every reported objective and strictly better on at least one. Hosted
runner results remain screening evidence because PMU, energy, and governor
control are unavailable.

### E3 outcome

Native run `30635472160` completed the frozen contract, but Q4_0, Q4_K_M, and
MNN int4 scored 46.67%, 53.33%, and 13.33% respectively. All predictions were
stable and all variants failed the 75% floor, so the valid Pareto set is empty.
Most responses reached the eight-token limit, especially MNN reasoning
preambles. The cap and parser will not be changed retroactively; any calibration
is a separately versioned experiment. See
[`../results/reports/e3-qwen-frontier.md`](../results/reports/e3-qwen-frontier.md).

## E3b frozen quality-anchor protocol

E3b is a separately versioned model-scale calibration; it does not reinterpret
E3. A local x86 diagnostic gave the failed 1.5B Q4_K_M candidate 64 output
tokens instead of eight and it still scored 16/30 (53.33%), confirming that
truncation alone did not explain the quality failure. A local 7B run was stopped
without a result after the already swap-saturated host read 166 GB through the
storage layer; this protects the machine and supplies no performance or quality
evidence.

The native protocol compares the existing Apache-2.0 Qwen2.5-1.5B-Instruct
Q4_K_M package with the official Apache-2.0 7B Q4_K_M package. Model scale and
package files are the only candidate difference. Both use one patched,
KleidiAI-enabled llama.cpp build, four threads, and a 2,048-token context. The
30 tasks, answers, instruction, greedy decoding, eight-token cap, parser, two
repetitions, 75% absolute floor, and one-task best-candidate rule are unchanged
from E3.

Four alternating paired rounds measure 128-token prompt and 64-token generation
performance with one warm-up and three retained iterations. Only stable
quality-eligible candidates enter the accuracy, same-text latency, peak RSS,
and package-size frontier; no weighted score is used. E3b is a valid calibration
even if its frontier remains empty. Exact files, hashes, order, and rules are
frozen in [`../experiments/e3b_contract.json`](../experiments/e3b_contract.json).
If E3b yields a frontier, deployment selection uses the separately frozen
[`../configs/cloud-quality.json`](../configs/cloud-quality.json) policy: at
least 75% task accuracy, at most 5 seconds median same-text latency, 8 GiB
process RSS, a 5 GB package, and 10 seconds model load on the 16 GiB target.

### E3b outcome

Native run `30643977955` completed the frozen contract. The 1.5B and 7B
candidates scored a stable 16/30 (53.33%) and 22/30 (73.33%) respectively. The
7B candidate was within one task of the best because it was the best, but it
missed the absolute 75% floor by one task; the valid frontier is therefore
empty. Under the separately frozen cloud policy, 7B also exceeded the
5-second same-text ceiling by 129.0 ms and the 8 GiB RSS ceiling by 583,420
KiB. No threshold is relaxed. See
[`../results/reports/e3b-quality-anchor.md`](../results/reports/e3b-quality-anchor.md).

## E3c frozen quality-per-byte protocol

E3c does not modify either empty-frontier result. It tests the stronger-model
hypothesis with the official Apache-2.0 Qwen3-4B-Instruct-2507 source model,
selected before measurement because its official card identifies a non-thinking
4B architecture and reports substantially stronger reasoning and instruction
following than the original Qwen3-4B release. The measured GGUF files are
Apache-2.0 derivatives from one immutable Unsloth revision. Source and
quantization-producer provenance are recorded separately.

Q4_K_M, Q5_K_M, and Q8_0 are the only candidates. Model architecture, chat
template, prompt text, runtime build, patches, thread count, context, and greedy
decoding remain identical; weight quantization is the controlled difference.
The 30 tasks, instruction, parser, two repetitions, eight-token cap, 75%
absolute floor, and one-task best-candidate rule are unchanged from E3 and E3b.
Framework-auto templating uses the chat template embedded in each GGUF and is
now recorded explicitly in every raw quality result.

Three cyclic rounds rotate all candidates through every execution position.
Every round retains one warm-up and three measured 128-input/64-output
iterations. The ingester requires exact model sizes and hashes, source and
producer revisions, both validated source patches, an observed runtime model
buffer for every quantization, and the complete raw quality and performance
records. Only quality-eligible variants enter the unweighted accuracy,
same-text latency, RSS, and package-size frontier.

The previously frozen `cloud-quality` policy is reused byte for byte: at least
75% accuracy, at most 5 seconds median same-text latency, 8 GiB process RSS, a
5 GB package, and 10 seconds model load. The policy checksum is part of the E3c
contract and evidence. Passing E3c requires the planner—not the experiment
author—to find a feasible candidate before model-serving integration begins.
Exact inputs and order are in
[`../experiments/e3c_contract.json`](../experiments/e3c_contract.json).

### E3c outcome

Native run `30647831008` completed the frozen comparison. Q4_K_M, Q5_K_M, and
Q8_0 were stable at 20/30, 19/30, and 18/30 respectively, so none met the 75%
floor and the frontier is empty. Q8_0 had the strongest secondary token
performance but also exceeded the frozen model-load and RSS ceilings. An
independent Python 3.10 ingestion reproduced the summary byte for byte at
SHA-256
`994c5f17d34b83da265ff090219385cfd0faee20e5f22c7a0d12f9fa84484a72`.
See
[`../results/reports/e3c-quality-per-byte.md`](../results/reports/e3c-quality-per-byte.md).

## E3d frozen current-runtime KleidiAI protocol

E3d is a separate calibration, not a reinterpretation of E3c. It tests official
Apache-2.0 Qwen3.5-4B because the pinned model card reports a materially stronger
current reasoning and instruction-following prior. The older LLM-Runner-pinned
llama.cpp predates this architecture, so E3d pins upstream llama.cpp tag
`b10208` and its declared KleidiAI v1.24 dependency rather than moving a branch.

Only Q4_0 and Q8_0 are candidates because source inspection of the pinned
runtime shows that these are the quantized weight types handled by its KleidiAI
backend. The workflow requires a `CPU_KLEIDIAI` model buffer for every candidate;
a build flag alone is insufficient proof. Source model, quantization producer,
chat template, HTTP endpoint, non-thinking template argument, greedy sampling,
seed, thread count, context, tasks, parser, repetitions, and thresholds are
identical across candidates. Quantization is the only candidate-level change.

The unchanged 30-task quality workload runs through the real OpenAI-compatible
`llama-server` path with prompt and generation timings retained per request.
Three cyclic rounds then run the pinned upstream `llama-bench` prompt and token
tests with one warm-up and three retained repetitions. Exact source/package
hashes, the CMake cache, server logs, process RSS, readiness, HTTP responses,
and raw benchmark samples are required by the ingester.

The existing `cloud-quality` policy remains byte-identical. No E3d candidate
can be selected below 75% stable accuracy or above the 5-second latency, 8 GiB
RSS, 5 GB package, or 10-second model-load ceilings. Exact inputs and order are
frozen in
[`../experiments/e3d_contract.json`](../experiments/e3d_contract.json).

Run `30650734222` completed every native measurement. Q4_0 and Q8_0 were both
stable at 20/30 (66.67%), leaving an empty quality-eligible set. Q8_0 improved
the secondary prompt/decode medians to 112.774/14.961 tokens/s, but exceeded
the frozen load and RSS ceilings. The red workflow conclusion is a retained
post-processing-only defect: `llama-bench` emitted a nine-character commit
abbreviation while the ingester expected eight. Python 3.10 independently
validated the complete uploaded artifact after deriving that abbreviation
from the frozen full commit. See
[`../results/reports/e3d-current-runtime.md`](../results/reports/e3d-current-runtime.md).

## E3e frozen bounded-reasoning protocol

E3e is a separately predeclared follow-up to the E3d immediate-answer
calibration. Before any thinking-mode output was observed, the completed Q4_0
portion of E3d showed stable 20/30 immediate answers, a 1,620.8 ms median prompt,
and about 40.4 ms per generated token. Its errors were concentrated in
arithmetic, code, data, and systems questions rather than the already-perfect
logic and evidence categories. This supports testing bounded computation, not
editing prompts or answers after observation.

All candidates use the exact E3d Q4_0 file and pinned current llama.cpp/KleidiAI
build. The runtime's forced-end reasoning sampler is the only mechanism under
test. Exact budgets 0, 16, 32, and 48 tokens have output caps of 8, 24, 40, and
56 tokens respectively, leaving eight tokens after a forced end tag for the
final answer. The largest budget projects below the existing five-second median
ceiling from pre-experiment native timing; this projection is a hypothesis, not
a result.

The two quality repetitions use reverse-balanced execution order and restart
the real server for every candidate/repetition. The unchanged 30 tasks,
instruction, final-content parser, 75% floor, one-task-best rule, deterministic
sampling, four threads, 2,048-token context, and `cloud-quality` policy remain
fixed. Raw final content, separated reasoning content, timing, generated-token
count, process RSS, model load, and verbose `CPU_KLEIDIAI` buffer proof are all
required. Exact inputs are frozen in
[`../experiments/e3e_contract.json`](../experiments/e3e_contract.json).

Run `30651144293` completed all eight native cells but is invalid. Every
zero-budget request consumed all eight output tokens as reasoning and produced
no final answer, contradicting the pinned runtime's documented immediate-end
semantics. The fail-closed ingester rejected it before creating a manifest or
plan. Positive budgets 16/32/48 produced stable but ineligible diagnostic scores
of 13/30, 11/30, and 7/30; they do not rescue the invalid matrix. Source and
unit-test analysis reproduces an unchecked forced-token state transition. See
[`../results/reports/e3e-bounded-reasoning.md`](../results/reports/e3e-bounded-reasoning.md).

## E3f frozen Ministral 3 quality-per-byte protocol

E3f is a new model-family hypothesis selected from primary evidence rather than
from the observed E3 task answers. Official Apache-2.0 Ministral 3 3B Instruct
reports 0.830 MATH Maj@1, emphasizes system-prompt adherence and edge
deployment, and recommends temperature below 0.1 for production. Those
published results select the candidate only; the unchanged native task suite
remains the acceptance evidence.

Both candidates derive from source revision
`b35d4dfe56c142746f54dbd64f579faab2744308` and one pinned Apache-2.0 GGUF
producer revision. Q4_0 is 2,046,375,200 bytes and must prove a
`CPU_KLEIDIAI` model buffer. Q4_K_M is 2,146,497,824 bytes and is the
quality-oriented anchor. Weight quantization is the only candidate-level
difference.

The task instruction text, all 30 tasks and answers, eight-token cap, parser,
two repetitions, greedy decoding, four threads, context, 75% floor, one-task
best rule, current llama.cpp/KleidiAI revisions, cyclic benchmark, and cloud
deployment policy remain fixed. The instruction is placed in the model's
supported system role and each task alone in the user role; this mapping is
frozen before any Ministral response and avoids silently invoking the GGUF
template's large general-purpose default preamble. Exact inputs and order are
in [`../experiments/e3f_contract.json`](../experiments/e3f_contract.json).

### E3f outcome

Native run `30656151957` produced stable Q4_0 and Q4_K_M scores of 21/30 and
23/30. Q4_K_M cleared the unchanged quality floor and every cloud SLO with a
2,146,497,824-byte package, 2,731.7 ms load, 1,798.7 ms median task time, and
4,696,108 KiB maximum quality-process RSS. Pareto64 selected it as the sole
feasible frontier member. Q4_0 directly proved a faster KleidiAI path but was
correctly rejected at 70% accuracy. See
[`../results/reports/e3f-ministral-frontier.md`](../results/reports/e3f-ministral-frontier.md).

## Experimental discipline

- E0–E3 establish feasibility; they do not prove a winning product.
- Run compared variants in the same job/host when possible and randomize or
  alternate order to reduce time/thermal bias.
- Record warm and cold paths separately.
- Use fixed model hashes, input manifests, seeds, and generation settings.
- Prefer medians and p95 with raw trials; never report only the best run.
- Measure setup/build/download time separately from inference time.
- Treat hosted-runner variability as a confounder and repeat headline results on
  a stable named target.
- Stop a branch early when its correctness or quality floor fails.
- Never claim that unlike model families or tokenizers have equivalent quality
  merely because the application output looks plausible.

## E6a frozen source-correctness protocol

E6a isolates a llama.cpp/KleidiAI native-feature selection defect observed in
E1 attempt 4. The exact unpatched flags contain SVE2 modifier names but finish
with `+nosve`; llama.cpp's existing compiled `HAVE_SVE` probe correctly fails,
while a later substring search still selects SVE KleidiAI assembly. The
assembler then rejects those sources under the final flags.

The patch is frozen by SHA-256 in
[`../experiments/e6_contract.json`](../experiments/e6_contract.json). On one
native runner and identical pinned source, the workflow must first reproduce the
specific unpatched failure. It then applies the patch, cleans every generated
object, rebuilds, verifies that KleidiAI SVE sources are absent, passes the
pinned upstream Phi-2 text test, and runs the fixed real-model benchmark. E6a is
a build/source-correctness result, not a speedup claim; a later hot-path E6b
still needs paired performance and mechanism evidence.

### E6a outcome

Native run `30636911078` reproduced the unpatched SVE assembler failure, applied
the byte-identical frozen patch, completed a clean build, passed the pinned
upstream test, and ran real KleidiAI inference. The independently validated
status is `valid_source_correctness_fix`. E6a is accepted as build-correctness
evidence; E6b remains required for a performance claim. See
[`../results/reports/e6a-native-feature-fix.md`](../results/reports/e6a-native-feature-fix.md).

## E6b frozen Q8 vector-store protocol

E6b targets `quantize_row_q8_0`, the activation quantizer used by generic Arm
Q4_0 matrix multiplication. The pinned implementation converts eight NEON
vectors to integer lanes, then extracts and writes all 32 bytes individually.
The single source change narrows those vectors in registers and emits two
128-bit stores. Cross-compiled GCC 15 preflight reduced the function from 124 to
69 static instructions and from 36 to 3 stores; an emulated Arm execution over
8,224 finite values was byte-identical. These are mechanism and harness checks,
not native performance results.

The frozen native experiment builds baseline and patched copies from the same
llama.cpp commit with KleidiAI off, so the controlled path is ggml's generic Arm
Q4_0 implementation. It requires exact standalone equivalence, the upstream
quantization test to pass on both builds, emitted-assembly proof, and unchanged
outputs on the same 30 Qwen tasks. Four alternating paired rounds measure upstream Q8_0
quantizer throughput at 4,096, 65,536, and 655,360 values and real Qwen Q4_0
inference at 128 input and 64 output tokens.

A hot-path win requires at least 1.25x median throughput at 4,096 values, 1.15x
at 65,536, no material regression at 655,360, improvement in the predeclared
number of rounds, no inference metric below 0.98x, and no more than 32 MiB extra
RSS. No weighted score is used. Exact inputs, ordering, and gates are frozen in
[`../experiments/e6b_contract.json`](../experiments/e6b_contract.json).

### E6b outcome

Native run `30640282768` passed every frozen gate. The patch improved paired
Q8_0 quantizer throughput by 2.001x at 4,096 values and 2.029x at both 65,536
and 655,360 values, with all four rounds improved at every size. Emitted scalar
byte stores fell from 32 to zero, while 8,224 finite-input results, both
upstream quantizer tests, and all frozen task outputs were unchanged. Real Qwen
inference was neutral and stayed above the 0.98 guardrail in every round; peak
RSS was identical. See
[`../results/reports/e6b-q8-vector-store.md`](../results/reports/e6b-q8-vector-store.md).

## E6c frozen reasoning-budget correctness protocol

E6c is a separately frozen source-correctness experiment derived from E3e's
invalid mechanism result. On the exact current llama.cpp tag, it first applies
only the new regression-test hunk. The untouched source must abort at the exact
forcing-state assertion. It then applies only the one-condition source hunk,
requires the complete patch diff and two-file change set to match byte for byte,
rebuilds, and requires all 13 upstream reasoning-budget tests to pass.

The patched server then loads the same checksum-pinned Qwen3.5 Q4_0 package on
the four-core native Arm runner with KleidiAI proven through a verbose runtime
probe. Two unchanged 30-task repetitions send real OpenAI-compatible requests
with thinking enabled, budget 0, and an eight-token cap. Every request must emit
zero reasoning characters, terminate normally, contain a standalone A-D final
answer, and remain stable across repetitions.

Patch acceptance depends on those source and runtime correctness obligations,
not on reaching the separate 75% quality reference floor. Accuracy, latency,
load, RSS, and generated tokens remain diagnostic and cannot create a planner
candidate. Exact hashes and gates are frozen in
[`../experiments/e6c_contract.json`](../experiments/e6c_contract.json).

### E6c outcome

Native run `30654805236` reproduced the untouched-source abort, reconstructed
the frozen patch byte for byte, and passed all 13 upstream reasoning-budget
tests. All 60 real Qwen requests emitted zero reasoning characters through the
KleidiAI-backed server. The application contract nevertheless failed: only 5
of 30 stable responses per repetition were standalone A-D answers ending by
`stop`; the other 25 began final-channel explanations and exhausted the frozen
eight-token cap. The validator remains unchanged, so no E6c manifest is
accepted. See
[`../results/reports/e6c-reasoning-budget-fix.md`](../results/reports/e6c-reasoning-budget-fix.md).

## E6d frozen current-upstream rebase protocol

E6d tests whether the three reviewable Arm source contributions survive current
llama.cpp rather than treating their pinned historical validation as permanent.
The upstream input is frozen at tag `b10216`, commit
`876a4321163249c43ca4e986818fab5ab081f282`. The Q8 vector-store and
reasoning-budget patches apply byte for byte. The validated-feature patch has a
context-only rebase because upstream added SME source lists around the same
unchanged flag-substring defect.

The native workflow must reproduce the invalid SVE source selection under
`armv8.6-a+sve2+nosve`, then build the rebased feature correction without those
sources. It applies only the reasoning regression-test hunk to the baseline and
requires the untouched source to abort; the complete series must pass all 13
tests. Baseline and patched trees must both pass `test-quantize-fns`, while
emitted assembly must replace at least 16 scalar byte stores with vector
narrowing and stores.

Four balanced Q8 direct-performance rounds reuse the E6b sizes, iteration count,
and conservative gates: at least 1.25x at 4,096 values, 1.15x at 65,536, no
material regression at 655,360, and the predeclared minimum number of improved
rounds. There is no model run because E6d is an upstream-portability gate; E6a,
E6b, and E6c retain the separate real-model correctness and inference evidence.
Exact hashes, order, and claim scope are frozen in
[`../experiments/e6d_contract.json`](../experiments/e6d_contract.json).

### E6d outcome

Native run `30675654688` passed every frozen gate on llama.cpp `b10216`. The
unpatched feature build reproduced the invalid SVE source selection and the
reasoning baseline aborted at the exact regression assertion. The three-patch
series then built without the invalid source, passed all 13 reasoning tests and
both quantizer targets, and emitted six vector narrows plus two vector stores
instead of 31 scalar byte stores. All twelve paired direct rounds improved;
median ratios were 1.956x, 1.950x, and 1.958x at the three frozen sizes.

Independent ingestion matched the uploaded summary byte for byte at SHA-256
`32e01c0baf21de4679ace516a1ef61f7520dbbbc641d218aa454380e0c9767fa`.
This accepts current-revision applicability, targeted correctness, and direct
Q8 hot-path performance only; it adds no whole-model or upstream-CI claim. See
[`../results/reports/e6d-current-upstream-patches.md`](../results/reports/e6d-current-upstream-patches.md).

## E6e frozen upstream-equivalent Arm CPU lane

E6e broadens E6d's targeted proof without calling one job the full upstream
matrix. It pins the same llama.cpp `b10216` source and three patch files, then
mirrors upstream's `build-cpu.yml` `ubuntu arm64` lane on the native
`ubuntu-24.04-arm` runner. GCC/G++ 14, the full default build target, fatal
warnings, RPC, and the complete `main` CTest label are retained; KleidiAI is
explicitly enabled so the Arm feature patch is exercised.

Acceptance requires the complete build to pass, at least the 47 tests registered
by the frozen source to execute with zero failures, errors, or skips, and the
reasoning-budget plus both quantizer tests to appear among the clean passes.
This is a source/build/unit-integration gate with no performance or model run.
Its maximum claim is one upstream-equivalent native Arm CPU lane for the frozen
series. Exact inputs and gates are in
[`../experiments/e6e_contract.json`](../experiments/e6e_contract.json).

### E6e outcome

Native run `30676413765` passed in 6m16s. The complete fatal-warnings build
succeeded with KleidiAI, RPC, native tuning, and all tests enabled. CTest passed
all 46 `main`-label tests plus the required fixture, 47/47 total, with no
failures, errors, or skips. The reasoning-budget and both quantizer tests were
present among the passes. Independent ingestion reproduced the uploaded summary
byte for byte at SHA-256
`63c0e450d967208e3eb81d21571c73354e8520940933434914920db5d63c27f1`.
The accepted scope remains one upstream-equivalent Arm CPU lane. See
[`../results/reports/e6e-upstream-arm-cpu-lane.md`](../results/reports/e6e-upstream-arm-cpu-lane.md).

## E5a frozen planner-API protocol

E5a is a product/API concurrency gate, not the final inference-server E5 result.
It runs the real fail-closed Pareto64 service on one native Arm runner using the
checksum-pinned E3 manifest and `cloud-balanced` policy. After one readiness and
20 warm-up requests, the probe issues 400 alternating GET/POST plan requests at
concurrency eight. Every response must remain HTTP 200 with
`no_feasible_candidate` and no selected deployment.

The frozen service SLO requires zero request/service failures, at least 100
requests/s, p95 HTTP latency no greater than 50 ms, service maximum RSS no
greater than 256 MiB, and a clean bounded shutdown. The exact contract is
[`../experiments/e5_contract.json`](../experiments/e5_contract.json). Passing
E5a validates the decision plane and DX; it does not substitute for later model
inference concurrency, TTFT, token throughput, and quality evidence.

### E5a outcome

Run `30638049776` returned 400/400 correct responses with zero failures,
369.685 requests/s, 3.361 ms median, 5.153 ms p95, and 23,868 KiB maximum RSS.
It passed every frozen gate. Two retained POST outliers exceeded one second,
creating a separately testable accept-backlog hypothesis rather than a reason to
rewrite E5a. See
[`../results/reports/e5a-planner-api.md`](../results/reports/e5a-planner-api.md).

## E5b frozen selected-inference protocol

E5b is the end-to-end inference-server gate unlocked by E3f. Every cell starts
a fresh pinned llama.cpp `b10208` process through the Pareto64 launch adapter.
The adapter must recompute the selected plan and verify the exact Q4_K_M model
size/SHA-256, model/source revisions, runtime commit, policy, runtime contract,
and manifest before serving. The launch recipe, process RSS, readiness, runtime
buffer evidence, metrics, slots, logs, and every raw HTTP response are retained.

The only comparison is serving concurrency. The baseline uses one server slot
and one client; the candidate uses two continuous-batching slots and two client
workers. Two repetitions run in balanced order: baseline, concurrent,
concurrent, baseline. Each fresh server receives the same two warm-up tasks and
then all 30 unchanged E3 tasks once, using the E3f system-role instruction,
greedy seed, eight-token cap, four threads, and 2,048 tokens of context per
slot.

Quality is the first gate. Every measured response must be HTTP 200, terminate
by `stop`, contain exactly one uppercase A-D letter, reproduce the selected
E3f prediction for that task, and preserve 23/30 accuracy in all four cells.
Only then may the two-slot candidate claim a win: median repeated throughput at
least 1.10x baseline, concurrent median/p95 HTTP latency no greater than
5/10 seconds, deployment readiness no greater than 15 seconds including model
integrity verification, and process RSS no greater than 8 GiB. Exact inputs and
order are frozen in
[`../experiments/e5b_contract.json`](../experiments/e5b_contract.json).

### E5b outcome

Clean run `30659829983` passed end to end. All 120 measured responses matched
E3f and every cell reproduced 23/30 with zero failures. Baseline and two-slot
repeated median throughput were 0.5371 and 0.5472 requests/s, only a 1.0189x
ratio versus the frozen 1.10x minimum. Two-slot pooled median/p95 latency were
3,571.6/4,564.3 ms, readiness was below 4.1 seconds, and maximum RSS was
4,901,032 KiB, so all non-throughput gates passed. The result validates exact
selected-model inference serving but retains the single-slot default. See
[`../results/reports/e5b-selected-inference.md`](../results/reports/e5b-selected-inference.md).

## E5c frozen shared-prefix cache protocol

E5c tests the next inference-server hypothesis on the exact E5b service. The
single slot, single client, selected model, pinned runtime, four threads,
2,048-token context, system instruction, task order, seed, and eight-token cap
do not change. The only variable is llama.cpp's `cache_prompt`: the baseline
explicitly disables it, while the candidate enables it in both the hashed
launch recipe and every request.

The 30 tasks share the system instruction and chat-template prefix. The pinned
runtime documents that caching can skip evaluation of this common prefix, but
also warns that different prompt batch sizes can change logits. Its own
cache-versus-no-cache equality test is skipped on Linux. E5c therefore treats
output stability as an obligation, not an assumption.

Four fresh servers run in balanced order: no-cache, cache, cache, no-cache.
Every one of the 120 measured responses must remain HTTP 200, stop normally,
contain an exact standalone A-D letter, match the frozen E3f prediction, and
reproduce 23/30. The baseline must report zero reused prompt tokens; every
cached request must report at least one reused token. Only after those gates may
the cache claim at least 1.10x repeated median request throughput and at least
1.10x improvement in repeated median prompt-encode time. The unchanged 5/10
second median/p95 latency, 15-second readiness, and 8 GiB RSS ceilings also
apply. Exact inputs and order are frozen in
[`../experiments/e5c_contract.json`](../experiments/e5c_contract.json).

### E5c outcome

Run `30662037235` passed every frozen obligation. All 120 responses matched the
selected E3f predictions and every cell reproduced 23/30. The baseline reported
zero cached tokens; every candidate request reused at least 25. Repeated median
throughput rose from 0.5378 to 0.8991 requests/s (1.672x), while repeated median
prompt encode fell from 1,738.0 to 989.0 ms (1.757x improvement). Pooled median
HTTP latency fell 41.3%, p95 fell 22.1%, and maximum RSS increased by only 6,308
KiB. Prompt caching cleared both 1.10x gates and is eligible for promotion. See
[`../results/reports/e5c-prompt-cache.md`](../results/reports/e5c-prompt-cache.md).

## E5d frozen cached-concurrency interaction protocol

E5d tests whether E5c changes the E5b concurrency conclusion; it does not
reinterpret either result. E5b showed that two uncached slots improved
throughput only 1.0189x, while E5c subsequently removed a large share of prompt
work. Because that changes the prompt/decode balance presented to continuous
batching, the combined setting is a separately testable cross-layer
interaction.

Both configurations use the promoted prompt cache, exact selected model and
runtime, four threads, 2,048 tokens of context per slot, system instruction,
task order, seed, and eight-token output cap. The only measured difference is
one slot/client versus two slots/clients. Each fresh server receives the same
two unmeasured warmups. The single-slot cell routes both to slot 0; the two-slot
cell routes one to each slot so both caches contain the frozen shared prefix.
All measured requests are then auto-scheduled by the normal server scheduler.

Four cells use balanced single/dual/dual/single order. Every one of the 120
measured responses must remain HTTP 200, stop normally, be an exact standalone
A-D letter, match E3f, and reproduce 23/30. Every measured request must report
real prefix reuse. A two-slot win additionally requires at least 1.10x repeated
median throughput, median/p95 HTTP latency below 5/10 seconds, no more than 512
MiB additional maximum RSS, readiness below 15 seconds, and absolute process
RSS below 8 GiB. Exact inputs and order are frozen in
[`../experiments/e5d_contract.json`](../experiments/e5d_contract.json).

### E5d outcome

Run `30664666945` passed every validity, quality, mechanism, latency, readiness,
and memory obligation. All 120 responses matched E3f, every cell reproduced
23/30, both dual slots were preloaded, and every measured request reused at
least 25 prompt tokens. Repeated median throughput rose from 0.9056 to 0.9617
requests/s, only 1.0619x and below the frozen 1.10x gate. Pooled median latency
rose 93.3% to 2,034.4 ms and maximum RSS increased 244,524 KiB. Cached two-slot
serving is rejected; the promoted cached single-slot default remains unchanged.
See
[`../results/reports/e5d-cached-concurrency.md`](../results/reports/e5d-cached-concurrency.md).

## E5e frozen context and KV-cache memory profile

E5e asks whether the promoted E5c single-slot service reserves more KV memory
than this application needs. The retained E5d probes used at most 127 prompt
tokens, and generation remains capped at eight. The 2,048-token default is
therefore compared with a 256-token workload profile, which leaves 1.896x
headroom over the measured 135-token prompt-plus-output bound.

The second factor is K-cache precision: f16, q8_0, and q4_0. V remains f16 in
every profile because the pinned runtime makes quantized V conditional on flash
attention; changing both would confound the memory mechanism. The existing
`auto` flash-attention mode is explicitly bound in every recipe. The exact runtime
must emit an unmeasured allocation record for all six context/precision
combinations, and the validator requires K sizes to decrease with precision,
both K and V sizes to decrease with context, and V to remain constant inside
each context factor.

Twelve fresh servers run two repetitions in forward then reverse order. The
selected model, pinned runtime, four threads, one slot/client, promoted prompt
cache, request content, seed, and output cap remain fixed. A profile may drift
to another valid A-D answer without invalidating evidence from the other
profiles, but it becomes ineligible. Every promotable profile must reproduce
all E3f predictions, retain at least 95% of baseline throughput, keep pooled
median and p95 HTTP latency within 1.10x, leave at least 1.5x measured context
headroom, reduce conservative maximum RSS by at least 128 MiB, become ready
within 15 seconds, and stay below 8 GiB RSS.

Selection is lexicographic, never weighted: among eligible non-baseline
profiles, prefer f16 K over q8_0 over q4_0, then larger context, lower maximum
RSS, and configuration name. This deliberately promotes workload right-sizing
before lossy cache quantization when both solve the memory problem. Exact
inputs and order are frozen in
[`../experiments/e5e_contract.json`](../experiments/e5e_contract.json).

### E5e outcome

Run `30667019678` passed all 12 measured cells and six allocation proofs. The
256-token f16 profile preserved every E3f prediction, retained 99.62% of
throughput, slightly reduced median and p95 latency, and lowered conservative
maximum RSS by 187,760 KiB (183.36 MiB). Its context headroom was 1.896x, so it
cleared every frozen gate and is selected for promotion.

The 256-token q8_0 profile also qualified and saved 247,636 KiB, but the frozen
precision-first selector preferred f16 once f16 met the memory target. Both
q4_0 profiles reproducibly changed `systems-04` from B to C and fell from 23/30
to 22/30, proving that KV precision can affect application quality even under
deterministic decoding. See
[`../results/reports/e5e-kv-context-profile.md`](../results/reports/e5e-kv-context-profile.md).

Promoted-default run `30668306694` subsequently omitted context/KV flags for
the selected-profile cells and reproduced the result: 23/30 twice, 1.0001x
throughput retention, and 187,468 KiB lower maximum RSS. Its provenance binds
the launcher default to `ctx256_k_f16`; independent Python 3.10 ingestion
matched the uploaded summary at SHA-256
`51f1e704259d300a460fb8f386f893dd2c86cd3d2e62c54071d48b099a96e8ac`.

## E5f frozen prompt batch and microbatch profile

E5f asks whether the promoted f16/256 cached single-slot service reserves an
oversized prompt compute graph. Pinned llama.cpp defaults the logical batch to
2,048 and physical microbatch to 512, but causal attention clamps them to the
256-token context, yielding the observed 256/256 baseline and a 40.13 MiB CPU
compute buffer. The source reserves its worst-case prompt graph from the
effective microbatch.

The frozen profiles are the unflagged 256/256 product default, explicit
128/128, and explicit 64/64. The largest retained prompt is 127 tokens, so 128
tests the first one-batch workload boundary; 64 deliberately exercises the
server's split-prompt path. Six fresh servers run the three profiles forward
then in exact reverse. The selected model, 256-token context, f16 K/V cache,
automatic flash attention, shared-prefix cache, one slot/client, four threads,
request order, seed, and output cap do not change.

INFO-level mechanism launches must bind the requested launcher arguments to
the runtime-reported effective logical/physical batches and parse the CPU
compute-buffer allocation. The monotonic trend is reported but does not decide
artifact validity; each candidate's reduction gate decides eligibility. Answer
drift likewise makes only that profile ineligible, because pinned upstream
explicitly warns that caching and different prompt batch sizes can change logits.

A candidate must reproduce every E3f prediction and cached-prefix reuse, save
at least 8 MiB in both the reported compute buffer and conservative maximum
RSS, retain at least 98% of throughput, keep pooled median and p95 latency
within 1.05x, become ready within 15 seconds, and stay below 8 GiB RSS.
Selection is unweighted and lexicographic: lower maximum RSS, smaller physical
microbatch, smaller logical batch, then configuration name. Exact inputs and
order are frozen in
[`../experiments/e5f_contract.json`](../experiments/e5f_contract.json).

### E5f outcome

Native run `30669700602` passed all six measured cells and three mechanism
proofs. The 64/64 profile preserved every E3f prediction twice, reduced the CPU
compute buffer from 40.13 to 10.03 MiB, and lowered conservative maximum RSS by
14,824 KiB. It retained 1.0226x throughput; median latency was 1.0044x baseline
and p95 fell to 0.9095x. It is the only eligible profile and is selected for
promotion.

The 128/128 profile also preserved quality and reduced the compute buffer by
20.06 MiB, but maximum RSS fell by only 1,076 KiB. It missed the frozen 8 MiB
process gate and is not promoted. Independent Python 3.10 ingestion matched
the uploaded summary byte for byte at SHA-256
`396222dd2ec0d66c0985392b0c2b65e4fa1b8a3100f57c4d1d30d50a41f92d4b`.
See
[`../results/reports/e5f-prompt-batch-profile.md`](../results/reports/e5f-prompt-batch-profile.md).

## E5g frozen marginal prompt batch floor

E5g asks whether the promoted 64/64 profile is still oversized. It is a staged
boundary test, not an open-ended sweep: the only candidate is 32/32. Batch 16
is excluded unless 32 first clears every frozen gate.

The retained E5f requests make the cost of this step explicit. After shared
prefix reuse, batch 64 requires 34 prompt chunks across the 30 measured
requests and splits 4 requests. Batch 32 would require 63 chunks and split 28
requests; batch 16 would require 113 chunks and split 29. E5g therefore tests
whether the marginal compute-buffer and RSS savings survive a 1.85x increase
in prompt-chunk work before considering the still smaller profile.

Four fresh servers run 64/64 then 32/32 and immediately reverse that order.
The promoted baseline omits both Pareto64 batch flags, while its generated
llama.cpp recipe must still pin 64/64. The 32/32 candidate binds both layers
explicitly. Model, runtime, request set and order, 256-token context, f16 K/V
cache, automatic flash attention, shared-prefix cache, one slot/client, four
threads, seed, and output cap remain fixed.

The candidate must reproduce every E3f prediction and cached-prefix reuse,
save at least 4 MiB in both the reported compute buffer and conservative
maximum RSS, retain at least 98% of throughput, keep pooled median and p95
latency within 1.05x, become ready within 15 seconds, and stay below 8 GiB
RSS. Exact evidence order and the no-weighted-score selector are frozen in
[`../experiments/e5g_contract.json`](../experiments/e5g_contract.json).

### E5g outcome

Native run `30671733556` passed all four measured cells and both mechanism
proofs. Batch 32 preserved every selected prediction twice, reduced the CPU
compute buffer from 10.03 to 5.02 MiB, retained 1.0116x throughput, and kept
median/p95 latency within the frozen ratios. Maximum RSS increased by 660 KiB,
so the candidate failed the 4 MiB process-memory gate and is not promoted.

The staged study therefore stops before batch 16 and retains 64/64. Independent
Python 3.10 ingestion matched the uploaded summary byte for byte at SHA-256
`374e5af3d8af8c022d76ff51f614c50e1dd25f8948fcc727fe3f983afad984b6`.
See
[`../results/reports/e5g-prompt-batch-floor.md`](../results/reports/e5g-prompt-batch-floor.md).

## E5h frozen Arm weight-repack boundary

E5h asks whether the selected Arm service can expose a memory-constrained tier
without changing its model or numerical representation. The promoted baseline
uses llama.cpp's default extra CPU buffer types. Its retained mechanism log
shows 2,024.36 MiB of mapped weights plus a separate 2,038.92 MiB
`CPU_REPACK` buffer created for optimized Arm weight layouts.

Pinned llama.cpp exposes one clean controlled difference: `--no-repack` sets
`no_extra_bufts`, preventing KleidiAI and generic CPU repack buffer types from
being offered to the model loader. Four fresh servers compare repack enabled
and disabled in A–B–B–A order. Model, runtime build, request order, f16/256/64
serving profile, prompt cache, flash attention, slots, threads, seed, and output
cap remain fixed. Mechanism logs must show both mapped and repack buffers for
the baseline and no repack buffer for the candidate.

The candidate is a separate Pareto memory tier, not a default replacement. It
must reproduce every selected prediction and prefix reuse, save at least 1.5
GiB maximum RSS, stay at or below 3 GiB RSS, retain at least 30% of baseline
throughput, keep median/p95 HTTP latency at or below 5/10 seconds, and become
ready within 15 seconds. The default remains repack enabled even if the memory
tier passes. Exact order and gates are frozen in
[`../experiments/e5h_contract.json`](../experiments/e5h_contract.json).

### E5h outcome

Native run `30672633366` passed both mechanism proofs and all four measured
cells. No-repack reproduced every selected prediction twice, retained cached
prefix reuse, removed the 2,038.92 MiB `CPU_REPACK` buffer, and reduced maximum
RSS from 4,453,532 to 2,381,264 KiB. The 2,072,268 KiB process saving clears
the frozen 1.5 GiB gate and the candidate stays below the 3 GiB tier ceiling.

Throughput retention is 0.4847x; median and p95 HTTP latency are 2.416 and
3.304 seconds, inside the absolute 5/10-second ceilings. The result therefore
retains `repack_off` as an explicit memory tier while `repack_on` remains the
default. Independent Python 3.10 ingestion matched the uploaded summary byte
for byte at SHA-256
`e048f3e25d513430b49fd2ee0a140e8a0f82fe31d79b5fb0aafb36b470190faa`.
See
[`../results/reports/e5h-weight-repack-boundary.md`](../results/reports/e5h-weight-repack-boundary.md).

## E5i frozen Arm Flash Attention ablation

E5i asks whether the selected service's `--flash-attn auto` default delivers a
material end-to-end benefit on Arm. Pinned source maps `off` to
`LLAMA_FLASH_ATTN_TYPE_DISABLED`; auto begins with the fused operation enabled
and resolves it only after a backend allocation and compute probe. The retained
E5h mechanism log records both `flash_attn = auto` and `Flash Attention
enabled`, so this is a resolved graph change rather than a label-only flag.

Four fresh servers run off–auto–auto–off. Both profiles keep the exact model,
runtime build, repacked weights, f16/256/64 service, prompt cache, one slot and
client, four threads, request order, seed, and output cap. Mechanism launches
must record `disabled` without a fused-op success for the baseline and `auto`
plus a successful Flash Attention resolution for the candidate. The hashed
recipe and timed outer command bind the mode independently.

Auto must reproduce every selected prediction and cached-prefix reuse, improve
repeated median throughput by at least 1.05x, avoid median and p95 HTTP latency
regression, add no more than 16 MiB maximum RSS, become ready within 15 seconds,
and stay below 8 GiB RSS. No weighted score is used and no threshold changes
after observation. Exact order and gates are frozen in
[`../experiments/e5i_contract.json`](../experiments/e5i_contract.json).

### E5i outcome

Native run `30674023380` passed both mechanism proofs and all four measured
cells. Auto resolved the fused graph, and both modes reproduced every selected
prediction twice with cached-prefix reuse. Auto improved repeated median
throughput by 1.0322x and median HTTP latency by 6.18%, while maximum RSS fell
7,384 KiB. The throughput gain misses the frozen 1.05x minimum, however, and
p95 HTTP latency increased 6.03%, failing the non-regression gate.

The result is a valid no-win. Pareto64 retains auto as its configured upstream
default but adds no material Flash Attention performance claim. Independent
Python 3.10 ingestion matched the uploaded summary byte for byte at SHA-256
`ca41dd4c8ce7eaec196ac4d6a1320f689755ae4fb9e5d13bb4061f3c24a46ba2`.
See
[`../results/reports/e5i-flash-attention-ablation.md`](../results/reports/e5i-flash-attention-ablation.md).

## E5j frozen Arm serving thread-efficiency profile

E5j challenges the last unmeasured serving assumption: the selected service
uses four inference threads because the native runner exposes four physical
Neoverse N2 cores. Lower thread counts may reduce scheduler and synchronization
work, but they can also lengthen requests. The study therefore treats CPU-time
efficiency and service performance as separate obligations.

Six fresh servers run 4–3–2–2–3–4 threads. Every cell holds the selected model,
pinned runtime, repacked weights, f16/256/64 service, automatic Flash Attention,
shared-prefix cache, one slot/client, task order, seed, and output cap fixed.
The launch recipe and timed outer command bind both `--threads` and
`--threads-batch` to the profile. The probe binds the live server PID, completes
both warmups, then samples `/proc/<pid>/stat` immediately around the 30 measured
requests. It recomputes user, system, total, per-request, and average-core CPU
time from integer counters and the host clock-tick rate. Model load, readiness,
warmups, the Python client, and shutdown are outside that window.

A lower-thread candidate must reproduce every selected prediction and cached
prefix, retain at least 95% of repeated median throughput, keep pooled median
and p95 HTTP latency within 5% of the four-thread baseline, and reduce repeated
median server CPU seconds per request by at least 5%. All cells must also clear
the existing readiness and 8 GiB RSS ceilings. Selection is lexicographic with
no weighted score. If neither candidate clears every gate, four threads remain
the default and the negative result is retained without threshold changes.
Exact inputs, order, measurement boundary, and gates are frozen in
[`../experiments/e5j_contract.json`](../experiments/e5j_contract.json).

CPU time is not energy or power. E5j can support a thread-efficiency claim only;
an energy claim would require independent power measurements.

### E5j outcome

Native run `30677332825` completed all six cells and retained a clear no-win.
Three threads reduced repeated median server CPU seconds per request only 0.11%
while retaining 75.52% throughput; median and p95 latency increased 31.53% and
36.34%. Two threads reduced CPU seconds per request 1.36% while retaining only
51.18% throughput; median and p95 latency nearly doubled. Both candidates missed
the frozen 5% CPU-time reduction, 95% throughput, and latency gates.

Every profile reproduced all selected predictions twice with prefix reuse and
zero request failures. Four threads therefore remains the default. Python 3.10
independent ingestion matched the uploaded summary byte for byte at SHA-256
`747b6795d42be691c07cf5aac38237095477d06149e787cc313ec2b9558c4ff7`.
No energy or power claim is made. See
[`../results/reports/e5j-thread-efficiency-profile.md`](../results/reports/e5j-thread-efficiency-profile.md).

## E6f frozen current-runtime selected-service upgrade lane

E6d proves that all three Arm patches apply to llama.cpp `b10216`, pass their
targeted correctness gates, and preserve the direct Q8 hot-path improvement.
E6e proves a complete upstream-equivalent Arm CPU build and `main` test lane.
Neither runs the selected 2.15 GB Ministral service, which remains pinned to
historical llama.cpp `b10208`. E6f closes that application-level gap.

One native job builds clean `b10208` and `b10216` plus the exact three-patch
series with matched Release, native, KleidiAI, server, test-disabled, and
curl-disabled flags. Four fresh servers run historical–current–current–historical.
The model bytes, repacked weights, f16 K/V cache, 256-token context, 64/64 prompt
batch, automatic Flash Attention, shared-prefix cache, four threads, one
slot/client, request order, seed, and output cap remain identical. Both source
commits/tags, all patch hashes and changed files, CMake caches, server versions,
model buffers, timed commands, recipes, process PIDs, and raw responses are
retained and independently validated.

The current patched runtime becomes an upgrade candidate only if it reproduces
every selected prediction twice with prefix reuse and zero request failures,
retains at least 95% throughput, keeps pooled median and p95 HTTP latency and
repeated median server CPU seconds per request within 5%, keeps repeated median
readiness within 10%, and adds no more than 64 MiB maximum RSS. A pass validates
one native Arm selected-application lane; it does not automatically rewrite the
product launch contract or imply a model-wide speedup, full upstream coverage,
or energy savings. Exact details are frozen in
[`../experiments/e6f_contract.json`](../experiments/e6f_contract.json).

### E6f outcome

Native run `30678703184` passed every frozen gate. Patched `b10216` reproduced
23/30 twice with exact prediction stability and prefix reuse. It retained
100.28% throughput, reduced pooled median/p95 HTTP latency by 0.82%/0.61%, and
used 99.93% of baseline server CPU seconds/request. Median readiness was 4.82%
slower and maximum RSS increased by only 100 KiB, both within their ceilings.

The result makes the current patched source an upgrade candidate for this exact
service only. The retained manifest continues to disallow automatic promotion.
The product later adds an explicit opt-in launch contract that separately binds
the manifest, current source diff, build cache, and binary while leaving the
historical default unchanged. Python 3.10 re-ingestion matched the uploaded
manifest byte for byte at `da95b831…70ace`. See
[`../results/reports/e6f-current-runtime-service.md`](../results/reports/e6f-current-runtime-service.md).

## E6g frozen current-runtime launch integration

E6g verifies that the product adapter—not a manually reconstructed server
command—can consume E6f safely. One native Arm job checks every frozen input,
rebuilds the exact patched `b10216` source, downloads the selected model, and
starts the exact one-slot repacked f16/256/64 cached four-thread service through
`python -m pareto64 launch` with the E6f manifest and current-runtime contract.

The recipe must bind the recomputed E3f model plan, E6f decision, exact git
HEAD/four-file diff, three patch hashes, CMake source/build relationship, server
location/version/binary hash, model bytes, and exact service arguments. The
live server then runs two warmups and all 30 selected tasks. Acceptance requires
23/30 with zero reference drift or failures, prefix reuse in every measured
request, valid PID-bound CPU counters, readiness within 15 seconds, maximum RSS
no greater than 8 GiB, one slot, metrics, and an accepted server exit.

This is a product-integration reproduction, not another optimization comparison.
It cannot promote no-repack, lower-thread, concurrency, alternate-cache, batch,
context, or Flash profiles and supports no energy claim. Exact details are in
[`../experiments/e6g_contract.json`](../experiments/e6g_contract.json).

### E6g outcome

Corrected native run `30679814341` passed every frozen gate. The adapter rebuilt
and verified the exact patched `b10216` source/build/server, launched the exact
service, and reproduced 23/30 across all 30 requests with zero reference drift,
zero failures, and cached-prefix reuse throughout. Readiness was 3.980 seconds,
maximum RSS was 4,453,376 KiB, and the one-slot/metrics/PID checks passed.
Independent Python 3.10 ingestion matched the uploaded result byte for byte at
`13496b5e…404ac9`. See
[`../results/reports/e6g-current-runtime-launch.md`](../results/reports/e6g-current-runtime-launch.md).

## E6h frozen current-runtime no-repack memory-tier upgrade lane

E5h qualifies a no-repack service below 3 GiB on historical llama.cpp `b10208`,
while E6f/E6g validate only the repacked fast service on patched `b10216`. E6h
tests whether that already-measured memory tier can cross the same runtime
boundary without borrowing the fast tier's evidence.

One native job builds clean `b10208` and exact three-patch `b10216`, then runs
four fresh no-repack servers in historical–current–current–historical order.
Every other model, build, f16/256/64, cached, four-thread, one-slot, task, seed,
and output setting is held fixed. Runtime proofs must contain the mapped model
buffer and must not contain a repack buffer.

The current candidate must reproduce every selected prediction and cached
prefix, retain at least 95% throughput, keep median/p95 HTTP latency and measured
server CPU seconds/request within 1.05x, keep readiness within 1.10x, add no more
than 64 MiB maximum RSS, and keep every cell below 3 GiB. A pass is only a
no-repack memory-tier upgrade candidate; E5h remains the evidence for the tier's
fast-versus-memory tradeoff, and a separate launch integration is required.
Exact details are frozen in
[`../experiments/e6h_contract.json`](../experiments/e6h_contract.json).

### E6h outcome

Corrected native run `30690331795` passed every frozen gate. Patched `b10216`
reproduced 23/30 twice with zero drift or failures, retained 100.24% throughput,
used 99.85% of baseline server CPU seconds/request, and produced median/p95
latency ratios of 0.9983x/0.9984x. Readiness improved to a 0.9435x ratio, maximum
RSS increased by 180 KiB, and every cell remained below 3 GiB. Both proof-only
starts showed the mapped model buffer and no repack buffer. Independent Python
3.10 ingestion matched the uploaded result byte for byte at
`7b112b38…53b27f`. This is a current-runtime memory-tier upgrade candidate, not
a launch integration. See
[`../results/reports/e6h-current-runtime-memory-service.md`](../results/reports/e6h-current-runtime-memory-service.md).

## E6i frozen current-runtime no-repack launch integration

E6i closes the product boundary left deliberately open by E6h. One native Arm
job rebuilds the exact three-patch `b10216` source and selected model, then calls
`python -m pareto64 launch` with a new E6h-bound runtime contract and the explicit
`--no-weight-repack` control. The adapter must verify the immutable E3f and E6h
manifests, exact source diff, CMake source/build relationship, server version and
binary hash, model bytes, and the exact one-slot cached f16/256/64 four-thread
memory profile before starting the live server.

The executed recipe must contain exactly one server `--no-repack` argument and
retain the E6h provenance hashes. All 30 requests must reproduce the selected
23/30 map with zero failures or drift and cached-prefix reuse throughout.
Readiness must stay within 15 seconds, the live process must expose one slot and
metrics, and maximum RSS must remain at or below 3 GiB. A pass integrates only
this exact memory tier; it cannot promote the fast tier, other profiles, energy,
or a broader upstream matrix. Exact details are frozen in
[`../experiments/e6i_contract.json`](../experiments/e6i_contract.json).

### E6i outcome

Native run `30691254831` passed every frozen product-integration gate. The
adapter rebuilt and verified exact patched `b10216`, consumed the E6h manifest
and memory runtime contract, generated the no-repack server recipe, and executed
the live selected workload. All 30 requests succeeded, reproduced 23/30 with
zero reference drift, and observed cached-prefix reuse. Readiness was 2.242
seconds, maximum RSS was 2,381,040 KiB, and the one-slot/metrics/process checks
passed. Independent Python 3.10 ingestion matched the uploaded result byte for
byte at `2bcbd7e1…06d2`. See
[`../results/reports/e6i-current-runtime-memory-launch.md`](../results/reports/e6i-current-runtime-memory-launch.md).

## E7a frozen LTO service and runtime-footprint ablation

E7a opens the compiler/build front that the selected service has not yet tested.
One native Arm job checks out exact patched llama.cpp `b10216` and creates two
separate Release, native, KleidiAI server builds. Every source, compiler,
model, service, request, and order setting is identical; the only profile
difference is upstream `GGML_LTO=OFF` versus `ON`. Build-command evidence must
show `-flto` only in the candidate.

The job measures build wall time and copies the server plus every unique
transitive shared library resolved within its own build root into the raw
artifact. Each copied file, its size, and its SHA-256 are independently checked;
system libraries are excluded from the deployment-footprint comparison. It then
runs four fresh services in off–on–on–off order. Each cell performs two fixed
warmups and all 30 selected requests with exact prefix-cache, PID-bound CPU,
readiness, latency, throughput, RSS, slot, metrics, and process evidence.

LTO is eligible only if it reproduces the selected 23/30 prediction map with
zero drift and clears every common guardrail: median and p95 latency and CPU
seconds/request at most 1.05x baseline, readiness at most 1.15x, RSS growth no
greater than 64 MiB, every process below 8 GiB, and build time at most 2x. It
must also clear one disjunctive benefit branch: at least 1.03x throughput with
runtime closure at most 1.05x, or at least 98% throughput with runtime closure
at most 0.95x. No weighted score is used and a miss retains LTO-off. Build time
is a promotion cost, not a headline optimization. A pass is only an upgrade
candidate for this exact service and still requires a separate product launch
integration. Exact details are frozen in
[`../experiments/e7a_contract.json`](../experiments/e7a_contract.json).

### E7a outcome

Native run `30692292700` is a valid no-win. LTO reproduced 23/30 twice with
stable predictions, zero drift or failures, and prefix reuse throughout. It
passed every common guardrail, but throughput improved only 0.137% and the
eight-file transitive local runtime closure shrank only 0.775%, missing both
the 3% performance and 5% footprint benefit branches. LTO-off remains selected.

Median latency improved 0.833%; p95 increased 0.096%; measured server CPU
seconds/request improved 0.047%; readiness was 1.0296x baseline; and maximum RSS
decreased 28 KiB. The candidate build took 213.77 seconds versus 222.25 seconds
for baseline, within the cost guardrail. Independent Python 3.10 ingestion
matched the uploaded result byte for byte at `b48e6c12…b46839`. See
[`../results/reports/e7a-lto-service.md`](../results/reports/e7a-lto-service.md).

## E7b frozen loopback HTTP dependency-pruning ablation

E7b opens a deployment-dependency front exposed by E7a's exact runtime
inventory. Upstream llama.cpp `b10216` enables `LLAMA_OPENSSL` by default to
support HTTPS, while the selected Pareto64 service binds and probes plain HTTP
on loopback. The retained E7a build consequently resolves `libssl.so.3` and
`libcrypto.so.3` even though its measured protocol never exercises TLS.

One native Arm job builds the exact same patched source twice with LTO disabled.
`LLAMA_OPENSSL=ON` versus `OFF` is the only profile difference. Each CMake cache
and complete Ninja command inventory must prove that difference, including the
presence or absence of `CPPHTTPLIB_OPENSSL_SUPPORT`. The existing closure
capture retains raw `ldd` output, independently inventories every transitive
dependency, and copies and hashes each build-local runtime file. The service
matrix then runs four fresh servers in on–off–off–on order with the same model,
quality map, warmups, cached prefix, request sequence, and PID-bound performance
evidence as E7a.

The OpenSSL-off candidate is eligible only if the baseline resolves both frozen
OpenSSL library names, the candidate resolves neither, and it adds no new
dynamic dependency. It must also reproduce 23/30 twice with zero drift or
failures and cached-prefix reuse, retain at least 98% repeated median
throughput, keep the build-local closure no larger, and pass the existing 1.05x
latency/CPU, 1.15x readiness, 64-MiB RSS-growth, 8-GiB process, and 2x build-time
guardrails. No weighted score is used. A miss keeps HTTPS support enabled.

A pass applies only to the exact loopback HTTP service. HTTPS deployments must
keep OpenSSL enabled, and E7b cannot support claims about vulnerabilities,
installed-package/container size, energy, other services, or automatic product
promotion. Exact details are frozen in
[`../experiments/e7b_contract.json`](../experiments/e7b_contract.json).

### E7b outcome

Native run `30695349303` passed every frozen gate. The OpenSSL-on baseline
resolved `libssl.so.3` and `libcrypto.so.3`; OpenSSL-off removed both and added
no dependency. Both profiles reproduced 23/30 twice with stable predictions,
zero drift or failures, and prefix reuse throughout. Candidate throughput was
0.999811x baseline, median/p95 latency ratios were 0.999401x/1.001827x,
measured CPU seconds/request was 1.001021x, readiness was 1.036803x, and maximum
RSS decreased 1,544 KiB.

The eight-file build-local runtime closure fell from 20,058,904 to 19,857,648
bytes, a 1.003% reduction, and build time was 0.948237x baseline. Python 3.10
replay matched the uploaded result byte for byte at `8dffd667…7ffd9b`.
OpenSSL-off is a dependency-pruning candidate for a separate loopback HTTP
launch integration; it is not yet an automatic product default. See
[`../results/reports/e7b-openssl-service.md`](../results/reports/e7b-openssl-service.md).
GitHub Actions clean-checkout run `30695888838` then passed all 141 tests, 32 immutable
hashes, E7b assertions, planner/runtime checks, and demo smoke on exact retained
commit `d00be1c`.

## E7c frozen HTTP-only launch integration

E7c closes E7b's deliberate product boundary. A new immutable runtime contract
binds the retained E7b manifest, selected E3f model, exact three-patch b10216
source, repacked fast-service settings, `GGML_LTO=OFF`, and
`LLAMA_OPENSSL=OFF`. It also requires `libssl.so.3` and `libcrypto.so.3` to be
absent from the local server's dynamic dependency inventory.

One native Arm job rebuilds that exact source/profile and launches it only
through `python -m pareto64 launch`. Before starting the server, the adapter
recomputes the model plan, validates both input hashes, source commit and
full-index diff, CMake source/build binding and required cache entries, server
path/version/hash, and a fresh `ldd` inventory. Those dependency names are
embedded in the recipe; the independent ingester compares them with a separately
retained raw `ldd` capture from the same hashed binary.

The live one-slot loopback HTTP service must reproduce all 30 selected requests
with 23/30 exact quality, zero drift or failures, and prefix reuse throughout.
Readiness must remain at or below 15 seconds, maximum RSS below 8 GiB, and the
slot/metrics/PID-bound CPU/process evidence must validate. A pass integrates
only this exact HTTP build. It does not enable HTTPS or support security,
installed-package, energy, other-profile, or full-upstream claims. Exact details
are frozen in [`../experiments/e7c_contract.json`](../experiments/e7c_contract.json)
and [`../configs/runtime-b10216-http-service.json`](../configs/runtime-b10216-http-service.json).

The first native attempt `30696286405` built and exercised the service but was
rejected before result ingestion because E7c had not frozen the otherwise
unchanged request protocol at the top level. The corrected contract copies the
exact E6g/E6i warmups, task order, output cap, instruction mode, temperature,
seed, and timeout without changing the model, runtime, service, or acceptance
gates. Native run `30696606993` then passed. All 30 requests reproduced 23/30
with zero drift or failures and prefix reuse throughout; readiness was
4,356.71 ms, maximum RSS 4,449,416 KiB, throughput 0.93026 requests/s, and
server CPU time 4.247 seconds/request. The adapter and independent raw `ldd`
capture matched on 13 dependency basenames, with neither forbidden OpenSSL
library present. Python 3.10 replay was byte-identical at
`f4e73971…e1857cf`.

GitHub Actions clean-checkout run `30697133805` passed on the retained E7c result
commit: native `aarch64`, all 145 tests, 35 immutable evidence hashes, exact
planner/runtime assertions, and the dependency-free demo smoke test.

## E8a planned local-device energy and cost evidence

E8a keeps the exact E7c source/build/server recipe fixed and changes only the
request-level shared-prefix policy. Eight fresh-process cells use two
opposite-start four-cell blocks, and the primary energy window excludes model
load, readiness, and warm-ups. Gross joules/request is primary; idle-subtracted
energy is supporting only. Quality, cached-token mechanism, sensor-domain,
governor/power-mode, power-source, thermal, sample-integrity, throughput, and
energy gates are predeclared in
[`final-device-evidence.md`](final-device-evidence.md).

Apple Silicon was selected as the eventual local target, but E8a is deferred
until that physical device is awake and available. No Mac probe, synthetic
energy value, hosted-runner PMU proxy, or CPU-time-as-energy claim is permitted
in its absence.

## E9a frozen final-service comparison

E9a is the intentionally compounded judge-facing comparison between the exact
earliest admitted one-slot E5b service and the exact final E7c service. The
baseline is reconstructed from retained E5b run commit `beb9614`, not from the
later evolved launcher: clean llama.cpp `b10208`, four threads, 2,048-token
context, one slot, continuous batching, no prompt cache, and no explicit
batch/KV/Flash arguments. The final profile is the exact three-patch llama.cpp
`b10216` OpenSSL-off build with four threads, 256-token context, one slot,
64/64 batch, f16 KV, auto Flash Attention, weight repack, and prefix caching.

Both profiles use the same selected 2,146,497,824-byte Ministral 3B Q4_K_M
model, 30-task sequence, two warmups, deterministic request protocol, client
concurrency, and native `ubuntu-24.04-arm` job. Eight fresh processes run in two
opposite-start blocks: E5b/E7c/E7c/E5b followed by
E7c/E5b/E5b/E7c. The artifact retains both historical workflow/launcher
snapshots, source revisions and patch diff, CMake inputs/caches, build commands,
hashed binary closures and `ldd` inventories, host state, per-request answers,
latency and cache counters, PID-bound CPU counters, readiness, process time,
RSS, metrics, and slots.

Before results, acceptance requires 23/30 with the exact selected prediction
map in all eight cells, zero failures or drift, zero baseline cached tokens,
at least one cached token in every final request, both OpenSSL libraries absent
from the final dependency closure, and at most 5% throughput CV per profile.
The final service must reach at least 1.25x repeated-median throughput and at
most 0.85x pooled median latency, pooled p95 latency, and median CPU
seconds/request. Every cell also retains the existing 15-second readiness and
8-GiB RSS ceilings. A miss is a retained no-win; gates are not weakened.

This comparison deliberately combines multiple accepted changes. E9a may
describe the end-product delta but may not assign it to one mechanism. Causal
interpretation remains with the isolated E5c prompt-cache, E5e context, E5f
batch, E6f runtime-upgrade, and E7b dependency experiments. Exact details are
frozen in [`../experiments/e9a_contract.json`](../experiments/e9a_contract.json).

### E9a outcome

Native run `30764802071` passed all gates on a same-job two-logical-CPU
Neoverse N2 runner. E5b/E7c repeated-median throughput was 0.27210/0.46713
requests/s (1.71675x); pooled median latency was 3,576.09/2,090.72 ms
(0.58464x); p95 was 5,251.61/3,705.49 ms (0.70559x); and median CPU
seconds/request was 7.2725/4.2223 (0.58059x). Maximum RSS fell from 4,649,560
to 4,452,100 KiB.

All eight cells reproduced 23/30 with zero drift or failures. Baseline cached
tokens remained zero; every final request reused at least 25 tokens. The final
closure removed the two OpenSSL dependency names and was 201,368 bytes smaller.
One baseline readiness cell took 10.13 seconds while the other three took about
2.74 seconds; it remains included and stayed below the frozen 15-second cap.
Python 3.10 replay was byte-identical at `39424e7f…012d`. See the retained
[`report`](../results/reports/e9a-final-service-comparison.md).

## E9b external holdout selected before results

E9b is supplemental robustness evidence and does not modify the 30-task
admission contract. Before observing any external task result, the evaluation
selected three zero-shot multiple-choice tasks: ARC Easy for grade-school
science, HellaSwag for adversarial continuation, and WinoGrande for referential
commonsense. The pinned datasets are ARC revision `210d026f…0453`
(CC-BY-SA-4.0), HellaSwag `218ec52e…6b76` (MIT), and WinoGrande
`01e74176…67b5` (the original repository's Apache-2.0 license; its Hugging Face
card omits a license field). The task transforms are copied from pinned
lm-evaluation-harness v0.4.12 under MIT.

Each task contributes exactly 100 records chosen without model outputs: rank
every source index by SHA-256 of a frozen salt, task name, and index, then take
the first 100. The generated map hash is `c92200f7…2e49`. Evaluation is
zero-shot with the model chat template, 256-token maximum length, one request
at a time, exact E7c build and launch flags, `acc` plus `acc_norm` where the
task defines it, and complete per-sample logs. There is no accuracy pass gate;
poor scores remain evidence. Q4_K_M is primary and Q4_0 is the preselected
nearest control if the full run remains practical.

The pinned harness's automatic remote tokenizer path requires
`/tokenizer_info`, which llama.cpp b10216 does not expose. A native synthetic
preflight therefore uses Transformers 5.14.1 and the exact Mistral tokenizer
revision `b35d4dfe…4308` with its documented regex correction, saves a local
snapshot, and requires token-for-token equality with llama.cpp `/tokenize`
before testing completion echo logprobs through lm-eval. No ARC, HellaSwag, or
WinoGrande result is allowed during preflight. The immutable details are in
[`e9b_preflight_plan.json`](../experiments/e9b_preflight_plan.json).

### E9b preflight outcome

Native run `30766707967` stopped at the intended compatibility gate before an
external record was loaded. Exact E7c source, patches, build flags, selected
model, launch arguments, and OpenSSL-free dependency closure all validated.
The corrected pinned tokenizer also reached the completion stage only after
every token-parity probe and saved-snapshot round trip passed.

The synthetic completion then lacked the echoed prompt-token logprob shape
lm-eval needs for continuation likelihood. This matches pinned b10216 source:
its OpenAI completions parser rejects `echo=true`. Adapting or patching that
response would no longer test the exact E7c server, so E9b is retained as
`blocked_api_prompt_logprobs`. No ARC Easy, HellaSwag, or WinoGrande score or
sample was observed, tasks were not replaced, and the admission contract is
unchanged. See the retained [`blocker report`](../results/reports/e9b-holdout-preflight-blocker.md).

## E9c frozen prompt-cache generalization fallback

E9c follows the ordered fallback only because the exact E7c OpenAI-compatible
server cannot provide lm-eval's required prompt echo logprobs. It does not
start another server-knob sweep. The source, OpenSSL-off build, Q4_K_M model,
four threads, one slot, 256-token context, f16 KV, 64/64 batch, weight repack,
and every launch argument remain the exact E7c recipe. Only the request-level
`cache_prompt` boolean changes inside paired cells.

Before results, the matrix fixes three prefix working-set cardinalities (one,
two, and four) and three exact tokenized common-prefix lengths (16, 32, and
64). The nine points run in a fixed interleaved order. Every point uses four
fresh server processes in no-cache/cache/cache/no-cache order, two repetitions
per request state, one warmup per active prefix, and the same 16-request task
sequence. This yields exactly 36 fresh processes and 576 measured requests.
Prefix construction is deterministic and validated through b10216's native
`/apply-template`, `/tokenize`, and `/completion` endpoints. The four frozen
variant marker IDs were independently checked against the pinned corrected
Mistral tokenizer before launch. The contract records the one-token BOS
difference between Transformers chat-template tokenization and the native
`add_special=false` endpoint path rather than treating their filler counts as
interchangeable.

Every cell retains standalone answers, selected E3f prediction comparisons,
HTTP/prompt/decode timing, cached/evaluated token counts, PID-bound process CPU,
RSS, readiness, slots, metrics, source/build/binary closure, host state, and
commands. A point is eligible only with zero failures or output mismatches,
the exact cache mechanism, at most 5% throughput CV in both states, at least
1.05x throughput and prompt-encode speedup, and no p95 latency or CPU
seconds/request regression. Output drift and gate misses remain negative
evidence.

For each cardinality, a threshold is emitted only when eligible lengths form a
monotone suffix of the three tested lengths. A non-monotone result emits an
explicit tested-length allowlist; no eligible point disables cache. The policy
never interpolates to untested prefix counts or lengths and makes no energy,
PMU, concurrency, local-device, fleet, or other-runtime claim. Exact details
are frozen in [`e9c_contract.json`](../experiments/e9c_contract.json).

### E9c outcome

Native run `30770403695` completed all 36 fresh processes and 576 measured
requests. The exact cache mechanism was observed at every point, both
repetition CVs remained below 0.48%, and every throughput, prompt-encode, p95,
and CPU-time gate passed. Observed cache-on throughput ranged from 1.9406x to
2.4007x the paired cache-off rate.

The output obligation failed first. There were zero HTTP failures, but the
frozen alternating-prefix prompt construction produced 252 reference
prediction mismatches, 204 non-standalone responses, and 12 paired cache-state
output mismatches. The strict parser and task sequence were not changed. E9c is
therefore retained as `valid_cache_generalization_output_regression`; all three
cardinality policies are disabled and the performance ratios remain diagnostic
only. The earlier E5c decision is not generalized beyond its exact measured
workload. See the retained
[`report`](../results/reports/e9c-prompt-cache-generalization.md).

## E9d frozen local PR-ready patch series

E9d follows the second ordered fallback after E9c completes. It does not change
or rebase any source hunk. The exact b10216 aggregate diff
`e11cdd4109…a9893` is represented as three focused `git format-patch` commits:
validated KleidiAI feature selection, Q8_0 vector stores, and the
reasoning-budget forced-token guard. Each patch has a descriptive message and
`Signed-off-by` trailer; the cover letter names the exact base and existing
native evidence. The series remains local and unpublished.

One native `ubuntu-24.04-arm` job must apply the three messages with
`git am --3way`, reproduce the aggregate full-index diff and four-file set, and
then run independent GCC 14 and Clang 18 lanes. Each compiler builds and runs
`test-quantize-fns` plus all 13 reasoning-budget tests. Each also builds the
KleidiAI quantizer target under the predeclared
`armv8.6-a+sve2+nosve` feature-selection stress configuration and must exclude
the invalid SVE assembly source.

A third targeted Clang debug build enables both llama and ggml AddressSanitizer
and UndefinedBehaviorSanitizer options. The same quantizer and reasoning suites
must exit zero with leak detection enabled and no ASan, LeakSanitizer, or UBSan
diagnostic. Every gate is required; there is no performance claim, later-source
applicability claim, full backend/platform CI claim, or upstream publication.
The immutable inputs and acceptance rules are in
[`e9d_contract.json`](../experiments/e9d_contract.json).

### E9d first result and diagnostic revision

Native run `30772783697` passed exact mail-series application, aggregate-diff
identity, both GCC/Clang native correctness lanes, and both feature-stress
builds. The strict sanitizer build and 13-test reasoning suite passed, but
UBSan stopped `test-quantize-fns` at upstream
`tests/test-quantize-fns.cpp:115` for an incompatible function-pointer call.
That test file is outside the patch series, but the strict gate remains failed
and the retained status is `invalid_pr_ready_patch_series`.

Revision 2 fixes only observed harness representation and retention defects:
the actual CMake `STRING` cache type, array-shaped commit log, and early
provenance capture. It keeps the strict sanitizer acceptance unchanged and
predeclares a pristine-b10216 control plus a non-gating scoped diagnostic to
attribute the failure. See the retained
[`report`](../results/reports/e9d-pr-ready-patch-series.md).

Native diagnostic run `30773922751` confirmed the same function-type UBSan
failure on pristine b10216. The exact patched series passed every GCC, Clang,
feature-stress, ASan, leak, reasoning, and supplemental scoped-UBSan check, but
the unchanged strict gate still failed. E9d closes as
`invalid_pr_ready_patch_series`; the unpublished mail series is retained
without a sanitizer-clean or publication-readiness claim.

## E9e bounded speculative / cross-runtime feasibility

E9e is the final ordered fallback and is explicitly premeasurement. A measured
job is allowed only if four gates pass together: compatible licenses and pinned
provenance, a sound mechanism on the exact E7c runtime, exact or separately
quality-qualified model comparability, and a workload that makes the mechanism
meaningful without changing the 30-task admission contract.

Source inspection stops both candidate lanes. Exact llama.cpp b10216 stores and
logs the requested draft path but loads `params.model.path`; this source is
outside the retained patch series. No compatible official Ministral 3 draft or
model-specific speculator was identified in the inspected exact documentation.
The model-free n-gram path exists, but all 240 retained E9a completions contain
exactly two generated tokens, so the frozen workload provides no meaningful
multi-token draft/verification window.

Arm LLM-Runner commit `8ba39e40…94d5` has no Ministral model configuration.
Its non-llama backends require separate exported artifacts and cannot consume
the selected GGUF Q4_K_M identity; its llama backend would be the same runtime
behind a wrapper. The official Ministral ONNX export is Apache-2.0 and public,
but it is not the selected Q4_K_M artifact or proven output-equivalent.

Licensing and storage gates pass, but mechanism, model-comparability, and
workload gates fail. No model download, runner job, or performance measurement
is launched. The stop decision and exact hashes are retained in the
[`manifest`](../results/manifests/e9e-feasibility.json) and
[`report`](../results/reports/e9e-speculative-cross-runtime-feasibility.md).

## E10a frozen cache-divergence calibration

E10a begins the cache-safe serving lane because E9c showed a large performance
opportunity and a narrow deterministic output boundary, while E9e confirmed
that decode speculation is not meaningful for the current two-token product
workload. It is deliberately an instrument-first calibration, not a cache
policy or a broad knob sweep.

The exact E7c source, three-patch set, OpenSSL-off build, Q4_K_M model, four
threads, one slot, 256-token context, f16 KV, 64/64 prompt batches, repacked
weights, and launch arguments are unchanged. The calibration uses only the
eight task IDs already exposed by E9c, repeated in the same order, and the
single 64-token shared-prefix stress length where E9c observed true letter
flips. One, two, and four alternating prefixes run in fixed order with two
reverse-balanced cache-off/cache-on repetitions and a fresh server for every
cell: 12 processes, 192 measured requests, and 96 paired comparisons.

Each request constrains output to exactly one A/B/C/D byte and asks pinned
b10216's native `/completion` endpoint for its top-32 probability list. A
retained preflight established that b10216 returns the pre-grammar vocabulary
distribution despite the `post_sampling_probs` label. The frozen representation
therefore requires all four exact candidate bytes in that list, aggregates
duplicate candidate tokens, and conditions their raw probabilities on the
A/B/C/D support. This normalization preserves their logit ordering and is the
grammar-restricted candidate distribution. The emitted temperature-one sample
is retained only as mechanism evidence. The deterministic prediction is the
highest conditional candidate probability, with alphabetical tie-breaking.
Raw distributions, raw candidate mass, discarded top-entry count, top-1 margin,
paired Jensen-Shannon divergence, maximum probability delta, top-2 overlap,
prompt-token hash, timings, process CPU, RSS, readiness, source, build, binary,
and dependency closure are all retained.

Before results, the only cache-only separation rule is fixed: at least one
paired top-1 flip must reproduce, each request-shape fingerprint must keep the
same drift label across repetitions, and the maximum cached margin among
drifted pairs must be strictly below the minimum cached margin among stable
pairs. Pair divergence is diagnostic because it requires an uncached shadow.
E10a selects no threshold and observes no holdout. Only a passing calibration
permits a separately frozen guard and independent task holdout; otherwise the
negative result is retained without tuning on unseen tasks. Exact inputs and
boundaries are in
[`e10a_contract.json`](../experiments/e10a_contract.json).

### E10a outcome

Native run `30793728347` completed the 12-cell matrix with zero request
failures and a verified cache mechanism. Cache-on throughput was 3.0869x,
2.3254x, and 2.3618x cache-off for one, two, and four prefixes respectively.
Four of 96 pairs changed candidate top-1, all repeat-stable instances of the
same one-prefix `logic-02` request shape.

The predeclared cache-only margin gate failed: the maximum cached margin among
drifted pairs was 0.0279410, but the minimum among stable pairs was lower at
0.0122079. Pairwise Jensen-Shannon divergence separated the observed drift but
requires an uncached shadow and cannot serve as the frozen cache-only signal.
The retained status is `valid_cache_margin_not_separable`; no threshold is
selected and the independent holdout remains unobserved. The result therefore
stops the proposed margin-guard branch without weakening its quality gate. See
the retained [`manifest`](../results/manifests/e10a-30793728347.json) and
[`report`](../results/reports/e10a-cache-divergence.md).

## E4a frozen accept-backlog tuner

E4a tests the one-second E5a tail as a TCP admission hypothesis. The only server
change is the listen/accept backlog. A bounded search evaluates capacities 5,
16, and 64 in three cyclic orders on the same native Arm job. Every fresh server
receives one readiness request, 20 warm-ups, and 400 measured alternating
GET/POST requests at concurrency 32.

Selection is lexicographic and predeclared: minimize failures, then the number
of requests over 50 ms, choose the smallest backlog capacity, and finally
minimize pooled p95. No weighted score is used. A validated win additionally
requires the default
backlog five to reproduce at least one tail breach in every round, the selected
larger backlog to have zero breaches and failures, p95 at most 50 ms, at least
90% of default median-round throughput, and no more than 10 MiB additional RSS.
The search evaluates all nine configurations even if an early candidate looks
good; total search overhead is reported. Exact details are frozen in
[`../experiments/e4_contract.json`](../experiments/e4_contract.json).

### E4a outcome

Native run `30638730535` validated backlog 64. Across three rounds, backlog 5
had 19 failed requests and 76 tail breaches; backlog 16 had no failures but 44
tail breaches; backlog 64 had neither. Its pooled p95 was 21.862 ms and maximum
RSS was only 120 KiB above the default candidate. The independently re-ingested
result is
[`../results/manifests/e4a-30638730535.json`](../results/manifests/e4a-30638730535.json).

## First workload scope

Start with the smallest public, permissively licensed text path already supported
by LLM-Runner to keep E0–E2 within a 14-GiB ephemeral runner. The exact model and
weights remain a provenance decision. Pin LLM-Runner and every backend by commit;
do not benchmark moving branches.

## Raw result layout (planned)

```text
results/
  manifests/<experiment-id>.json
  raw/<experiment-id>/<variant>/<trial>.json
  reports/<experiment-id>.md
  figures/<experiment-id>.*
```

Large raw artifacts stay in GitHub Actions artifacts until a compact, reviewable
result set is selected for Git.
