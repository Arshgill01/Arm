# Public demo script — 2 minutes 45 seconds

Record at 1440×900 or 1920×1080. Show the browser and terminal at readable zoom.
Use no copyrighted music or third-party footage.

## 0:00–0:18 — The hook

**Screen:** Open the Pareto64 demo at the top.

**Voice:** “The fastest model lost. On native Arm, our KleidiAI package was 29%
faster and slightly smaller, but it failed the workload. Pareto64 selected the
only model that cleared quality and every deployment obligation.”

## 0:18–0:40 — Quality before speed

**Screen:** Point to the 70% Q4_0 marker, fixed 75% line, and selected 76.67%
Q4_K_M marker.

**Voice:** “The planner locks quality first, then evaluates latency, memory,
startup, and package size. There is no weighted score to hide a bad tradeoff,
and changing an operator policy cannot rescue a model whose experiment failed.”

## 0:40–1:00 — Interactive refusal

**Screen:** In “Decision lab,” click “Latency temptation,” show `No feasible
candidate`, then restore “Quality deployment.”

**Voice:** “When no measured package clears every obligation, Pareto64 refuses
deployment. The rejection reason and exact evidence hashes remain visible
instead of moving the gate after results.”

## 1:00–1:30 — Exact final service

**Screen:** Show the earliest-versus-final table.

**Voice:** “One native job ran the exact earliest and final service recipes four
times each with fresh processes and reverse-balanced order. All 240 answers
matched. The final service reached 1.717 times throughput, cut median latency
41.5%, and cut CPU seconds per request 41.9%. This is a compounded product
result; the controlled cache, context, batch, runtime, and dependency experiments
provide attribution.”

## 1:30–1:58 — Cache certification with an honest first-use cost

**Screen:** Show the E21b lifecycle table and first-use row.

**Voice:** “The online cache begins empty, shadows unknown transitions, certifies
only exact response reuse, and denies the unsafe start transition. Across four
repetitions it preserved 23 of 30 and every paired response, reached 1.728 times
lifecycle throughput, and broke even in cycle two. First-use p95 regressed 66%,
so that cost stays visible. The claim covers this identity and workload—not
arbitrary prompts.”

## 1:58–2:28 — Persistent Arm-packed weights

**Screen:** Navigate to “Packed weights.” Point to readiness, summed PSS, and
the clean-checkout lifecycle table.

**Voice:** “Pareto64 can pack all 183 Arm tensors once, verify every tensor, and
map one read-only sidecar into two workers. Same-job warm readiness fell 62%.
Two workers saved 1.995 GiB of summed PSS at unchanged throughput and exact
answers. The public prepack, verify, corruption-rejection, launch, stop, and
cleanup lifecycle passed all 14 gates. Its one-time 12.6-second construction
breaks even after an estimated nine warm starts. Cold storage, per-process RSS,
energy, and fleet economics remain unclaimed.”

## 2:28–2:40 — Failed evidence stays failed

**Screen:** Show E16d and E16e together in the evidence list, then run:

```bash
python3 scripts/verify_submission.py
```

**Voice:** “E16d completed the product but its frozen reader failed on raw
tokenizer bytes. E16e changed only that reader and replayed the exact artifact.
The failed run remains public.”

## 2:40–2:45 — Close

**Screen:** End on the report masthead and public source link.

**Voice:** “Pareto64 makes Arm optimization auditable: freeze, measure, reject,
select, verify, and launch.”
