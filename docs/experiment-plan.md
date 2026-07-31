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
