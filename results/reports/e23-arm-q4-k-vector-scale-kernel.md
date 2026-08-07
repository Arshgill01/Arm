# E23 Arm Q4_K vector-scale kernel result

Status: accepted narrow Arm-native win.

The candidate changes the AArch64 Q4_K × q8_K I8MM prefill kernel, preserves
the generic and decode paths, and makes matched whole-model prompt processing
faster on both measured Arm microarchitectures. The primary Axion result is
1.1069x at pp128 and 1.0787x at pp512. The independent Neoverse N2 result is
1.0998x and 1.0843x. Decode is effectively unchanged. The desired 1.20x
whole-model target was not reached and is not claimed.

## Selection and source dispatch

The [opportunity audit](arm-native-kernel-opportunity-ranking-2026-08-07.md)
ranked the existing Q4_K × q8_K NEON/I8MM compute loop first, tiled FFN fusion
second, and missing q8_K activation packers third. Exact b10216 and upstream
`fc3f10b3895ebb0ddfe1fcb7fd5950f2c1719339` have the same relevant dispatch
and source gap; KleidiAI covers Q4_0/Q8_0, not Q4_K/q8_K.

On the Axion host, `svcntb()` returned 16 bytes. The 256-bit SVE condition was
therefore false and inference selected `ggml_gemm_q4_K_8x8_q8_K`'s
NEON/I8MM body. The baseline profile measured:

| Case | Q4_K GEMM | q8_K pack | Flash attention | IPC | L1D refill/access |
| --- | ---: | ---: | ---: | ---: | ---: |
| pp128 | 53.55% | 2.45% | 14.04% | 4.29 | 0.641% |
| pp512 | 46.38% | 2.20% | 36.52% | 4.46 | 0.453% |

This rejected a packer-only headline and selected the compute loop. The final
candidate pp128 profile attributes 56.14% of flat cycle samples to the changed
public kernel, proving real whole-model execution. The same profile records
2.87% in q8_K packing, 17.59% in flash attention and 11.44% in Q6_K GEMM.

## Mechanism

The retained [b10216 patch](../../patches/llama.cpp/b10216/0013-arm-q4-k-neon-vector-scale-kernel.patch):

1. separates the inactive 256-bit SVE body from the hot NEON dispatcher;
2. decodes eight Q4_K scales directly to an `int8x8_t`, widens and pairs them
   once per subblock, and consumes those vectors in the four column pairs; and
3. prevents GCC from fully unrolling that four-way loop.

The public hot function shrinks from `0x142c` to `0x08a4` bytes; the separated
SVE helper still exists, so this is a hot-function layout reduction rather
than deletion of SVE support. The direct 3072×128×3072 kernel improves from
about 17.5 ms to 14.95 ms (approximately 1.17x) on Axion and 1.1620x on N2.
These microbenchmarks support the mechanism but are not the headline.

The formatted [upstream mail patch](../../patches/llama.cpp/pr-ready/fc3f10b/0001-ggml-cpu-reduce-Q4_K-i8mm-scale-overhead.patch)
applies with `git am --3way` to both audited upstream `fc3f10b` and b10216.
The patched current-upstream `ggml-cpu` cross-build passed with GCC 15.2 for
`armv8.6-a+i8mm+dotprod`. On Axion, the formal patch and measured candidate
have the same complete `.text` section SHA-256,
`811c13359aeab9095f52de0408148264a48f6f4c08ef66bd43053ba581976d0d`.

## Correctness before performance

The native candidate and generic reference were compared for block counts
1, 2, 3, 12 and 36 with seeds 1, 17 and 1234567. All 15 cases passed. Maximum
NMSE was `2.38526954695e-13`; maximum absolute error was
`0.000274658203125`, exactly matching the baseline kernel's reference error.

Two deterministic full-model checks then switched only `libggml-cpu.so` under
one executable:

- the bounded 64-token response was byte-identical with SHA-256
  `c7096812e27d74355df83efbacdf43fd15378ec39ab3c1b85f8894d3a363b088`;
- the live 446-token-prompt demonstration was byte-identical with SHA-256
  `54684e05a7eaffd4a1cb124b0b4ef9fd4ad868685f9004ddf2db0bee46274b21`.

These are path-equivalence checks, not a general model-quality claim.

## Matched whole-model results

Every reported benchmark used one executable, four threads pinned to cores
0–3, CPU-only inference, flash attention on, identical model bytes and build
flags, and reverse-balanced `baseline, candidate, candidate, baseline` process
order. Each process contributed three samples on the primary and N2 results,
for six samples per implementation and case. The two adjacent-model Axion
screens used two samples per process, for four per implementation and case.

### Google Axion / Neoverse V2

