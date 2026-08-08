# E28 cumulative Arm runtime result

Status: current-upstream release and second-Arm portability lanes accepted;
pinned b10216 matrix retained as negative composition evidence.

## Decision

Retain one current-upstream runtime containing E24 Q6_K GEMV, E25 decoded
Q4_K metadata and E27's SVE-build NEON Flash Attention GEMM. On four Google
Axion cores and the frozen Ministral 3B Q4_K_M model, the directly measured
combined runtime changes `pp2048` from `25.185344` to `66.845524` tokens/second
(`2.654144x`) and `tg128` from `24.681688` to `28.535503` tokens/second
(`1.156141x`). These are matched stock-versus-combined measurements; no ratio
is inferred by multiplying earlier experiments.

The claim is bounded to source commit
`69bf6437914596fbbc4caf09a7ac16f2acdd1a94`, the recorded build and runtime
policy, the tested CPUs and the two pinned model files. The b10216 matrix is
composition evidence, not the release claim. E26 remains a negative result and
is absent from the runtime.

## Current-upstream integration

The ordered series is retained under `patches/llama.cpp/e28/current/` and
promoted byte-for-byte under `patches/llama.cpp/current/`. Both manifests pin
the upstream commit, application order and SHA-256 of each patch:

1. E24 Q6_K GEMV, SHA-256 `f1bab985...a451`.
2. E25 decoded Q4_K metadata, SHA-256 `09b7daee...9812`.
3. E27 Flash Attention NEON GEMM, SHA-256 `5f7c5896...97a4`.

The historical E23 patch is not upstream, but it changes the Q4_K 8x8 kernel.
Current llama.cpp dispatches aligned two-dimensional Q4_K tensors through its
8x4 path, which E25 replaces, so E23 is omitted as superseded. A real-model
prefill GDB trace records the current 8x4 dispatch rather than relying on source
or symbol inspection alone.

E25 initially integrated with b10216's Q8_K 4x8 packed layout. Current
upstream's Q4 8x4 GEMM consumes Q8_K 4x4; the mismatch produced direct NMSE as
high as about `2.9`. Before timing, the current patch and harness were repaired
to use the 4x4 layout. The accepted direct maximum NMSE is
`8.122988e-13`. The exact retained series applies cleanly in order to a fresh
worktree at the pinned current commit.

## Current correctness and quality

Nine Flash Attention comparisons cover q512 with kv512, kv2048 and kv4096 at
seeds 1, 17 and 42. All pass the frozen `5e-4` limit; maximum NMSE is
`8.490283e-5`. Native dispatch evidence separately covers E24 Q6_K, E25
decoded Q4_K, E27 NEON `fmla`, and the E23-superseding prefill route.

The 30-task deterministic suite scores `19/30` for stock and combined in both
repetitions, with stable predictions. The valid 17,020-byte perplexity corpus
has SHA-256 `874eb47b...9ae`; stock is `1.8956` twice and combined is `1.8969`
twice. The ratio is `1.000686`, below the frozen `1.001` ceiling.

E25's decoded sidecar selects 156 tensors and adds `163,577,856` bytes for
`1,472,200,704` packed Q4_K bytes, exactly `11.11%`. Median whole-process RSS
increases by about 156 MiB, consistent with that allocation rather than an
unbounded cache.

## Current matched performance

Each cell is the median of six fresh processes. Every process contributes one
timed `llama-bench` sample; the process is the statistical unit. Execution is
reverse-balanced over three rounds, pinned to cores 0-3 with four threads,
identical model bytes, Flash Attention, F16 K/V, batch/ubatch and no-warmup
policy. Confidence intervals are 10,000-resample percentile bootstraps of the
process medians with seed 280028.

| Case | Stock | Combined | Combined / stock | 95% CI | Stock CV | Combined CV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `pp2048` | 25.185344 tok/s | 66.845524 tok/s | **2.654144x** | 2.644436-2.658749 | 0.195% | 0.064% |
| `tg128` | 24.681688 tok/s | 28.535503 tok/s | **1.156141x** | 1.148769-1.163160 | 0.505% | 0.206% |

Median maximum RSS is 4,521,656 versus 4,681,326 KiB at `pp2048`, and
4,257,912 versus 4,417,656 KiB at `tg128`. Median server readiness is
2,367.18 ms stock versus 2,112.59 ms combined.

## Current profile and next ceiling

