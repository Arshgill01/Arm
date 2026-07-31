# E0 — native Arm feasibility

- Status: **pass**
- Run: [GitHub Actions 30630496081](https://github.com/Arshgill01/Arm/actions/runs/30630496081)
- Commit: `6f7cd918dc39db3b73a92f1da621dbae125dd07d`

## Question

Can the current repository obtain reproducible native Arm evidence without new
paid infrastructure?

## Result

Yes. The `ubuntu-24.04-arm` public runner provided:

- native `aarch64` Linux;
- four Neoverse N2 cores and about 16 GiB RAM;
- SVE/SVE2, DotProd, I8MM, and BF16 CPU features; and
- GCC 13.3, CMake 3.31.6, and Python 3.12.3.

The portable compute probe ran 21 samples of 100 million iterations. Median was
118.631 ms, p95 was 118.819 ms, and coefficient of variation was 0.000797
(0.0797%). Its checksum was identical in every trial.

## Interpretation

This is sufficiently stable for fast feasibility work and same-host/same-job
ablation screening. The noise number applies only to this short, compute-bound
probe; it does not predict LLM inference variance.

The runner exposes neither a CPU scaling-governor path nor unprivileged PMU
access (`kernel.perf_event_paranoid=4`). It cannot prove energy use or a
microarchitectural mechanism. Final headline results still require repeated runs
and, ideally, a named stable Arm cloud/device target with Performix or equivalent
counter access.

## Evidence

- Compact raw trials: [`../manifests/e0-30630496081.json`](../manifests/e0-30630496081.json)
- Full environment JSON: retained as the workflow artifact
  `e0-native-arm-30630496081-1`.
- Harness: [`../../experiments/e0_native_arm_probe.py`](../../experiments/e0_native_arm_probe.py)
  and [`../../experiments/e0_microbench.c`](../../experiments/e0_microbench.c).

## Next decision

Proceed to E1: pin Arm LLM-Runner, build its smallest public text path on this
runner, capture backend/model metadata, and run its upstream test/benchmark.
