# E16d/E16e: persistent Arm-packed sidecar product lifecycle

## Decision

**Promote the exact identity-bound sidecar lifecycle through E16e. Retain E16d
as a failed workflow.** The native E16d product commands completed successfully,
but its frozen final reader attempted to decode raw llama.cpp tokenizer
diagnostics as UTF-8 and raised `UnicodeDecodeError` before evaluating any gate.
E16e changed only that reader boundary: it searched the same two ASCII mechanism
markers in the original log bytes, changed no acceptance gate, mutated no source
artifact, and added no measurement.

- Failed native lifecycle: [E16d run `30988414887`](https://github.com/Arshgill01/Arm/actions/runs/30988414887), job `92248513907`, commit `9baf8b53b8ac704a509ff9abb68805ebbf6b34dd`.
- Successful native retention repair: [E16e run `30989161576`](https://github.com/Arshgill01/Arm/actions/runs/30989161576), job `92250913881`, commit `144b22e584b9f325ad03721fde900c074a83c343`.
- Compact evidence: [`e16e-30989161576.json`](../manifests/e16e-30989161576.json).
- Frozen repair contract: [`e16e_lifecycle_contract.json`](../../experiments/e16e_lifecycle_contract.json), SHA-256 `f7034e7c56d5ef45e7c24f60af06bbeb781932f69c8d02746d970247e807a22e`.

## What the clean-checkout lifecycle actually did

On `ubuntu-24.04-arm`, the exact retained E16c OpenSSL-off runtime and selected
Ministral 3B Q4_K_M bytes ran through the public Pareto64 CLI:

1. `sidecar-prepack` constructed the complete 183-tensor Arm-packed arena,
   serialized it into a read-only identity-bound sidecar, fully verified every
   tensor, recorded a receipt, and deleted the 183 raw tensor dumps.
2. `sidecar-verify` independently rechecked the entire sidecar and its index.
3. A deliberately corrupted index was rejected while the original sidecar and
   index hashes remained unchanged.
4. `sidecar-launch --workers 2` performed a full verification for each worker,
   mapped the same sidecar inode `r--s` at the frozen 1 MiB data offset, skipped
   runtime repacking, and served the complete 30-task workload on both workers.
5. A controlled stop terminated both workers cleanly. `sidecar-cleanup` first
   produced a dry-run plan, then removed only the receipt-bound sidecar and
   index while retaining the read-only receipt.

All 14 unchanged lifecycle gates pass in two byte-identical workflow replays and
two further local replays. Both workers reproduce 23/30, all 60 measured
requests succeed, neither worker differs from the retained reference map, and
the two workers' exact answers do not differ.

## Construction and storage evidence

These values describe the single E16d construction on a native Neoverse N2
runner. They are not a new performance comparison.

| Item | Retained value |
| --- | ---: |
| Server start to construction readiness | 3.06046 s |
| Construction server process | 3.27463 s |
| Sidecar serialization | 5.68884 s |
| Independent full verification | 2.37504 s |
| Total prepack lifecycle | 12.60244 s |
| Raw Arm-repacked tensor bytes | 2,137,964,544 |
| Read-only sidecar bytes | 2,139,013,120 |
| Index bytes | 81,926 |
| Raw-plus-sidecar construction peak | 4,276,977,664 bytes |
| Raw dumps deleted | 183 / 2,137,964,544 bytes |

Using the already retained E16b same-job warm-readiness medians—2.53023 seconds
for normal repacking and 0.96075 seconds for the sidecar—the recorded prepack
cost corresponds to an estimated break-even after nine warm worker starts. That
is only a warm, matched-host estimate. It excludes the model download, cold
storage and page-cache state, request work, energy, money, maintenance, and
fleet behavior.

## The failed run remains evidence

E16d's always-uploaded artifact is 13,968,867 compressed bytes with digest
`sha256:9324b4dabdccd47fdb2094ec309de9f9ef79f6f5c688aab7a1166f25d9b8d51d`.
E16e verified all 61 extracted files and 33,762,667 bytes; its canonical source
inventory hash is `b55833c162f77859550dd0f82b26e483866e412aeef78c3b6c6a335ff4d66a4b`.
Both worker logs contain non-UTF-8 tokenizer bytes and the exact frozen ASCII
sidecar markers. That is why the original strict decoder failed and the bounded
byte reader succeeds.

The successful E16e artifact is 13,997,803 compressed bytes with digest
`sha256:7dc461cacd549a10e3fbd6777758ff7bada630dc9d58aadf1a6507c63ccf686e`.
All 67 extracted files and 33,885,227 bytes were independently inventoried; the
workflow and local summaries are byte-identical at SHA-256
`7d9aa3af0ce2b674bd4386a8e7760a5cde633d0b5a096dd9214c2013ad64bc57`.

## Claim boundary

E16e establishes that the exact E7c/Q4_K_M identity can be prepacked, fully
verified, corruption-checked, launched as two workers on one read-only shared
sidecar, quality-checked, stopped, and safely cleaned up from a clean Pareto64
checkout. E16b remains the source of the 62.03% same-job warm-readiness result;
E16c remains the source of the 2,091,714 KiB summed-PSS saving and 1.00044x
aggregate-throughput result.

E16d/E16e do **not** establish cold-start improvement, per-process RSS
reduction, a new throughput result, energy or PMU behavior, Mac behavior,
portability to another CPU/model/runtime, fleet economics, or monetary cost.