STANDARD hardware PMU access was required before admission. The combined
`pp2048` profile assigns `63.97%` to `ggml_gemm_q4_K_8x4_q8_K`, `15.34%` to
the tiled Flash Attention function and `10.68%` to Q6_K GEMM. Eliminating the
ranked Q4_K GEMM entirely would bound speedup at about `2.78x` by Amdahl's law.

The combined `tg128` profile assigns `49.99%` to decoded Q4_K GEMV and `32.35%`
to Q6_K GEMV, bounding elimination of the first kernel at about `2.00x`.
E28 therefore ranks Q4_K GEMM for prefill and decoded Q4_K GEMV for decode;
it does not start another optimization.

Raw `perf stat` retains CPU cycles, retired instructions, L1D accesses and
refills, and L2D accesses for both cases. Symbol-ranked reports are in the
compact evidence; `perf.data` stays only in the checksum-verified full archive.

## Live 8K-context demo

The reusable current stock-versus-combined command runs one generated token
with seed 42, temperature zero, four pinned cores and complete command capture:

```bash
scripts/e28_demo_cumulative_arm.sh \
  /path/to/stock/bin /path/to/combined/bin \
  /path/to/model.gguf /path/to/prompt.txt /var/tmp/e28-demo
```

The measured prompt contains 7,493 tokens in an 8,192-token context. Stock
prompt evaluation is `849,171.06` ms and combined is `168,921.76` ms, a
direct `5.027008x` time reduction. Both one-token outputs have SHA-256
`5b043522...a4`; the retained diff is empty. Wall times are 14:11.77 and
2:51.30.

## Pinned b10216 2x2 composition

Each entry below is the median of six fresh processes per variant. The D/A
interval is a 10,000-resample percentile bootstrap of the process medians.

| Case | A | B | C | D | D / A (95% CI) | B / A | C / A | D / B | D / C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `pp512` | 55.720083 | 54.965116 | 90.084454 | 88.247382 | **1.583763x** (1.582925-1.588068) | 0.986451x | 1.616732x | 1.605516x | **0.979607x fail** |
| `pp2048` | 26.186141 | 25.973477 | 75.848289 | 74.582010 | **2.848148x** (2.843503-2.850696) | 0.991879x | 2.896505x | 2.871468x | 0.983305x |
| `pp4096` | 15.349590 | 15.223622 | 62.582982 | 61.695727 | **4.019373x** (4.014546-4.025684) | 0.991793x | 4.077176x | 4.052631x | 0.985823x |
| `tg128` | 25.333160 | 27.909959 | 25.272732 | 27.791710 | **1.097049x** (1.089515-1.103620) | 1.101716x | 0.997615x | 0.995763x | **1.099672x fail** |

Population CV across the sixteen timing cells ranges from 0.019% to 0.414%.
Median maximum RSS for A versus D is 4,360,528/4,520,166 KiB at `pp512`,
4,521,704/4,681,538 KiB at `pp2048`, 4,736,882/4,896,648 KiB at `pp4096`,
and 4,257,976/4,417,720 KiB at `tg128`. Median server readiness for A/B/C/D
is 2,409.41/2,209.01/2,410.82/2,209.07 ms. The sidecar remains 163,577,856
bytes over 1,472,200,704 packed Q4_K bytes (`11.11%`).

The pinned matrix is a retained negative composition result rather than a
fully accepted gate set. At `pp512`, D/C is `0.979607x` against the frozen
`0.98` floor (95% CI 0.979270-0.980117). At `tg128`, D/C is `1.099672x`
against `1.10` (95% CI 1.092006-1.105186). Neither is rounded into a pass.
E27's prefill effect itself remains present at every size: C/A and D/B clear
their respective 1.50, 2.70 and 3.75 gates. The failure rule for an E25 quality
loss or destruction of E27's effect therefore does not select the E27-only
fallback; the current-upstream combined runtime has its own accepted matched
release measurements and quality gate.

All A/B/C/D semantic outputs for the 7,493-token request have SHA-256
`7e6c8b6d...ea78`; A/C and B/D diffs are empty. A, B, C and D each score
`19/30` in both quality repetitions with stable predictions. All eight valid
PPL measurements are `1.8956`, so B/A and D/C are both `1.0`.

