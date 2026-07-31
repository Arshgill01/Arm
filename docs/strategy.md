# Single-project strategy

Status: provisional decision framework, 2026-07-31. Assessments below are
hypotheses, not measured facts.

## What the project must do

The goal is to optimize the maximum credible number of fronts in one coherent
submission. The organizer does not award points for raw metric count, so breadth
only helps when the same useful workload, baseline, technical changes, and proof
form one memorable story.

## Candidate comparison

| Candidate | Track | Fronts naturally covered | Strength | Principal risk |
| --- | --- | --- | --- | --- |
| **Pareto64: cross-runtime, evidence-first optimizer** | Cloud | model size/quality/speed, server speed, memory, cost, DX, Arm kernels | Searches and publishes the best quality-constrained deployment on Arm; directly reusable | Must add novelty beyond existing benchmark/autotune entries |
| Sensor-to-action voice/safety pipeline | Physical | model size/quality/speed, E2E latency, memory/energy, DX | Strong visual WOW and clear physical consequence | Hardware/control validation and safety metrics within two weeks |
| Private multimodal assistant | Mobile | size/quality/speed, memory/energy/privacy, Arm runtime, UX | Intuitive consumer value; device demo | Crowded idea space and weak server/scaling dimension |
| Single upstream inference kernel patch | Cloud | speed, throughput, Arm-specific implementation | Deepest technical signal and possible upstream impact | Narrower visible product/DX story; patch outcome uncertain |

## Leading hypothesis: Pareto64

**Pareto64** is a multi-objective optimization lab for CPU AI inference on Arm64.
Given a model/workload, quality floor, and deployment SLO, it explores model,
runtime, and system configurations on native Arm, rejects quality regressions,
finds the Pareto frontier, and emits a reproducible deployment manifest plus
judge-ready before/after evidence.

The sponsor-maintained Apache-2.0
[Arm LLM-Runner](https://github.com/Arm-Examples/LLM-Runner) is the strongest
starting substrate. Its common C++/JNI interface already spans llama.cpp, ONNX
Runtime GenAI, MNN, and ExecuTorch on Linux Arm64 and Android; exposes a
KleidiAI on/off baseline switch; builds benchmark binaries; and supports Arm
Streamline annotations. Building above that abstraction turns the idea from a
single-runtime tuner into a workload-aware cross-runtime optimizer.

The configuration space can include:

- runtime/backend selection for a comparable model and task;
- model representation and quantization;
- generic versus Arm KleidiAI microkernels;
- available Arm ISA dispatch (NEON/DotProd/I8MM/SVE/SME where supported);
- compiler/build options;
- thread count and affinity;
- prompt batch and micro-batch size;
- context and KV-cache choices;
- server concurrency and batching; and
- later, profiler/WhyVec-guided source patches in a measured hot path.

Outputs:

- raw, commit-addressed experiment JSON;
- correctness/quality-gated metrics;
- latency/throughput/memory/model-size tables;
- a Pareto-front visualization;
- a recommended configuration for a selected SLO;
- generated build/deploy/validation steps; and
- an optional Arm MCP/Performix evidence bundle.

This creates one product with two layers of value: it optimizes a real AI
application and gives other developers a reusable method for optimizing their
own workloads.

## Differentiation constraint

The current competitive landscape already contains standalone benchmark and
autotune concepts. Pareto64 cannot win by wrapping one runtime's benchmark. Its
defensible wedge is:

1. comparable application-level measurement across several Arm-optimized
   runtimes through one sponsor-maintained API;
2. workload/quality/SLO guardrails instead of “highest tokens per second”;
3. model, runtime, kernel, and system decisions on one Pareto frontier;
4. profiler/compiler evidence connected to an actual source patch; and
5. optional real voice/sensor application proof using Arm's reference assistant.

## How it targets the scorecard

| Judge criterion | Planned proof |
| --- | --- |
| Technical, 40 | Native Arm baselines, cross-runtime adapter, Arm-aware kernels, quality gates, repeated E2E tests, profiler-driven patch |
| WOW, 25 | Live “same task, collapsing resource envelope” Pareto visualization and automatic SLO selection in a real application |
| Impact, 20 | Runtime-agnostic schema, reusable runner, manifests, raw data, failure journal, upstreamable patch |
| DX, 15 | One command from workload to evidence, clear status, clean-checkout CI, concise report |

## Non-negotiable novelty gate

The concept must contribute at least one of:

1. a quality-constrained search method that materially reduces experiment cost;
2. a verified Arm-specific runtime/source patch;
3. a new cross-layer metric/evidence integration using Performix; or
4. a useful cross-runtime adapter/report contract missing from LLM-Runner.

## Track decision gate

Cloud AI becomes final only after a native Arm runner proves:

- Arm LLM-Runner builds and its reference workload runs;
- at least two backends or generic/KleidiAI modes can be compared honestly;
- at least three optimization fronts produce measurable tradeoffs; and
- an output-quality guard runs within CI resources.

If that gate fails quickly, the fallback is a Mobile/Physical version using the
same LLM-Runner substrate and Arm's real-time voice assistant. Apple Silicon is
already confirmed as a valid Mobile AI target.
