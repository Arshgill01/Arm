# Track analysis

Last verified: 2026-07-31 UTC.

## Published tracks

| Track | Required runtime boundary | Organizer examples | Strong evidence |
| --- | --- | --- | --- |
| Physical AI | Arm device/edge system perceives sensor input and produces a physical-world decision, signal, or action | Robotics, vehicles, drones, smart cameras, embedded/industrial devices; real or simulated camera/lidar/radar/IMU/GPS/audio/force; ROS 2, simulation, autonomy | Real or simulated sensor-to-action E2E latency, accuracy/safety, memory/energy, deployment reproducibility |
| Cloud AI | Inference on Arm cloud or on-prem server compute, normally exposed through an API/UI | AWS Graviton, Azure Cobalt, GCP Axion, Ampere; quantization/pruning; llama.cpp, vLLM, ExecuTorch, LiteRT; agents and MCP | Concurrent throughput, p50/p95/p99 latency, TTFT/tokens-per-second, memory per request, cost, scale-out behavior |
| Mobile AI | Inference runs locally on an Arm phone, tablet, laptop, Android/iOS/Windows-on-Arm client | Local text, vision, speech, multimodal; ExecuTorch, ONNX Runtime, LiteRT/TFLite, MediaPipe | Cold/warm latency, TTFT, memory/model size, quality, offline operation, energy/thermal behavior |

## Can one project optimize many fronts?

Yes. The rules require selecting one track, but they do not restrict the number
of optimization fronts within it. A single cohesive project can legitimately
show improvements across:

- disk size;
- peak/resident memory;
- output quality at a fixed size;
- cold start and warm latency;
- time to first output/token;
- steady-state throughput;
- concurrency/scalability;
- energy or cost per successful task;
- Arm-specific kernels/runtime configuration; and
- install, benchmark, migration, and debugging experience.

The key is cohesion: these must be measurements of one useful workload and one
clear product story, not unrelated microbenchmarks.

## Initial strategic read (not yet a project decision)

Cloud AI is the easiest track to benchmark continuously from this development
environment and the most natural place to combine model, runtime, server,
scaling, cost, and developer-experience optimization. Physical AI offers a more
visually distinctive demo but adds hardware/simulation and control-correctness
risk. Mobile AI makes privacy/energy benefits intuitive but requires reliable
access to an Android, iOS, or Windows-on-Arm validation target.

A winning candidate should make the same optimization ladder reusable across
several Arm tiers while selecting the track that matches its actual runtime.
Cross-track relevance can support impact and WOW factor, but the submission must
remain unambiguous about its one selected track.

## Decision gate

Do not lock a track until candidate concepts are scored on:

1. Real Arm hardware available within 24–48 hours.
2. Strength and number of honest measurable deltas.
3. Quality/correctness benchmark availability.
4. Arm-specific technical depth beyond generic quantization.
5. Visual demo clarity in under three minutes.
6. Reusable community artifact or upstreamable patch.
7. Cost/time to run statistically meaningful trials.
8. Licensing and model/data download feasibility.

