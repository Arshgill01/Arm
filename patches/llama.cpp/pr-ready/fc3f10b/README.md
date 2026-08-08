# Q4_K i8mm scale-overhead patch

Base: llama.cpp `fc3f10b3895ebb0ddfe1fcb7fd5950f2c1719339` (2026-08-07).

Apply from a clean checkout:

```sh
git am --3way 0001-ggml-cpu-reduce-Q4_K-i8mm-scale-overhead.patch
```

The same patch also applies cleanly to tag `b10216` at commit
`876a4321163249c43ca4e986818fab5ab081f282`. Reproduce the correctness-first
four-core A/B with:

```sh
MODEL_PATH=/absolute/path/to/q4_k_model.gguf \
  /absolute/path/to/Arm/experiments/e23_arm_kernel_ab.sh /tmp/e23-evidence
```

Measured evidence and claim boundaries are in
`results/reports/e23-arm-q4-k-vector-scale-kernel.md`.
