# Pareto64 product core

Pareto64 turns validated native Arm experiment manifests into an explicit,
quality-constrained deployment decision. The planner is standard-library Python
and has no network, model, or runtime dependency at decision time.

```text
validated E3/E3b/E3c/E3d/E3e/E3f manifest
        │
        ▼
evidence consistency checks ──reject──► invalid input
        │
        ▼
predeclared quality gate ──────reject──► recorded reason
        │
        ▼
named SLO requirements ────────reject──► recorded reason
        │
        ▼
recomputed Pareto frontier
        │
        ▼
explicit lexicographic priority ───────► deployment plan
```

No weighted score is used. A candidate can enter the frontier only after the
source experiment declares it quality-eligible and it passes every named SLO.
The planner then removes only dominated candidates and chooses from the remaining
frontier using the user-visible priority order.

## Run the current plan

```bash
python3 -m pareto64 plan \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json \
  --output results/plans/e3f-cloud-quality.json
```

The retained E3 through E3e policy runs return `no_feasible_candidate`. E3
rejects Q4_0, Q4_K_M, and MNN int4 at the frozen quality gate. E3b then rejects a
larger 7B Q4_K_M anchor at a stable 73.33%, one task short of the unchanged 75%
floor. E3c rejects Qwen3-4B Q4_K_M, Q5_K_M, and Q8_0 at stable accuracies from
60.00% to 66.67%; Q8_0 also misses the load and RSS ceilings. Pareto64 does not
allow any resource or quality near-miss to become a deployment.

E3f is the first selected plan. Ministral 3 3B Q4_K_M reached a stable 76.67%
and passed the frozen latency, RSS, package, and load ceilings. The smaller,
faster Q4_0/KleidiAI path remained rejected at 70.00%, so the selected result
preserves the same quality-first behavior.

The same decision is available through the bounded HTTP service:

```bash
python3 -m pareto64 serve \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json \
  --host 127.0.0.1 \
  --port 8080
```

The service exposes `/healthz`, `GET /v1/plan`, `POST /v1/plan`, and `/metrics`.
Its default TCP accept backlog is 64, selected by frozen E4a native Arm evidence
after capacities 5, 16, and 64 were each evaluated in three cyclic rounds. The
`--backlog` option remains available for an explicit deployment override.

## Launch the selected inference runtime

The launch adapter recomputes the plan, refuses an empty frontier, verifies the
selected model's exact size and SHA-256, checks catalog/source revisions and the
pinned llama.cpp commit, and writes a hashed launch recipe before replacing
itself with `llama-server`:

```bash
python3 -m pareto64 launch \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json \
  --models experiments/e3f_models.json \
  --contract experiments/e3f_contract.json \
  --service-manifest results/manifests/e5h-30672633366.json \
  --service-constraints configs/service-memory.json \
  --model-root /path/to/models \
  --llama-server /path/to/llama-server \
  --recipe-output /tmp/pareto64-launch.json \
  --parallel 1
```

The adapter preserves the measured four-thread deterministic serving
configuration and defaults to the E5e-selected 256-token context per slot.
`--threads` is a bounded experimental control: it can select from one thread up
to the four-thread runtime contract, writes the resolved value to the recipe,
and binds both llama.cpp inference and prompt-batch thread pools. Four remains
the default unless the frozen E5j native profile validates a lower value.
Increasing `--parallel` increases total context proportionally so each slot
retains that allocation. `--context-per-slot` remains an explicit bounded
override for a separately validated workload profile.
`--batch-size` and `--micro-batch-size` are a bounded pair that default to the
E5f-selected 64/64 profile. Both requested and effective values are written to
the hashed recipe. Explicit paired overrides reproduce larger profiles when a
different workload has passed its own application-level quality gate.
Weight repacking remains enabled by default. `--no-weight-repack` is a bounded
escape hatch that records `weight_repack: false` in the recipe and passes the
pinned runtime's `--no-repack` flag; E5h is the frozen quality, memory, and
performance boundary for treating that path as a separate memory tier.
When `--service-manifest` and `--service-constraints` are present, the adapter
recomputes that measured service decision, requires it to reference the selected
model, binds both additional hashes into the recipe, and applies the selected
repack mode. A missing input, empty service frontier, or conflicting manual
repack flag aborts before launch. Without a service policy, the historical
repack-on default and bounded manual escape hatch remain unchanged.
Flash Attention remains `auto` by default. `--flash-attention auto|on|off`
records the exact upstream mode in the recipe; E5i is the frozen Arm ablation
that must prove the resolved auto graph materially outperforms the disabled
graph before Pareto64 adds a performance claim for that default.
`--dry-run` performs every integrity and selection check and writes the recipe
without starting the server.

