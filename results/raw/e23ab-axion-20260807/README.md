# E23a/E23b compact evidence

This directory contains the text subset of the 2026-08-07 Axion Q4_K profile
and SVE/NEON split screen. The controlling interpretation is
[`results/reports/e23ab-arm-q4-k-kernel-profile-and-split-negative.md`](../../reports/e23ab-arm-q4-k-kernel-profile-and-split-negative.md).

The full raw archive, including binary `perf.data`, was intentionally not
committed. Its retained local path, size and SHA-256 are bound by
[`results/manifests/e23ab-axion-20260807.json`](../../manifests/e23ab-axion-20260807.json).

## Minimal source reproduction

```bash
git clone https://github.com/ggml-org/llama.cpp.git llama.cpp
git -C llama.cpp checkout --detach 876a4321163249c43ca4e986818fab5ab081f282
git -C llama.cpp apply /path/to/Arm/patches/llama.cpp/b10216/0001-kleidiai-use-validated-arm-features.patch
git -C llama.cpp apply /path/to/Arm/patches/llama.cpp/0002-arm-q8-vector-narrowing-stores.patch
git -C llama.cpp apply /path/to/Arm/patches/llama.cpp/0003-reasoning-budget-forced-token-guard.patch
git -C llama.cpp apply /path/to/Arm/patches/llama.cpp/b10216/0011-arm-q4-k-split-sve-neon-kernels.patch
cmake -S llama.cpp -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  '-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG -g -fno-omit-frame-pointer' \
  '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG -g -fno-omit-frame-pointer' \
  -DGGML_NATIVE=ON -DGGML_CPU_KLEIDIAI=ON -DGGML_LTO=OFF \
  -DLLAMA_BUILD_TESTS=OFF
cmake --build build --target llama-bench --parallel "$(nproc)"
```

## Measured command shape

Use the frozen model from `experiments/e23a_contract.json`, pin the same four
cores, and run each case in `baseline, candidate, candidate, baseline` order:

```bash
taskset -c 0-3 build/bin/llama-bench \
  --model Ministral-3-3B-Instruct-2512-Q4_K_M.gguf \
  --threads 4 --n-gpu-layers 0 --flash-attn on \
  --batch-size 1024 --ubatch-size 512 --no-warmup \
  --output jsonl --repetitions 3 --n-prompt 512 --n-gen 0
```

For a promotion-quality rerun, build baseline and candidate from the same
configuration and switch only the candidate patch. The retained throughput
cells are a negative screen, not a promotable benchmark claim.
