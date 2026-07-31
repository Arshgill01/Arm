# Public demo script — 2 minutes 50 seconds

Record at 1440×900 or 1920×1080. Show the browser and terminal at readable zoom.
Use no copyrighted music or third-party footage.

## 0:00–0:18 — The hook

**Screen:** Open the Pareto64 demo at the top.

**Voice:** “The fastest model lost. On native Arm, our KleidiAI model was 29%
faster and slightly smaller—but it failed the workload. Pareto64 selected the
only package that cleared quality and every deployment SLO.”

## 0:18–0:43 — The quality frontier

**Screen:** Point to the 70% Q4_0 marker, the fixed 75% line, and the selected
76.67% Q4_K_M marker. Keep all four selected metrics visible.

**Voice:** “Every experiment is checksum-pinned and repeated. The planner locks
experiment quality first, then evaluates latency, load time, memory, and size.
There is no weighted score to hide a bad tradeoff.”

## 0:43–1:08 — Interactive refusal

**Screen:** Navigate to “Decision lab.” Click “Latency temptation.” Show
`No feasible candidate`, then return to “Quality deployment.”

**Voice:** “Even if an operator lowers the policy after measurement, the faster
model stays rejected because its frozen experiment gate failed. Tightening the
latency SLO makes the selected model fail too, so Pareto64 refuses deployment
instead of moving the goalposts.”

## 1:08–1:43 — Serving optimization

**Screen:** Scroll to “Reuse 25 tokens. Keep all 120 answers.” Point to the
throughput bars, concurrency boundary, and context/KV profile.

**Voice:** “More server slots gained only 1.9%, so we rejected them. Shared
prefix caching was different: all 120 answers stayed identical, throughput rose
1.67 times, and median latency fell 41%. We then tested both together. Two
cached slots gained only 6.2% and nearly doubled latency, so one slot stayed the
default. Then we right-sized its context from 2,048 to 256 tokens: all answers
stayed exact, throughput stayed at 99.6%, and maximum RSS fell 183 MiB. q4 KV
saved more but changed an answer, so f16 stayed.”

## 1:43–2:08 — Arm-specific patch

**Screen:** Scroll to the before/after assembly section.

**Voice:** “Pareto64 also produced a bounded Arm source contribution. We
replaced 32 scalar byte stores in llama.cpp’s Q8 activation quantizer with six
NEON narrowing instructions and two vector stores. Direct throughput rose from
about 5.1 to 10.3 gigabytes per second. Outputs were bit-identical, upstream
tests passed, and real-model inference did not regress. We do not claim a
whole-model speedup.”

## 2:08–2:32 — Exact serving

**Screen:** Show the E5b through E5e rows, then the terminal.

```bash
python3 scripts/verify_submission.py
```

**Voice:** “The product launches through a hash-verifying adapter. The verifier
pins the model, runtime, selected plan, serving evidence, and Arm patch. Cache
mode is written into the recipe, and there is an explicit no-cache escape hatch
for workloads that have not passed the same correctness gate.”

## 2:32–2:50 — Close

**Screen:** Run the planner command, show `ministral3_3b_q4_k_m`, then end on the
top of the demo.

```bash
python3 -m pareto64 plan \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json
```

**Voice:** “Pareto64 turns Arm optimization from a leaderboard into a sequence
of provable obligations: measure, reject, select, verify, and launch. Every win,
near-miss, patch, and raw run is public.”
