# E23a/E23b Arm Q4_K profile and SVE/NEON split negative

E23a profiled the exact llama.cpp b10216 Q4_K_M inference path on Google
Axion. E23b then separated the 256-bit SVE implementation from the NEON/I8MM
Q4_K × q8_K function so the 128-bit-SVE host would not compile both kernels
into one public function. The change is correct and demonstrably executed, but
it is not a performance win: prefill improved by 2–3% and decode regressed by
0.7%. It does not clear the frozen 1.10x direct or 1.05x projected end-to-end
gates and must not be promoted or upstreamed.

## Frozen workload and host

- llama.cpp b10216 commit `876a4321163249c43ca4e986818fab5ab081f282`
- Ministral-3-3B-Instruct-2512 Q4_K_M, model SHA-256
  `fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4`
- one Google Axion `c4a-highcpu-8` VM in `us-central1-a`
- four threads pinned to cores `0-3`; CPU-only; flash attention on
- GCC 13.3, `-O3 -DNDEBUG -g -fno-omit-frame-pointer`, native Arm feature
  detection, KleidiAI enabled and LTO disabled in both GGML builds
- runtime SVE vector length: 16 bytes, so Q4_K dispatch selected NEON/I8MM

The [E23a contract](../../experiments/e23a_contract.json) freezes the detailed
source, build, model, host, PMU and benchmark settings.

## Hot path and source dispatch

| One-repetition sampled case | Q4_K × q8_K GEMM | q8_K 4×8 activation pack | Flash attention | IPC | L1D refill/access |
| --- | ---: | ---: | ---: | ---: | ---: |
| pp128 | 53.55% | 2.45% | 14.04% | 4.29 | 0.641% |
| pp512 | 46.38% | 2.20% | 36.52% | 4.46 | 0.453% |

The baseline profiler attributed the GEMM body to local ELF label
`.SVLPEND0`; disassembly resolves that label inside
`ggml_gemm_q4_K_8x8_q8_K`. Candidate sampling names the public function
directly at 50.79% of pp128 CPU-cycle samples. The q8_K packer is only about
2–3%, confirming the opportunity audit's rejection of a packer-only headline.
Aggregate L1D refill rates are below 0.7%, while annotated hot instructions
include nibble shifts, I8MM `smmla`, scale decoding and stack traffic. This
selects the existing Q4_K NEON/I8MM compute body, not the generic packer, as
the next optimization lane.

The sampled runs use `--no-warmup`, so the flat profile also contains model
loading and one-time weight repacking. In pp128,
`repack_q4_K_to_q4_K_8_bl` accounts for 2.80%; it is not conflated with the
steady-state kernel.

## E23b mechanism and execution proof

The retained [source patch](../../patches/llama.cpp/b10216/0011-arm-q4-k-split-sve-neon-kernels.patch)
moves the SVE body to a non-inlined helper and leaves runtime dispatch in the
public function. On the measured 16-byte SVE host, the public NEON function
shrinks from `0x142c` (5,164) to `0x0af0` (2,800) bytes. Its stack frame becomes
fixed rather than vector-length-dependent; at the measured vector length the
frame decreases from about 1,104 to 928 bytes.

Candidate `perf record` proves real inference executed
`ggml_gemm_q4_K_8x8_q8_K` for 50.79% of pp128 cycle samples. The baseline and
candidate shared libraries have distinct retained hashes, and their symbol
sizes are preserved under `results/raw/e23ab-axion-20260807/proof/`.

## Correctness

A bounded greedy CLI generation used the same model, prompt, seed, context,
thread count and candidate executable, switching only the baseline versus
candidate `libggml-cpu.so`. The extracted response bytes match exactly:

`dacdcbd09e5fb333f0359e7f457ea7b59fccdd5277acda7b11195ec7ebf3f66d`

This is a deterministic output-equivalence check for the exercised path, not a
broad quality claim.

## End-to-end screening result

Each case ran in reverse-balanced `baseline, candidate, candidate, baseline`
process order. Every process recorded three llama-bench samples, giving six
samples per implementation and case.

| Case | Baseline tok/s | Candidate tok/s | Candidate ratio | Decision |
| --- | ---: | ---: | ---: | --- |
| pp128 | 69.7128 | 71.7709 | 1.029522x | fail gate |
| pp512 | 51.7256 | 52.8670 | 1.022067x | fail gate |
| tg128 | 24.3165 | 24.1353 | 0.992550x | regression |

Candidate prefill samples also show more run-order drift than baseline (pooled
CV 1.09% at pp128 and 0.78% at pp512), so the small positive ratios should not
be overinterpreted. The decode regression independently rejects promotion.

The two GGML libraries use the same compiler, Arm flags, KleidiAI and LTO
settings, but the manually configured candidate tree omitted the baseline
tree's unrelated examples/server options. The correctness run eliminated this
confound by switching only `libggml-cpu.so` under one executable; the throughput
screen did not. Therefore these throughput ratios are sufficient only to reject
this already-small candidate. A result near or above a promotion gate would
have required a fresh exact-build A/B before any claim.

## Failed and excluded work

The first harness attempt stopped after a successful build because b10216
`llama-bench` does not implement `--version`. The corrected harness captures
`--help`; the 68,613-byte failed-run bundle is retained in the manifest.

The first pp4096 profile overlapped candidate compilation. It was terminated
and excluded from all tables and claims. A first CLI correctness probe used a
context shorter than the model-generated prompt and entered the revision's
interactive retry loop. That probe was stopped; 7.9 GB of meaningless repeated
temporary stdout was removed, while the stderr diagnosis was retained. The
bounded 1,024-token, single-turn replacement is the correctness result above.

## Evidence and decision

The [manifest](../manifests/e23ab-axion-20260807.json) binds the exact source,
model, host, candidate patch, compact committed evidence and full raw bundle.
The full bundle is 5,898,594 bytes with SHA-256
`15fceb80b02bf4021d87e1f07b67b1f8b84aa8a4c7cd3c2adeddb144622437c0`.
Binary PMU samples stay outside Git; compact controls, counters, reports,
reverse-balanced cells, hashes and correctness responses are committed under
[`results/raw/e23ab-axion-20260807`](../raw/e23ab-axion-20260807/).

The paid instance and its auto-delete boot disk were deleted after evidence
capture, and the final exact-name instance lookup was empty. This mechanism is
closed as a standalone optimization. The next experiment should change the
measured NEON/I8MM inner tile itself—reducing its persistent stack spills and
register pressure—rather than polishing dispatch separation or returning to
the low-ceiling q8_K packer.
