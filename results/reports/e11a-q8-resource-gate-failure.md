# E11a successor Q8_0: valid scoring, frozen resource-gate failure

Status: **invalid deployable-frontier cell; scoring retained as resource-infeasible**

GitHub run: [30847559089](https://github.com/Arshgill01/Arm/actions/runs/30847559089)

Artifact: `e11a-successor-ministral3_3b_q8_0-30847559089-1` (ID `8870637364`)

Artifact digest: `sha256:5b96094a6b4ff0d6046eef8ece4f3a87f313b113911049217623d4212b4e1395`

## Result

The exact native safe-sampled scorer completed all 300 holdout samples and
14,374 token-score requests in 2,749.93 seconds with zero request failures. All
raw responses are retained once, the synthetic API preflight passed, and the
quality coordinates validate independently:

| Task | Frozen metric | Q8_0 |
|---|---|---:|
| ARC Easy | normalized accuracy | 0.54 |
| HellaSwag | normalized accuracy | 0.73 |
| Winogrande | accuracy | 0.59 |

The server’s peak RSS was 10,003,620 KiB. The contract froze an 8,388,608 KiB
ceiling before scoring, so Q8_0 exceeded it by 1,615,012 KiB (19.25%). The
server exited normally; independent validation correctly rejected the cell on
the resource gate.

## Decision

- Do not raise the frozen RSS ceiling after observation.
- Do not treat Q8_0 as a valid deployable stock-frontier cell.
- Do not repeat the 46-minute scoring run; its scoring evidence is complete.
- Preserve the quality coordinates only as a resource-infeasible point.
- A separately frozen aggregate may combine the other valid stock cells while
  explicitly classifying Q8_0 as infeasible rather than silently dropping it.

The retained artifact contains 14,466 hashed files and all 14,374 compressed
raw responses. This is quality robustness evidence, not a service-performance,
energy, PMU, cost, or local-device claim.
