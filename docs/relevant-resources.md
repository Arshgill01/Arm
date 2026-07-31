# Vetted technical resources

Checked: 2026-07-31 UTC. Pin exact commits before experiments because most of
these projects are moving quickly.

## Best project foundations

### Arm LLM-Runner

[Arm-Examples/LLM-Runner](https://github.com/Arm-Examples/LLM-Runner) is the
strongest sponsor-maintained base and was active in July 2026. It uses a thin
C++/JNI API over four backends:

- llama.cpp;
- ONNX Runtime GenAI;
- MNN; and
- ExecuTorch.

It targets native Linux Arm64, macOS Arm64, and Android cross-builds. Its build
exposes `LLM_FRAMEWORK`, `USE_KLEIDIAI`, `BUILD_BENCHMARK`, architecture presets,
and Arm Streamline annotations. The explicit KleidiAI on/off control is unusually
valuable for a valid same-workload ablation. Primary code is Apache-2.0 with
preserved BSD third-party notices.

Important limits:

- not every model/format is accelerated in every backend;
- current llama.cpp KleidiAI acceleration is documented for Q4_0;
- current ONNX Runtime GenAI KleidiAI acceleration is documented for INT4 block
  size 32;
- its llama.cpp build disables an affected SVE path through documented presets;
- comparable task output across different model families is not automatically a
  quality-equivalent runtime comparison; and
- some default model downloads may need a Hugging Face account/token.

### Real-Time Voice Assistant

[Arm-Examples/Real-Time-Voice-Assistant](https://github.com/Arm-Examples/Real-Time-Voice-Assistant)
is an Apache-2.0/BSD-notice Android voice and optional vision application. It
combines whisper.cpp with selectable LLM backends and enables KleidiAI on Arm64.
It is a strong real-workload shell for a polished Mobile/Physical demo, but not a
substitute for original optimization work.

### Other useful Arm examples

- [CMSIS-Executorch](https://github.com/Arm-Examples/CMSIS-Executorch):
  Apache-2.0 PyTorch-to-quantized-Ethos-U template with selective operators,
  Docker, and CI.
- [CMSIS-Zephyr-Executorch](https://github.com/Arm-Examples/CMSIS-Zephyr-Executorch):
  Apache-2.0 ExecuTorch/Zephyr examples.
- [topo-simd-visual-benchmark](https://github.com/Arm-Examples/topo-simd-visual-benchmark):
  compact visual SIMD-versus-baseline presentation pattern; useful inspiration,
  not the product base.
- [Arm Learning Paths source](https://github.com/ArmDeveloperEcosystem/arm-learning-paths):
  official evolving tutorial source. Documentation is CC BY-SA 4.0 and embedded
  sample code is MIT-0; retain the separation and attribution.

There is no challenge-owned starter repository. The Devpost Resources page links
the general Arm developer ecosystem, and the current project gallery is not yet
published.

## Arm optimization libraries

| Project | Role | License/current caution |
| --- | --- | --- |
| [KleidiAI](https://gitlab.arm.com/kleidi/kleidiai) ([mirror](https://github.com/ARM-software/kleidiai)) | Dependency-free AI microkernels for Neon, SVE, SME, SME2 | Apache-2.0 plus BSD pieces; use runtime integration unless contributing a kernel |
| [KleidiCV](https://gitlab.arm.com/kleidi/kleidicv) | OpenCV adapter and optimized CV routines with ISA dispatch | Apache-2.0; confirm supported OpenCV version before using 5.x |
| [Arm Compute Library](https://github.com/ARM-software/ComputeLibrary) | Full CPU/Mali operators, runtime, memory, scheduling | MIT plus third-party notices |
| [CMSIS-NN](https://github.com/ARM-software/CMSIS-NN) | Cortex-M neural-network kernels | Apache-2.0 |
| [CMSIS-Ethos-U](https://github.com/ARM-software/CMSIS-Ethos-U) | Ethos-U driver/runtime | Apache-2.0 |
| [Vela](https://gitlab.arm.com/artificial-intelligence/ethos-u/ethos-u-vela) | Compile quantized LiteRT/TOSA for Ethos-U | Apache-2.0; cycle estimates are not device measurements |
| [Arm NN](https://github.com/ARM-software/armnn) | Historical inference runtime | MIT but explicitly legacy/unmaintained; no new security fixes, avoid as a base |

## Active runtimes

- [llama.cpp](https://github.com/ggml-org/llama.cpp): MIT; native KleidiAI CPU
  backend plus CLI, benchmark, server, and Android example.
- [XNNPACK](https://github.com/google/XNNPACK): BSD; CPU backend used by LiteRT,
  ExecuTorch, and MediaPipe; integrates KleidiAI.
- [ExecuTorch](https://github.com/pytorch/executorch): BSD; mobile/embedded with
  XNNPACK and Arm/Ethos-U paths.
- [ONNX Runtime](https://github.com/microsoft/onnxruntime) and
  [ONNX Runtime GenAI](https://github.com/microsoft/onnxruntime-genai): MIT;
  general inference and GenAI APIs with performance tooling.
- [LiteRT](https://github.com/google-ai-edge/LiteRT) and
  [MediaPipe](https://github.com/google-ai-edge/mediapipe): Apache-2.0;
  production on-device inference and perception pipelines.
- [MNN](https://github.com/alibaba/MNN): Apache-2.0; compact cross-platform
  runtime with KleidiAI integration. Test ISA detection/fallback because recent
  Android illegal-instruction reports are a relevant failure mode.
- [vLLM](https://github.com/vllm-project/vllm): Apache-2.0; cloud serving and
  batching with an official Arm INT4 learning path.
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp): MIT; local speech.

## Measurement stack

- [Arm Performix](https://developer.arm.com/servers-and-cloud-computing/arm-performix):
  free proprietary/EULA Neoverse profiler with SSH targeting, PMU/top-down
  analysis, machine-readable output, and CI integration. It is explicitly
  recommended by the challenge, not mandatory.
- [Arm Performance Studio](https://developer.arm.com/tools-and-software/arm-performance-studio):
  free/EULA; Streamline timelines, CPU/GPU, memory bandwidth, thermal analysis,
  and headless automation for Android/Linux.
- Runtime tools: `llama-bench`, `onnxruntime_perf_test`, ExecuTorch
  benchmark/Inspector, and LLM-Runner's benchmark binary.
- [MLPerf Inference](https://github.com/mlcommons/inference): Apache-2.0;
  heavyweight but useful measurement conventions.
- [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness):
  MIT; possible language-model quality regression guard.
- `perf`, `/usr/bin/time -v`, RSS, thermal, energy sensors, and raw application
  telemetry. If hosted hardware blocks PMU/energy data, record the gap.

## Native Arm environments

- Public GitHub Actions Arm64 Linux: free, ephemeral, current public runner docs
  list 4 vCPU/16 GiB. Good for smoke/CI regression; weak for stable PMU/thermal
  headlines.
- AWS T4g: an official free trial is currently available through the end of
  2026; it is burstable Graviton2 and therefore good for setup/CI, not a clean
  high-core headline without credit accounting.
- AWS Graviton m7g/r8g, Google Axion C4A, Azure Cobalt 100: stable cloud options
  for final Cloud evidence; cost/credentials require user confirmation.
- Raspberry Pi 5: accessible Cortex-A76 Physical target with Neon/DotProd but no
  SVE/SME2.
- Modern Android/Apple Silicon: suitable for Mobile; use runtime ISA detection
  and preserve generic/Neon fallback for SME2 experiments.

## License and provenance traps

### Selected E3 model artifacts

Qwen2.5-1.5B-Instruct is the first quality-frontier model. The Qwen-maintained
GGUF repository and taobao-mnn MNN export both declare Apache-2.0 and derive from
the same 1.54B-parameter instruction model. The official Q4_0 and Q4_K_M files
are 1,066,227,232 and 1,117,320,736 bytes; the six-file MNN package totals
879,481,306 bytes. Repository revisions, every package file size, and every
SHA-256 are pinned in `experiments/e3_models.json` rather than trusting a moving
`main` URL.

The two formats use different quantization implementations and tokenizers may
not map a nominal token count to identical text. Therefore E3 treats the same-
text quality suite's latency as the cross-runtime comparison and token-rate
measurements as secondary diagnostics.

E3b adds the official Qwen2.5-7B-Instruct Q4_K_M package at pinned revision
`bb5d59e06d9551d752d08b292a50eb208b07ab1f`. Its two files total
4,683,073,632 bytes and declare Apache-2.0. It is a quality anchor against the
unchanged 1.5B Q4_K_M task protocol, not a post-hoc replacement for the E3
cross-runtime result. Exact sizes and SHA-256 values are in
`experiments/e3b_models.json`.

- Runtime licenses do not grant model/data licenses. Record exact weight source,
  license, version, and SHA-256.
- [AI-on-Arm](https://github.com/arm-education/AI-on-Arm) uses an Arm Education
  EULA, not an OSI license. Learn from it but do not copy it into this Apache-2.0
  submission.
- Do not copy CC BY-SA tutorial prose into Apache documentation without the
  required separation and attribution.
- Raspberry Pi IMX500 model zoo artifacts have mixed licenses, including AGPL
  and proprietary terms. Review each chosen model separately.
