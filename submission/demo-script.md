# Public demo script — 2 minutes 45 seconds

Record at 1440×900 or 1920×1080. Show the browser and terminal at readable zoom.
Use no copyrighted music or third-party footage.

## 0:00–0:18 — The hook

**Screen:** Open the Pareto64 demo at the top.

**Voice:** “The fastest model lost. On native Arm, our KleidiAI model was 29%
faster and slightly smaller—but it failed the workload. Pareto64 selected the
only package that cleared quality and every deployment SLO.”

## 0:18–0:40 — The quality frontier

**Screen:** Point to the 70% Q4_0 marker, the fixed 75% line, and the selected
76.67% Q4_K_M marker. Keep all four selected metrics visible.

**Voice:** “Every experiment is pinned and repeated. The planner locks quality
first, then evaluates latency, memory, load time, and size. There is no weighted
score to hide a bad tradeoff.”

## 0:40–1:00 — Interactive refusal

**Screen:** Navigate to “Decision lab.” Click “Latency temptation.” Show
`No feasible candidate`, then return to “Quality deployment.”

**Voice:** “Lowering a policy after measurement cannot rescue the faster model:
its experiment gate already failed. Tighten latency and the selected model fails
too, so Pareto64 refuses deployment instead of moving the goalposts.”

## 1:00–1:42 — Serving optimization

**Screen:** Scroll to “Reuse 25 tokens. Keep all 120 answers.” Point to the
throughput bars, concurrency boundary, context/KV profile, and prompt-batch
profile.

**Voice:** “More server slots gained only 1.9%, so we rejected them. Shared-prefix
caching preserved all 120 answers, raised throughput 1.67 times, and cut median
latency 41%. Combining cache and concurrency nearly doubled latency, so one slot
stayed. Right-sizing context saved 183 MiB; q4 KV saved more but changed an
answer. Batch 64 cut the compute buffer 75%. Disabling Arm weight repacking
saved another 1.98 GiB but halved throughput, so the planner exposes separate
fast and under-three-GiB tiers—and refuses an envelope neither tier measured.”

## 1:42–2:08 — Arm-specific patch

**Screen:** Scroll to the before/after assembly section.

**Voice:** “In llama.cpp’s Q8 activation quantizer, we replaced 32 scalar stores
with six NEON narrows and two vector stores. Direct throughput doubled from 5.1
to 10.3 gigabytes per second with bit-identical output. The full Arm CPU lane
then passed 47 tests. Real-model inference stayed neutral, so we claim the hot
path—not a whole-model speedup.”

## 2:08–2:36 — Exact serving and final boundaries

**Screen:** Show the E5b through E9e rows and final comparison, then the terminal.

```bash
python3 scripts/verify_submission.py
```

**Voice:** “The hash-verifying adapter reproduced all 30 task outputs with zero
drift. OpenSSL-off removed two unused library edges and retained 99.981% of
throughput. Then one same-job comparison ran the exact earliest and final
recipes four times each. All 240 answers matched: final throughput was 1.717
times, median latency fell 41.5%, and CPU work per request fell 41.9%. This is a
compounded product result; isolated experiments provide attribution. The
external holdout stopped before task results when the exact API lacked required
logprobs. Alternating prefixes changed answers, strict sanitizer readiness
failed on an inherited test, and speculative/cross-runtime gates failed before
measurement. We publish those boundaries too.”

## 2:36–2:45 — Close

**Screen:** Run the service planner command, show `repack_off` and
`--no-weight-repack`, then end on the top of the demo.

```bash
python3 -m pareto64 service-plan \
  --manifest results/manifests/e5h-30672633366.json \
  --constraints configs/service-memory.json
```

**Voice:** “Pareto64 turns Arm optimization from a leaderboard into a sequence
of provable obligations: measure, reject, select, verify, and launch. Every win,
near-miss, patch, and raw run is retained and ready for review.”
