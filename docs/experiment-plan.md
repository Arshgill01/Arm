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