### Opt into the current patched runtime

The default path above remains bound to the immutable E3f `b10208` selection
evidence. E6f separately accepts patched llama.cpp `b10216` for one exact
service. Opting into it requires all four provenance inputs:

```bash
python3 -m pareto64 launch \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json \
  --models experiments/e3f_models.json \
  --contract experiments/e3f_contract.json \
  --runtime-manifest results/manifests/e6f-30678703184.json \
  --runtime-contract configs/runtime-b10216-selected-service.json \
  --llama-source-root /path/to/patched/llama.cpp \
  --llama-build-root /path/to/llama.cpp-build \
  --model-root /path/to/models \
  --llama-server /path/to/llama.cpp-build/bin/llama-server \
  --recipe-output /tmp/pareto64-current-launch.json \
  --parallel 1
```

Before writing the recipe, the adapter verifies the E6f and E3f manifest hashes,
accepted upgrade decision, selected candidate/commit, exact four-file git diff,
three patch hashes, build directory and CMake source binding, Release/native/
KleidiAI/server flags, executable location and version, and model bytes. The
recipe records the actual server binary and CMake-cache hashes.

This opt-in path is deliberately narrower than the historical adapter. It
accepts only repacked weights, f16 K/V cache, 256-token context, 64/64 prompt
batch, automatic Flash Attention, shared-prefix caching, four threads, and one
slot—the exact E6f profile. Lower threads, multiple slots, no-repack, alternate
caches, larger contexts/batches, explicit Flash modes, or changed log verbosity
fail before launch. Those profiles remain available with the historical pin and
need their own current-source application evidence before being admitted here.

Prompt-prefix reuse is enabled by default after E5c reproduced every selected
answer and improved repeated median throughput 1.672x. The pinned llama.cpp
runtime warns that cache-dependent prompt batch sizes can alter logits, so the
hashed recipe records the mode and `--no-prompt-cache` remains available for
workloads that have not passed an equivalent application-level correctness
gate.

E5b validated the full launch path on native Arm with zero answer drift across
120 measured requests. Its two-slot candidate improved repeated median
throughput by only 1.89%, below the frozen 10% minimum, while pooled median
latency rose from 1.81 to 3.57 seconds. The default remains one slot; `--parallel`
is an explicit deployment override, not a promoted optimization.

E5c kept one slot and changed only shared-prefix caching. All 120 answers again
matched the selected evidence, while throughput rose from 0.5378 to 0.8991
requests/s and pooled median latency fell from 1.807 to 1.062 seconds. Unlike
the two-slot candidate, prompt caching cleared both frozen 1.10x performance
gates and is promoted.

E5d then tested whether the promoted cache makes two-slot serving worthwhile.
All 120 answers remained exact and both slots demonstrated prefix reuse, but
throughput improved only 1.0619x while pooled median latency rose 93.3% and
maximum RSS increased 244,524 KiB. The cross-layer candidate missed the same
1.10x gate, confirming cached single-slot serving as the default.

E5e profiled 2,048/256-token contexts against f16, q8_0, and q4_0 K caches while
holding the selected model, f16 V cache, request set, and serving path fixed.
The 256-token f16 profile preserved all selected predictions, retained 99.62%
of baseline throughput, and reduced maximum RSS by 187,760 KiB. q8_0 also met
every gate, but the precision-first selector kept f16. q4_0 reproducibly changed
one correct answer, so it was excluded. The 256-token f16 profile is promoted.

E5f held that selected service fixed and profiled effective prompt batches of
256/256, 128/128, and 64/64. Only 64/64 passed every gate: it preserved all 60
selected predictions, reduced the CPU compute buffer 40.13→10.03 MiB, lowered
maximum RSS by 14,824 KiB, and retained 1.0226x throughput. It is selected for
promotion and is now the launcher default; 128/128 missed the process-RSS gate.

