# E25a cumulative E24 Q4_K baseline profile

Status: native Arm profiling checkpoint complete; no E25 speedup is claimed by
this checkpoint.

The cumulative E24 baseline was rebuilt from llama.cpp b10216 commit
`876a4321163249c43ca4e986818fab5ab081f282` with the retained E23 Q4_K patch
and both accepted E24 Q6_K patches.  The primary Ministral Q4_K_M model matched
SHA-256 `fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4`.
All runs used four threads pinned to Axion cores 0--3, CPU-only execution,
Flash Attention, no warmup, and the unchanged output policy.

## Bound hot path

The unsampled `tg128` control reached 25.6045 tok/s.  Exclusive cycle samples
from the same cumulative baseline were:

| Function | `tg128` | Live request |
| --- | ---: | ---: |
| `ggml_gemv_q4_K_8x8_q8_K` | 57.35% | 49.56% |
| `ggml_gemv_q6_K_8x8_q8_K` | 30.46% | 26.36% |
| `ggml_compute_forward_flash_attn_ext` | 0.79% | 1.06% |
| q8_K activation quantization | 0.27% | 0.51% |

The deterministic live request processed its 43-token prompt at 84.18 tok/s
and its following 127 decode steps at 25.50 tok/s.  Both profiles recorded the
named Q4_K and Q6_K AArch64 functions, proving real dispatch rather than an
inferred model-format match.

## Instruction and memory evidence

The `tg128` stat run retired 718,639,081,818 instructions in 184,693,716,790
cycles (3.891 IPC).  It recorded 134,424,922,628 L1D accesses,
2,462,907,926 refills (1.832%), and 27,154,568,237 L2D accesses.  The live
request measured 3.921 IPC and a 1.730% L1D refill/access ratio.  These are
whole-process counters and are not presented as kernel-local cache misses.

Static disassembly of the selected Q4_K body contains 32 `sdot`, 22 `and`, 16
`ushr`, 24 `ldp`, 22 `stp`, and 58 `mov` instructions.  Cycle annotation also
places material samples in the packed scale/min reconstruction.  That evidence
supports moving scale/min preparation and the duplicated q8 broadcast schedule
out of token generation, rather than another instruction-order-only rewrite.

The real dispatch source maps Arm I8MM Q4_K to the 8x8 layout.  The direct
model shapes remain 3072x2304 and 9216x768 before four-core row chunking; E25's
packed-format harness uses those exact full matrices.

## Current-source audit and evidence

Current upstream at capture time was
`69bf6437914596fbbc4caf09a7ac16f2acdd1a94`.  The E25 patch will be checked
separately against that commit after the pinned result is complete.

Compact raw controls, counters, symbol shares, dispatch lines, host identity,
tool versions, and hashes are under
[`results/raw/e25a-axion-20260808`](../raw/e25a-axion-20260808/).  Binary
`perf.data` stays on the bounded experiment host and is not committed.
