# E24b Arm Q6_K decode first-result checkpoint

Status: narrow result retained; mandatory user checkpoint before breadth and
upstream work.

## Result

On one `c4a-highcpu-8` Google Axion Neoverse V2 VM, the candidate increased
Ministral 3B Q4_K_M `tg128` from a median `24.872925` to `25.9593425`
tokens/second, a `1.0436787x` ratio (`+4.37%`). The matched run used six
processes per variant, three internal repetitions per process, four pinned
cores, and reverse-balanced `baseline,candidate,candidate,baseline` ordering.

This is below the pass's visible double-digit target and the approximately 20%
desired result. At the measured medians it removes about `1.683` milliseconds
per generated token, or `215` milliseconds by token 128. It is a first-machine
narrow result, not yet a general claim.

## Mechanism

The retained AArch64 change is in `ggml_gemv_q6_K_8x8_q8_K`:

1. `0016-arm-q6-k-gemv-fused-scales.patch` removes the 256-byte widened-scale
   scratch array, consumes each scale row once for both bias and
   dequantization, and keeps eight column accumulators in two NEON vectors.
2. `0020-arm-q6-k-gemv-just-in-time-loads.patch` loads each Q6 column pair at
   its point of use instead of making sixteen unpack vectors live at once.

The final patch deliberately retains the baseline split-lane floating-point
multiply/add sequence. A first version contracted that step and changed model
output despite passing the NMSE threshold; it was rejected before timing was
admitted.

## Direct evidence and correctness

| Shape | E23 baseline | Candidate | Ratio |
| --- | ---: | ---: | ---: |
| `n=3072, nc=2304` | 412.785 us | 339.252 us | 1.216750x |
| `n=9216, nc=768` | 413.223 us | 339.844 us | 1.215920x |

Each value is the median of 11 process medians, with 31 timed calls per
process. All 12 generic-reference cases passed; worst candidate NMSE was
`3.66714270791e-13`. Final candidate and baseline direct checksums are exact.
The 128-token live outputs are byte-identical with SHA-256
`ce8f5083c626b4d3ddc532144cae09206238a8767d048efab233b2f5be0d321b`.

The candidate native profile attributes `31.00%` of exclusive cycle samples
to `ggml_gemv_q6_K_8x8_q8_K`. Complete per-variant binary trees and loader
traces prove that the baseline and candidate processes loaded different CPU
backend hashes from their own binary directories. A preliminary
`LD_LIBRARY_PATH`-only run was excluded after the loader trace showed that it
was not a sufficient backend boundary.

## Closed Q4_K and Q6_K variants

- The corrected Q4_K I8MM formulation was 3.3–6.7% slower across four direct
  shapes. Its earlier interleaved-RHS form also failed native correctness.
- Forced Q4_K subblock unrolling reached only `1.0385–1.0417x` direct and
  missed the predeclared Q4 gate.
- The first fused Q6_K schedule reached about `1.081x` direct. Forced subblock
  and compact/paired column-loop schedules regressed. Point-of-use loads were
  the change that cleared the Q6 direct gate.

## Evidence

Compact evidence is under
[`results/raw/e24b-axion-20260807`](../raw/e24b-axion-20260807/). The verified
full checkpoint archive is `/var/tmp/e24b-evidence-checkpoint-v2.tar.gz`,
SHA-256 `0de9c8fa636c3b355ab8c653eb32ec935d0436e3c8ba91c56ea973505938670e`.
All files in the extracted archive passed its rebased SHA-256 inventory.

The paid VM remains active only because the pass requires adjacent-model and
second-machine work after user review. It must be deleted and exact instance
and disk absence verified before final closure.

## Checkpoint decision

The evidence supports continuing to adjacent Q4_K models, an independent Arm
machine, the cumulative stock-versus-combined comparison, current-upstream
porting, and the streamed side-by-side demo. It does not support calling the
current `4.37%` generation gain a double-digit result.