E5g tested the next batch floor without changing that default. Batch 32 reduced
the reported compute buffer from 10.03 to 5.02 MiB and preserved every selected
prediction, 1.0116x throughput, and both latency gates. Conservative maximum
RSS increased by 660 KiB, however, so it failed the frozen 4 MiB process-memory
gate. Pareto64 retains 64/64 and, per the staged contract, does not test 16/16.

E5h then isolated the selected service's Arm weight-repack allocation. Repack
enabled produced 2,024.36 MiB mapped plus 2,038.92 MiB repacked model buffers
and reached 0.9295 requests/s at 4,453,532 KiB maximum RSS. The no-repack path
preserved every selected prediction and prefix reuse, removed the repack buffer,
and lowered maximum RSS by 2,072,268 KiB to 2,381,264 KiB. Its throughput fell
to 0.4505 requests/s, or 48.47% retention, with 2.416/3.304-second median/p95
HTTP latency. It clears the frozen low-memory gates but does not replace the
faster default; operators opt into the separately validated tier with
`--no-weight-repack`.

E5i ablated the configured `flash_attention: auto` path against an explicit
disabled graph. Both mechanism proofs passed and all 120 answers remained
exact. Auto improved throughput from 0.9013 to 0.9303 requests/s (1.0322x),
reduced median HTTP latency 6.18%, and lowered maximum RSS by 7,384 KiB, but its
p95 latency increased 6.03%. It missed the frozen 1.05x throughput and p95
non-regression gates. Auto remains the configured upstream-default behavior,
but Pareto64 makes no material Flash Attention serving-performance claim.

E5j freezes the remaining thread-count question on the same selected service.
Fresh four-, three-, and two-thread servers run twice in reverse-balanced order.
The probe samples Linux `llama-server` user and system CPU counters after both
warmups and immediately around the 30 measured requests, excluding model load,
readiness, client work, and shutdown. A lower-thread profile must reduce median
server CPU seconds per request by at least 5%, retain at least 95% throughput,
preserve median and p95 latency within 5%, and reproduce every selected answer
and cached prefix. CPU time is explicitly not an energy or power measurement.

Native E5j rejected both lower-thread profiles. Three threads retained 75.52%
throughput for only 0.11% lower CPU seconds per request; two threads retained
51.18% throughput for only 1.36% lower CPU seconds per request. Both also missed
the latency gates. All answers and cached prefixes remained exact, so four
threads stays the launcher default and no thread-efficiency or energy claim is
promoted.

E6f then compared the exact selected service on clean `b10208` and patched
`b10216` with four fresh servers in reverse-balanced order. Current source
reproduced 23/30 twice, retained 100.28% throughput, used 99.93% of baseline
server CPU seconds/request, slightly improved median/p95 latency, and added only
100 KiB maximum RSS. The source is therefore accepted by the explicit
evidence-bound upgrade path above; it does not silently replace the historical
runtime or broaden the validated service envelope.

E6g exercised that path rather than only unit-testing its checks. Native run
`30679814341` rebuilt the exact patched source, recomputed the model decision,
verified every runtime input, and started the server through `python -m pareto64
launch`. All 30 requests succeeded, reproduced 23/30 without prediction drift,
and observed prefix reuse; readiness was 3.980 seconds and maximum RSS was
4,453,376 KiB. This validates only the explicit exact-service integration. The
historical default and every other current-runtime profile remain unpromoted.

E6h separately tested the historical no-repack memory tier on exact patched
`b10216`. It reproduced 23/30 twice, retained 100.24% throughput, used 99.85% of
baseline CPU seconds/request, added 180 KiB RSS, and kept all four cells below
3 GiB. That makes the exact profile a current-runtime upgrade candidate, but the
adapter still rejects it: E6h is comparison evidence, not the distinct
evidence-bound launch integration required to expand the current-runtime
contract.

E6i validates that separate integration without weakening the fast contract. A
second runtime contract binds the E6h manifest and exact no-repack service, and
the shared validator explicitly accepts only the E6f fast or E6h memory evidence
shapes. Native run `30691254831` launched through the adapter with
`--no-weight-repack`, reproduced 23/30 with zero drift or failures and prefix
reuse throughout, and used 2,381,040 KiB maximum RSS. The exact memory profile
is now admitted on patched b10216; unmeasured profiles still fail closed.

