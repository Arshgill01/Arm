# E24a decode hot-path and opportunity ranking

Status: checkpoint 1 complete; awaiting the required user review before a
decode source change.

E24a freezes the accepted E23 Q4_K prefill patch as the baseline and profiles
single-token generation on Google Axion. Both the synthetic `tg128` workload
and a deterministic real request select `ggml_gemv_q4_K_8x8_q8_K` first and
`ggml_gemv_q6_K_8x8_q8_K` second. Together they account for 89.29% of exclusive
cycle samples in `tg128` and 77.28% in the live request. No decode optimization
has been implemented or measured yet.

## Bound baseline

- llama.cpp b10216 commit `876a4321163249c43ca4e986818fab5ab081f282`;
- the exact three retained runtime patches plus E23's
  `0013-arm-q4-k-neon-vector-scale-kernel.patch`;
- Ministral 3B Q4_K_M, SHA-256
  `fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4`;
- one `c4a-highcpu-8` Google Axion Neoverse V2 instance with standard PMU;
- four threads pinned to cores 0--3, CPU-only, Flash Attention enabled; and
- GCC 13.3, native Arm feature detection, KleidiAI enabled, LTO disabled.

The unsampled baseline reached 24.6668 tok/s at `tg128`. The 43-token live
prompt processed at 83.98 tok/s and its following 127 decode steps ran at
24.66 tok/s. Those rates describe the baseline only and are not an A/B result.

## Exact dispatch and measured hot path

The 8x8 repack trait maps Q4_K, Q5_K and Q6_K weights with q8_K activations to
their corresponding public GEMV functions. Native profiles prove that the real
model executes the Q4_K and Q6_K AArch64 bodies. All reported shares are
exclusive CPU-cycle samples from `perf report --no-children`; both profiles
recorded zero lost samples.

| Function | `tg128` share | Live-request share | Interpretation |
| --- | ---: | ---: | --- |
| `ggml_gemv_q4_K_8x8_q8_K` | 55.78% | 48.16% | Primary decode source target. |
| `ggml_gemv_q6_K_8x8_q8_K` | 33.51% | 29.12% | Material second kernel, not an adjacent-model guess. |
| Q4_K/Q6_K GEMM | 0% | 6.24% | Live prompt processing only; E23 remains the prefill baseline. |
| Q5_K GEMV | 0% | 0% | Not executed by this model; no implementation lane. |
| q8_K activation packing | 0.27% | 0.50% | Too small for a visible decode result. |
| Flash Attention | 0.76% | 1.02% | Not a decode headline target. |

The PMU stat runs measured 3.918 retired instructions/cycle and a 1.417%
L1D-refill/access ratio for `tg128`; the live request measured 3.948 IPC and
1.424%. These whole-process counters do not prove a kernel-local cache cause.
The instruction annotations instead show the Q4_K body spending samples across
nibble masks/shifts, q8 broadcasts, scale widening and DOT-product work, while
the Q6_K body is dominated by its unpack/shift schedule. They motivate direct
kernel experiments but do not by themselves identify a speedup.

## Current-source audit

The current llama.cpp master observed before implementation was
`42e98813e4aba923453d84433c12cfdd29f07a47`. Its Arm `repack.cpp` has the same
SHA-256 as b10216, `2e7ba6aa...e4cce7`, so the Q4_K/Q6_K GEMV bodies and
dispatch gap are unchanged. Current KleidiAI commit
`b9693e1c56115bfa5c7e342b91b3cb07fd7224a1` contains no Q4_K or q8_K source
match; llama.cpp still documents KleidiAI kernels only for Q4_0 and Q8_0.

## Whole-model ceilings

These are Amdahl projections from measured exclusive share, not expected or
claimed results.

| Target | Perfect-kernel ceiling, `tg128` | Whole `tg128` if kernel is 1.10x | If kernel is 1.20x | Live if kernel is 1.20x |
| --- | ---: | ---: | ---: | ---: |
| Q4_K GEMV | 2.261x | 1.053x | 1.102x | 1.087x |
| Q6_K GEMV | 1.504x | 1.031x | 1.059x | 1.051x |

Q4_K alone needs approximately 1.426x direct speed to project to 1.20x
`tg128`. If both measured GEMV families improved by 1.20x, the `tg128`
projection would be 1.175x. The desired visible result therefore likely needs
either a larger Q4_K mechanism or successive Q4_K and Q6_K improvements; this
checkpoint does not assume either is achievable.

## Ranked opportunities

1. **Q4_K 8x8 GEMV inner tile.** Build a direct harness for the selected
   3072/9216 decode shapes, then test a dedicated I8MM-oriented two-column
   schedule that consumes the already interleaved 8x8 weights with less
   DOT-product reduction, scale materialization and register traffic. The
   existing function is selected on an I8MM CPU but its GEMV body uses the
   DotProd formulation. Kill an exact rewrite below 1.10x direct speed or
   below a 1.05x measured-share projection. Do not transplant E23's rejected
   shared scale decoder; it previously caused a 2.6% decode regression.
2. **Q6_K 8x8 GEMV unpack schedule.** The measured 33.51% share justifies a
   successor only after the Q4_K screen. Its annotation concentrates samples
   in nibble shift, vector load/move and unpack work. Test a direct harness
   before source integration and kill below 1.10x direct or 1.03x projected
   `tg128` speed.
3. **Deeper Q4_K/Q6_K decode dataflow.** Consider a packed-layout or cross-
   kernel dataflow change only if both narrow screens fail or their retained
   gains cannot reach a visible result. Activation packing, Q5_K and Flash
   Attention are explicitly closed by this profile rather than being promoted
   from microbenchmark potential.

## Evidence and closure

The compact text evidence is under
[`results/raw/e24a-axion-20260807`](../raw/e24a-axion-20260807/) and is bound by
the [manifest](../manifests/e24a-axion-20260807.json). The full verified bundle
is `/var/tmp/e24a-evidence-final.tar.gz`, 10,320,506 bytes, SHA-256
`a83abc523e3897af5ce447c0dd0b23290990f901479ad5bd1b14bf9aeeda80df`.
Its remote inventory and local extracted inventory both passed; binary
`perf.data` stays outside Git.

Three zero-result setup failures are retained with hashes in the manifest: an
invalid metadata field, a VM created without explicit standard PMU, and a
missing declared `ripgrep` dependency. The successful paid instance used a
six-hour automatic deletion cap and ran for about 13 minutes. It and its named
boot disk were explicitly deleted, and final exact-name lookups were empty.

## Checkpoint recommendation

Proceed with opportunity 1: direct correctness/timing harness first, then the
smallest Q4_K GEMV-only I8MM schedule supported by that harness. Return to the
user after the first matched end-to-end result, including a negative result.
