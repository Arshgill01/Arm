# E10d external holdout: retained paired API failure

Native Arm run
[`30818303255`](https://github.com/Arshgill01/Arm/actions/runs/30818303255)
does **not** produce a valid external-holdout comparison. Both independently
scheduled model cells failed the frozen zero-request-failure gate, and GitHub
correctly skipped the paired aggregate. The partial task metrics are not
comparable and are not used for a quality, model, frontier, or performance
claim.

## Frozen experiment

E10d selected ARC Easy, HellaSwag, and WinoGrande with 100 salted, pinned
samples per task before observing model outcomes. The exact same 300 samples,
1,000 choices, 14,374 target-token requests, harness task construction,
Q4_K_M primary, nearest Q4_0 control, and native `ubuntu-24.04-arm` service were
frozen. Each model ran in a fresh one-slot E7c OpenSSL-off b10216 process with
the E10b exact-token probability patch. Every successful response was retained
as a gzip file. Acceptance required all 300 samples, all 14,374 token requests,
and zero failures for both models; there was no minimum accuracy gate.

Both jobs ran on four-logical-CPU Neoverse N2 hosts. Their synthetic preflights
passed with zero repeat log-probability delta, and both artifacts contain the
same prepared-workload SHA-256
`0cfde913aeb36570e3ac527201035f16cd9b029f73902d4b92d5bd2889820d5e`.

## Exact failure

| Cell | Completed choice records | Completed token records | Failed samples | First missing probability records |
| --- | ---: | ---: | ---: | --- |
| Q4_K_M primary | 997 | 14,262 | 1 | HellaSwag ordinal 44, source 3681, choice 1, token index 28, target ID 1194 |
| Q4_0 control | 994 | 14,159 | 2 | The same ordinal-44 failure, plus HellaSwag ordinal 70, source 6417, choice 1, token index 13, target ID 27043 |

In each case the `/completion` request returned HTTP 200, but the response did
not contain the one `completion_probabilities` entry required to bind the
requested token's score. The probe therefore emitted
`ValueError: completion response lacks one probability entry`, marked the
sample failed, continued through the frozen sample list, and exited normally.
The strict ingester then rejected each cell with
`ValueError: E10d probe header or totals differ`.

The independent failure ingester accounts for every retained raw file and the
partial attempts immediately before each missing record:

| Cell | Raw responses validated | Compressed bytes | Uncompressed bytes | Received but not retained failure responses | Frozen token requests not attempted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Q4_K_M | 14,290 | 20,984,813 | 43,227,332 | 1 | 83 |
| Q4_0 | 14,200 | 20,826,007 | 42,919,698 | 2 | 172 |

The ordinal-44 partial choice has exactly 28 contiguous retained responses
before token index 28 in both cells. The ordinal-70 Q4_0 partial choice has
exactly 13 before token index 13. No raw file has an unexplained or duplicate
role. The response that triggered each exception was received but was not
written by the original E10d probe because that probe parsed the probability
entry before calling its raw-retention function. A successor preflight must
retain responses before parsing.

## Interpretation and decision

This is an API-response compatibility failure, not evidence that either model
has poor task quality. Descriptive metrics from incomplete samples are excluded
because the missing samples and unattempted requests differ by model. Likewise,
the cell elapsed time, CPU time, and RSS are not compared as model-performance
results.

The original E10d contract remains failed. Its exact E11a stock-frontier and
E12b generated-frontier prerequisites are unsatisfied, so neither original
experiment may be dispatched or relabeled with substitute evidence. The next
allowed action is a separately frozen, two-case native compatibility preflight:
reproduce the missing records, force a known complete one-byte sampled token,
retain every response before parsing, and require the requested raw
pre-sampling log probabilities to match the original prefix and a fresh repeat
within the predeclared tolerance. Passing that preflight can authorize only a
newly named full-holdout successor.

## Reproducibility

The 90-day artifacts are
`e10d-ministral3_3b_q4_k_m-30818303255-1` (ID `8861197969`) and
`e10d-ministral3_3b_q4_0-30818303255-1` (ID `8860154414`). They retain the
contract, sample map, prepared workload, task and harness provenance, source
revision and complete patch diff, compiler and CMake records, runtime closure,
model hash, commands, host capture, server logs, process counters, partial
per-sample results, and all successful raw HTTP responses.

Local independent ingestion reproduced the exact breakpoints and inventories
from both downloaded artifacts. The compact pair
[`manifest`](../manifests/e10d-30818303255.json) has SHA-256
`59cc8fa743962108798438df89eb15e5f9fb474cc1afe581c0b574fe27ac5336`;
the full primary and control cell manifests are retained beside it.