E7a tests the remaining whole-program compiler/build choice against the exact
patched fast service. `GGML_LTO=ON` preserved the 23/30 map and every shared
guardrail, but improved throughput only 0.137% and reduced the hashed transitive
local runtime closure only 0.775%. Both frozen benefit branches failed, so the
product keeps LTO off and adds no new launch path.

E7b tests the next build boundary exposed by that dependency inventory. The
selected service uses plain HTTP on loopback, while upstream HTTPS support links
OpenSSL by default. `LLAMA_OPENSSL=OFF` removed exactly `libssl.so.3` and
`libcrypto.so.3`, added no library, reproduced 23/30 twice, retained 99.981%
throughput, and reduced the hashed build-local closure 1.003%. Every latency,
CPU, readiness, RSS, and build-cost guardrail passed. This qualifies an exact
HTTP-only dependency-pruned profile for a separate launch integration; the
current adapter remains unchanged and HTTPS must keep OpenSSL enabled.

E7c closes that deliberate integration boundary without weakening the E6g fast
contract. A third runtime contract binds the E7b manifest, exact
`LLAMA_OPENSSL=OFF` cache, patched source/build/binary/model, repacked service,
and absence of both OpenSSL libraries. Native run `30696606993` launched only
through `python -m pareto64 launch`, reproduced 23/30 across all 30 requests
with zero drift or failures and prefix reuse throughout, and retained a
13-library inventory that matched an independent raw `ldd` capture. Readiness
was 4.357 seconds and maximum RSS was 4,449,416 KiB. The claim is limited to
this exact loopback HTTP service; HTTPS, security, installed-package, energy,
other-profile, and full-upstream claims remain excluded.

E9a measures the complete product delta without converting it into a causal
claim. In one native two-logical-CPU Arm64 job, four reverse-balanced fresh
processes per profile compared the exact E5b one-slot recipe with exact E7c.
Every cell reproduced 23/30 with zero drift or failures. E7c delivered 1.71675x
throughput, 0.58464x median latency, 0.70559x p95 latency, 0.58059x CPU
seconds/request, and 0.95753x maximum RSS. Its closure also omitted the two
OpenSSL libraries. One E5b readiness repetition reached 10.13 seconds but
remained under the frozen 15-second ceiling and is not discarded. The result
validates the compounded end product only; E5c, E5e, E5f, E6f, and E7b remain
authoritative for mechanism-specific interpretation.

E16c adds an exact two-worker deployment tier without changing the default
single-process recipe. On one native four-core Arm host, two workers mapping the
same identity-bound read-only packed arena reduce summed PSS from 6,815,078 KiB
to 4,723,364 KiB while retaining 1.00044x aggregate throughput and every exact
answer. The tier is admitted only when the sidecar's model, source diff, CPU
feature set, vector length, format, tensor layouts, and complete SHA-256 all
match. It does not promise lower per-process RSS, cross-host portability, cold
startup, energy, or fleet economics.

E16d turns that retained mechanism into four fail-closed product commands. The
inputs remain the promoted E16c contract/evidence, exact selected GGUF, and exact
sidecar-capable runtime closure:

```bash
python3 -m pareto64 sidecar-prepack \
  --contract experiments/e16c_contract.json \
  --evidence results/manifests/e16c-30851609576.json \
  --model /path/to/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
  --llama-server /path/to/runtime/bin/llama-server \
  --sidecar /path/to/ministral.sidecar \
  --index /path/to/ministral.index.json \
  --receipt /path/to/receipt.json \
  --lifecycle-dir /path/to/lifecycle-evidence \
  --scratch-root /path/to/bounded-scratch

python3 -m pareto64 sidecar-verify \
  --contract experiments/e16c_contract.json \
  --evidence results/manifests/e16c-30851609576.json \
  --model /path/to/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
  --llama-server /path/to/runtime/bin/llama-server \
  --sidecar /path/to/ministral.sidecar \
  --index /path/to/ministral.index.json \
  --receipt /path/to/receipt.json \
  --output /path/to/verification.json

python3 -m pareto64 sidecar-launch \
  --contract experiments/e16c_contract.json \
  --evidence results/manifests/e16c-30851609576.json \
  --model /path/to/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
  --llama-server /path/to/runtime/bin/llama-server \
  --sidecar /path/to/ministral.sidecar \
  --index /path/to/ministral.index.json \
  --receipt /path/to/receipt.json \
  --workers 2 \
  --plan-output /path/to/launch-plan.json \
  --ready-output /path/to/ready.json \
  --outcome-output /path/to/outcome.json

python3 -m pareto64 sidecar-cleanup \
  --receipt /path/to/receipt.json \
  --output /path/to/cleanup-plan.json
```