| Model and case | Baseline tok/s | Candidate tok/s | Ratio |
| --- | ---: | ---: | ---: |
| Ministral 3B Q4_K_M pp128 | 69.7590 | 77.2162 | **1.1069x** |
| Ministral 3B Q4_K_M pp512 | 51.7816 | 55.8594 | **1.0787x** |
| Ministral 3B Q4_K_M tg128 | 24.7092 | 24.8436 | 1.0054x |
| Ministral 3B Q4_K_S pp128 | 70.3139 | 78.9700 | **1.1231x** |
| Ministral 3B Q4_K_S pp512 | 52.0997 | 56.7465 | **1.0892x** |
| Qwen2.5 1.5B Q4_K_M pp128 | 142.7305 | 155.7375 | **1.0911x** |
| Qwen2.5 1.5B Q4_K_M pp512 | 116.6313 | 125.3555 | **1.0748x** |

### Neoverse N2 GitHub runner

| Qwen2.5 1.5B Q4_K_M case | Baseline tok/s | Candidate tok/s | Ratio |
| --- | ---: | ---: | ---: |
| pp128 | 103.0913 | 113.3768 | **1.0998x** |
| pp512 | 89.1482 | 96.6658 | **1.0843x** |
| tg128 | 32.2609 | 32.5756 | 1.0098x |

The N2 correctness, sample-count, pp128, pp512 and decode-regression gates all
passed in [GitHub run 31165274205](https://github.com/Arshgill01/Arm/actions/runs/31165274205).
Its raw samples are committed under
[`results/raw/e23-31165274205`](../raw/e23-31165274205/) and bound by the
[manifest](../manifests/e23-31165274205.json).

## Live demonstration

The [demo script](../../scripts/demo_arm_q4_k_kernel.sh) runs the same model,
446-token prompt, deterministic seed and executable while switching only the
CPU library. On Axion it printed identical text and measured:

| Metric | Baseline | Candidate | Ratio |
| --- | ---: | ---: | ---: |
| Prompt throughput | 54.12 tok/s | 58.29 tok/s | 1.0771x |
| Whole command elapsed | 11.19 s | 10.56 s | 1.0597x |
| Decode throughput | 23.06 tok/s | 22.98 tok/s | 0.9965x |

This single live run demonstrates visible request latency; the balanced
multi-process tables above remain the performance evidence.

## Retained negatives and causal narrowing

| Candidate | pp128 | pp512 | tg128 / decision |
| --- | ---: | ---: | --- |
| SVE/NEON split only | 1.0295x | 1.0221x | 0.9926x; retained negative |
| row-pair helper | 0.8860x | 0.9128x | 1.0025x; rejected |
| GCC column-pair no-unroll only | 1.0660x | 1.0481x | below material gate alone |
| GCC unroll factor 2 | approximately neutral to factor 1 | — | rejected |
| shared decoder cleanup | 1.1016x | 1.0700x | 0.9744x decode; rejected |

The shared-decoder cleanup looked attractive in prefill but changed GEMV
code generation and caused a 2.6% decode regression. The final patch deliberately
duplicates the small vector-return helper so existing GEMV/Q5_K callers retain
their old implementation. The earlier split-only negative is documented in
the [E23a/E23b report](e23ab-arm-q4-k-kernel-profile-and-split-negative.md).

## Reproduction and evidence

Minimal clean reproduction on a four-core AArch64 host:

```sh
MODEL_PATH=/absolute/path/to/q4_k_model.gguf \
  ./experiments/e23_arm_kernel_ab.sh /tmp/e23-evidence
./experiments/e23_ingest.py \
  /tmp/e23-evidence /tmp/e23-evidence/summary.json
```

The runner clones exact b10216, builds one executable, captures the baseline
library, applies the retained patch, rebuilds only `ggml-cpu`, runs correctness
before performance, and records the full environment and hashes. The frozen
settings are in the [E23 contract](../../experiments/e23_contract.json).

Axion compact evidence is under
[`results/raw/e23c-axion-20260807`](../raw/e23c-axion-20260807/) and bound by
the [Axion manifest](../manifests/e23c-axion-20260807.json). The verified full
bundle is `/var/tmp/e23c-final-evidence-20260807-v2.tar.gz`, 4,069,957 bytes,
SHA-256 `e0e10e79636ada6eb0c8a903e161c939ae913f6a43118b6291974cafb415dcae`,
with 288 checked manifest entries. Earlier profiling and failed-harness bundles
remain at `/var/tmp/e23a-evidence-20260807.tar.gz` and
`/var/tmp/e23a-failure-version-probe.tar.gz` with hashes recorded in the
E23a/E23b report.

The paid `arm-kernel-e23c-20260807` instance ran for approximately 1.1 hours,
well within the pass's USD 40 ceiling. The exact instance and named boot disk
were deleted; final lookups were empty.

## Broadening plan

1. Profile and transplant vector scale reuse into Q5_K and Q6_K only where
   measured shares justify it; candidate pp128 still spends 11.44% in Q6_K.
2. Add a Clang-specific or structural compact-loop treatment only after a
   Clang A/B. The current no-unroll directive is intentionally GCC-only.
3. Run an unchanged-path guard on a true 32-byte-SVE machine. This pass proves
   NEON/I8MM behavior on 16-byte-SVE V2 and N2, not a speed claim for SVE256.
4. Consider tiled FFN fusion only after the small Q4/Q5/Q6 kernel lanes are
   exhausted; do not repeat the prior 1.0026x activation-pack reuse result.