The pinned four-way live demo also uses 7,493 prompt tokens, one generated
token, seed 42, temperature zero and the same four pinned cores. Prompt
evaluation is 839,491.22/840,161.75/156,081.86/157,804.13 ms for A/B/C/D;
wall time is 14:02.25/14:02.68/2:38.82/2:40.33. Thus A/C is `5.378532x` and
B/D is `5.324080x` by prompt-evaluation time. All four generated outputs have
SHA-256 `5b043522...a4`; the required A/C and B/D comparisons are byte
identical.

## Second Arm generation and adjacent model

GitHub Actions run `31261118570` uses a four-core hosted Neoverse N2 machine
and Qwen2.5 1.5B Q4_K_M, SHA-256 `6a1a2eb6...07e`, rather than substituting it
for the primary model. Direct Q4/Q6/Flash correctness passes with maximum
direct NMSE `8.122988e-13` and maximum Flash NMSE `8.490283e-5`.

| Case | Stock | Combined | Combined / stock | 95% CI |
| --- | ---: | ---: | ---: | ---: |
| `pp512` | 89.072046 tok/s | 109.851068 tok/s | **1.233283x** | 1.230172-1.237852 |
| `pp2048` | 50.923432 tok/s | 97.408594 tok/s | **1.912844x** | 1.910190-1.914178 |
| `pp4096` | 32.683629 tok/s | 84.636890 tok/s | **2.589581x** | 2.586635-2.591009 |
| `tg128` | 32.537311 tok/s | 40.309814 tok/s | **1.238880x** | 1.232924-1.248166 |

Each entry again uses six fresh processes per variant. The Qwen sidecar is
84,086,784 bytes for 756,781,056 packed Q4_K bytes (`11.11%`). This run is a
portability result on a different Arm generation and model, not a replacement
for the Axion/Ministral claim.

## Contract revisions and rejected attempts

The experiment contract was frozen before timing, then amended twice before
any accepted timing began. Revision 2 removes three duplicated internal
repetitions while retaining six fresh processes per cell; the process remains
the statistical unit. Revision 3 replaces the too-short 2,896-token PPL input
with two byte-identical copies of the frozen source file. The rejected
short-corpus outputs are retained separately.

The first current and pinned instances lacked STANDARD PMU configuration. No
timing from either was accepted. Their checksum-verified archives are:

- `current-no-pmu-20260808.tar.gz`, SHA-256
  `0c36f3abbeaa1f58afec779480278d2075e19bbf3e146b613e584b0831363273`.
- `pinned-no-pmu-20260808.tar.gz`, SHA-256
  `a189a2e646a022a05b856b5ba327c1252dbb2cf66803f79db531444ec6ffd9b0`.

The accepted current benchmark also has a rejected outer-launcher status file:
shell expansion made its trap write a literal `1`. The campaign's own marker,
24 nonempty raw samples and accepted final ingester establish completion; the
launcher failure is retained rather than rewritten.

## Evidence and resource closure

Compact current evidence is under `results/raw/e28-current-axion-20260808`;
second-machine evidence is under `results/raw/e28-n2-31261118570`.
Compact pinned evidence is under `results/raw/e28-pinned-axion-20260808` with
a verified SHA-256 inventory. Its full archive, including three
`perf.data` files and the complete D disassembly, is at
`/home/arshdeepsingh/work/e28-evidence-archives/e28-pinned-axion-full-20260808.tar.gz`
with SHA-256
`60e422959c32424f6e66cad44fa97699c900988087798ad6e2b76bd2a57d260b`.

The full current archive, including PMU data and disassembly, is at
`/home/arshdeepsingh/work/e28-evidence-archives/e28-current-axion-full-20260808.tar.gz`
with SHA-256
`66e6d7962e688137330310fdb97e0af8c8cab9ecd856f0091f9ab3e902f9fc58`.

Four c4a-highcpu-8 instances existed across the two rejected and two accepted
attempts. Every instance had a six-hour `DELETE` ceiling and an auto-delete
boot disk. At the published `$0.03787` per-vCPU-hour starting rate, even the
unreached worst case of all four eight-vCPU instances lasting six hours is
about `$7.27` of compute, leaving disk cost and substantial headroom below the
frozen `$12` limit.

The current instance and exact-name boot disk were explicitly deleted after
archive verification; both retained post-delete inventories are empty.
The pinned instance was explicitly deleted after archive verification, about
3 hours 24 minutes after creation. Its auto-delete boot disk was already absent
when the exact-name disk deletion check ran. At 2026-08-08T17:03:55Z, both
exact-name instance and disk inventories were `[]`.