`sidecar-prepack` starts the exact final service once to emit every runtime
packed tensor, constructs the canonical sidecar, hashes the entire container
and every tensor, removes only the command's fresh raw-tensor directory, and
writes a read-only receipt. The receipt binds the model, source diff, CPU
identity, runtime closure, sidecar hash, and index hash. Existing output paths
or insufficient bounded scratch space fail before construction.

`sidecar-verify` repeats the full identity, container, tensor, runtime, receipt,
and read-only checks. `sidecar-launch` performs one complete verification of the
immutable sidecar before starting distinct ports on the same inode. After each
worker becomes healthy, the deployment boundary independently proves that its
mapping is read-only, shared, and uses the verified inode. It emits a plan and
an optional post-health ready record. A `--stop-file` can request controlled
group shutdown for supervisors. `sidecar-cleanup` is dry-run by default and deletes
only the two absolute, hash-matching paths in the retained receipt when
`--execute` is supplied; the receipt remains.

The lifecycle receipt separates observed E16b same-job warm readiness, E16c
two-worker summed PSS, unmeasured cold storage, and a warm-only construction
amortization estimate. It explicitly excludes cold-start, per-process RSS,
energy, money, and maintenance claims. E16d completed the native product path
but failed its final UTF-8 reader; E16e retains that failure and passes all 14
unchanged lifecycle gates twice with a byte-safe replay of the exact artifact.

The asymmetric scheduler remains experimental and disabled. E15b's strict
two-CPU confirmation found only 1.00427x throughput for split 2/4 and exactly
1.00000x CPU seconds/request, so it failed the predeclared efficiency gate and
the product retains tied 4/4 thread pools.

## Deploy workers behind the certificate gateway

`pareto64 deploy` composes sidecar validation, multiple workers, mapping proof,
and the OpenAI-compatible certificate gateway into one supervised lifecycle:

```bash
python3 -m pareto64 deploy \
  --contract experiments/e16c_contract.json \
  --evidence results/manifests/e16c-30851609576.json \
  --model /path/to/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
  --llama-server /path/to/runtime/bin/llama-server \
  --mode shared \
  --sidecar /path/to/ministral.sidecar \
  --index /path/to/ministral.index.json \
  --sidecar-receipt /path/to/sidecar-receipt.json \
  --workers 4 \
  --threads 1 \
  --registry /path/to/certificates.json \
  --plan-output /path/to/deployment-plan.json \
  --ready-output /path/to/ready.json \
  --deployment-receipt /path/to/deployment-receipt.json \
  --stop-file /path/to/stop
```

`--mode normal` launches the exact control with private runtime repacks and
requires no sidecar arguments. `--mode shared --prepack` may construct a fresh
sidecar before launch when bounded scratch and lifecycle paths are supplied.
The command records command-lifecycle readiness, starts all workers, verifies
every shared mapping through `/proc/PID/maps`, and writes a final read-only
receipt even when a worker or gateway fails.

Clients send standard `/v1/chat/completions` requests to the ready record's
gateway origin and must include `X-Pareto64-Session-ID`. An unknown transition
runs cached shadow plus uncached oracle and serves only the oracle. Exact,
materially reused transitions become identity- and session-bound certificates;
certified routes use cache with periodic oracle revalidation. Any successful
output drift revokes the certificate immediately. `/healthz` and `/metrics`
expose worker, route, oracle, certification, denial, and revocation state. The
registry is integrity protected, atomically replaced, persistent across
restarts, and isolated across sessions.

### Measured multi-worker product boundary

E22a runs this exact `pareto64 deploy` path in normal and shared modes at one,
two and four workers on native Arm. All 420 measured requests are exact across
modes; each shared worker proves the verified sidecar inode through a read-only
shared mapping. Shared/control throughput stays within 0.55% at every count,
while summed PSS savings grow from 2,086,925 KiB at two workers to 6,261,824 KiB
at four. The ephemeral GitHub host blocks PMU access and is not a stable
performance authority, so E22a is a mechanism/product preflight only.

