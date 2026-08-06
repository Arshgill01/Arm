# Public demo script — 2 minutes 45 seconds

Record at 1440×900 or 1920×1080. Show the browser and terminal at readable zoom.
Use no copyrighted music or third-party footage.

## 0:00–0:20 — The result

**Screen:** Open the final report and point to the result card.

**Voice:** “Pareto64 fits eight exact Arm inference workers where the normal
representation could sustain six. Across four repetitions on one fixed 16.72
gigabyte Google Axion host, shared workers delivered 1.3525 times median
aggregate throughput while using 59.43 percent less summed PSS.”

## 0:20–0:42 — The boundary

**Screen:** Point to the red readiness boundary and the 2.0817× metric.

**Voice:** “That is a steady-state density result, not a full lifecycle win.
Shared readiness was 2.0817 times normal and missed our frozen limit of two.
We did not move the gate after seeing the throughput number.”

## 0:42–1:08 — Why it works

**Screen:** Open “Fixed-memory density” in the interactive demo and show the
normal/shared table.

**Voice:** “Normal workers privately rebuild about two gigabytes of Arm-packed
tensor pages. Pareto64 serializes all 183 packed tensors once, verifies them,
and maps one read-only inode into every worker. Per-worker speed is nearly the
same; the gain comes from fitting two more workers inside the same host.”

## 1:08–1:30 — The failure that defines the frontier

**Screen:** Point to the normal-8 OOM note and the evidence list.

**Voice:** “The curve tested one through eight workers. Normal eight failed
before readiness with one kernel OOM kill and no swap. Shared eight completed
with 13.84 gigabytes still available. The failed cell is retained as the
maximum-density boundary, never converted into a performance sample.”

## 1:30–2:00 — One deployable system

**Screen:** Show “Six planes, one deployment decision,” then the E22a row.

**Voice:** “This is not a hand-run benchmark. One Pareto64 command verifies or
builds the sidecar, launches workers, starts an OpenAI-compatible exact-transition
gateway, and writes an integrity-bound receipt. Unknown routes serve the oracle;
only exact reuse is certified, with bounded revalidation and revocation. E22a
passed all 420 requests across normal and shared product modes.”

## 2:00–2:24 — Quality still comes first

**Screen:** Scroll to the original quality comparison and final-service claim.

**Voice:** “The faster model still lost: Q4_0 was 29 percent faster but scored
70 percent. Q4_K_M scored 76.67 percent and became the only admitted package.
The final exact service later reached 1.7168 times its earliest admitted
baseline with all 240 answers unchanged.”

## 2:24–2:40 — Reproduce

**Screen:** Run `python3 scripts/verify_submission.py` and show the pass line.

**Voice:** “Contracts, hashes, requests, mappings, PMU counters, raw artifacts,
failed gates, and reports are retained together. The compact verifier downloads
nothing and fails if the evidence or claim boundary changes.”

## 2:40–2:45 — Close

**Screen:** End on the report title and public source link.

**Voice:** “Pareto64: more exact Arm workers, with the readiness bill visible.”
