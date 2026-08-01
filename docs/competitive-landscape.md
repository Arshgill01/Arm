# Competitive landscape and winner signals

Checked: 2026-08-01 UTC. The 2026 Devpost gallery is still not public, so repositories
below are unverified public competitor intelligence, not official submissions.
The live gallery page displayed roughly 2,000 participants but no published
entries; participant count is not a submission count.

## Prior winner signals

Arm selected six projects from 142 submissions in the 2025 Arm AI Developer
Challenge. Arm's recap highlights offline privacy/trust, performance per watt,
right-sized/quantized models, and utility with poor connectivity.

Three prior entries supply the best combined template:

- [Chuck'it](https://devpost.com/software/chuck-it), first: strongest product
  coherence and polish. It replaced an impractical LLM with a hybrid local
  embedding/OCR/label pipeline, quantified user-facing latency, and made privacy
  a feature. Its linked source is now unavailable and its public methodology is
  too thin for the stronger 2026 optimization bar.
- [DreamMeridian](https://github.com/msradam/dream-meridian), second: strongest
  evidence package. It proves Raspberry Pi hardware, documents architecture
  flags, publishes a deterministic 57-query task suite, reports correctness and
  failures, separates install/write-up/results, and makes validation easy.
- [Epictetus](https://github.com/abishekmuthian/Epictetus), third: strongest
  model-to-runtime Arm chain. A fine-tuned 270M model, conversion, dynamic INT8,
  constrained context/cache, XNNPACK/KleidiAI, and measured Snapdragon behavior
  form one understandable optimization ladder.

Other useful patterns:

- [InstaMeme](https://github.com/MkFoster/InstaMeme): narrow, visual input-to-
  artifact magic moment and polished native tests.
- [Jackqr](https://github.com/mizzleinetimi/jacker): reliability fallbacks,
  simplified output contracts, and device-aware model ladder.
- [Pocket Garden](https://github.com/AmandineFlachs/PocketGarden): visually
  compelling multi-model system across three Raspberry Pis with clear diagrams.

The 2025 weakness to surpass is consistent: many entries publish absolute speed
but no baseline, repeated-run statistics, memory/energy evidence, or retained
task quality. The 2026 organizer has now explicitly asked for that comparison.

## Current public competitors

| Repository | Observed wedge | Implication |
| --- | --- | --- |
| [gravitonkv](https://github.com/StephenSook/gravitonkv) | KV precision sweep, six models, context ladder, task/KL quality, PMU mechanism | Strongest evidence package observed; a simple precision sweep is not enough |
| [armsmith](https://github.com/kitfunso/armsmith) | Graviton autotuner, Performix, quality guard | Generic “autotuner + profiler” territory is occupied |
| [kleidibench](https://github.com/yannan000/kleidibench) | One-command KleidiAI benchmark/CI | KleidiAI toggling alone is commodity |
| [arm-pulse](https://github.com/sirmos/arm-pulse) | llama.cpp benchmark, MCP, dashboard | A dashboard around tokens/second is not differentiation |
| [PocketTune](https://github.com/ayanbag/PocketTune) | Android feature detection, autotuning, chat | Mobile feature-aware tuning needs a more specific application thesis |
| [nightjar](https://github.com/hungtruongOwolf/nightjar) | NEON gate and multimodal camera guard | Real workload and visible outcome raise the competitive bar |
| [arm-optimize-physical-AI](https://github.com/stanleyoz/arm-optimize-physical-AI) | Pi 5 INT8 vision and servo loop | Physical submissions already connect optimization to an actuator |

No code or claims from these projects should be reused without independent
license/provenance review and reproduction.

## Defensible gap

The most open space is not another llama.cpp benchmark. It is a planner that:

- measures a real end-to-end workload through one API across several runtimes;
- rejects variants that violate task quality, memory, thermal, energy, or
  response-time budgets;
- connects model/runtime/system decisions on one Pareto frontier;
- produces a reproducible deployment recipe and ablation evidence; and
- proves itself in a memorable voice/vision/sensor or production-server loop.

The strongest submission combines DreamMeridian's evidence rigor, Chuck'it's
product coherence, and Epictetus's transparent Arm-specific optimization chain.

## Demo/evidence pattern

The clearest three-minute structure is:

1. 0:00–0:15 — real user problem and one-sentence result.
2. 0:15–0:30 — actual Arm device/instance identity.
3. 0:30–0:55 — live baseline.
4. 0:55–1:20 — two or three decisive technical changes.
5. 1:20–2:05 — uninterrupted optimized end-to-end magic moment.
6. 2:05–2:35 — before/after table with retained quality and resource use.
7. 2:35–2:50 — one-command reproduction and reusable artifacts.
8. 2:50–3:00 — impact and track fit.

For Cloud, show live request/load metrics and instance identity. For Mobile, show
the local runtime and visibly disable networking. For Physical, keep sensor input
and the resulting action in the same continuous shot.