E22b then measures the complete fixed-memory curve on one eight-core Google
Axion Neoverse V2 host with 16,723,460,096 physical bytes, no SMT and no swap.
The private path admits six workers; normal-8 fails before readiness with a
retained `oom_kill` transition. The shared path admits eight workers. E22c
repeats normal-6 and shared-8 four times each in reverse-balanced order.
E22d repeats that frozen comparison on a fresh instance with a different
provider instance ID. Across both hosts, eight balanced pairs and 3,360 exact
requests deliver 1.3568x median aggregate throughput and 59.32% lower median
summed PSS. Combined median readiness is 2.2138x and remains outside the
promoted claim, so the product claims only same-provider, same-machine-class
warm steady-state fixed-memory density—not faster readiness, cold startup,
energy, billing economics or fleet behavior.

## Select a measured service profile

Model selection and service-profile selection are separate obligations. The
model planner answers which package is eligible to deploy. The service planner
then answers which quality-valid, natively measured operating point fits the
deployment envelope:

```bash
python3 -m pareto64 service-plan \
  --manifest results/manifests/e5h-30672633366.json \
  --constraints configs/service-throughput.json \
  --output results/plans/e5h-service-throughput.json

python3 -m pareto64 service-plan \
  --manifest results/manifests/e5h-30672633366.json \
  --constraints configs/service-memory.json \
  --output results/plans/e5h-service-memory.json
```

The throughput envelope requires at least 0.9 requests/s and selects
`repack_on`. The memory envelope caps maximum RSS at 3,145,728 KiB and selects
`repack_off`, including the exact `--no-weight-repack` launcher argument. A
2-GiB cap has no feasible measured profile, so the planner refuses deployment.

The service policy supports explicit lower bounds for throughput and upper
bounds for median/p95 HTTP latency, maximum RSS, and readiness. It first rejects
answer-drifting or SLO-ineligible profiles, then recomputes the non-dominated
frontier and applies the declared lexicographic priority. The output records
both input hashes, every observed metric and rejection, the feasible profiles,
frontier, selected runtime settings, and `weighted_score_used: false`.

Only the selected schema-1 E5h manifest is accepted. Its quality permission,
zero-failure validation, selected-tier names, model-buffer proof, and
repack-buffer consistency must agree. Tampered or merely diagnostic evidence
fails closed before a plan is created.

## Constraint contract

The schema-1 policy has two explicit parts:

- `requirements`: `at_least` for higher-is-better accuracy and `at_most` for
  lower-is-better latency, RSS, package size, and model-load time;
- `selection_priority`: a unique ordered list used only after quality, SLO, and
  Pareto filtering.

Every numeric metric must be finite and non-negative. Schema-1 E3, E3b, E3c,
E3d, E3e, and E3f quality-frontier manifests are accepted. Candidate sets, quality
decisions, experiment status, and the experiment's declared eligible set must
agree or the planner rejects the manifest. The output records hashes of both
input files, all observed metrics, all rejection reasons, the feasible set,
frontier, selected candidate, and the fact that no weighted score was used.

## Current boundary

The evidence-to-decision core, HTTP decision plane, and selected-runtime launch
adapter are implemented. E5a validated planner correctness, concurrency,
latency, and RSS; E4a then eliminated the observed admission tail under a
stricter load. The adapter remained locked until E3f passed the quality gate, so
Pareto64 cannot turn an invalid measurement into a deployment. E3b, E3c, and
E3d all produced valid empty frontiers. E3d's current-runtime Qwen3.5
candidates both reached a stable 66.67%. E3e was rejected before frontier
creation because budget 0 violated the runtime's documented immediate-end
mechanism. E6c subsequently validated the exact source correction and zero
reasoning output on native Arm, but failed its frozen eight-token standalone
final-answer obligation; it creates no deployable candidate.

E3f now selects Ministral 3 3B Q4_K_M after a stable 76.67% result and clean
resource SLOs. E5b is the frozen native Arm gate for the launch adapter and
two-slot inference service. The service passed every quality and resource gate,
but two slots missed the throughput-improvement threshold, so inference serving
is validated while the single-slot default is retained. E5c subsequently
validated quality-preserving shared-prefix caching at 1.672x throughput and
promoted it within that single-slot default. E5d separately tested their
interaction and rejected cached two-slot serving at only 1.0619x throughput.
E5e then selected a 256-token f16 context, saving 183.36 MiB maximum RSS without
answer drift or material performance loss.
