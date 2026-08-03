# E17a quantized-V subset-reference probe failure

Native Arm run
[`30855793293`](https://github.com/Arshgill01/Arm/actions/runs/30855793293)
started all three frozen fresh-process servers. Each reached readiness with
Flash Attention enabled. The f16/f16, q8/q8, and q4/q4 launches respectively
logged 104.00, 55.25, and 29.25 MiB KV allocations. Those values are retained
only as descriptive launch diagnostics because no measured model request ran.

## Exact failure

The unchanged E5b request engine validates that its task IDs exactly equal its
reference-prediction map. E17a intentionally supplies the three tasks frozen
before observation, while the stable E3f reference manifest contains all 30
application tasks. Each cell therefore stopped at the same pre-request check:

```text
ValueError: task IDs differ from the selected reference predictions
```

All caller statuses were nonzero and no `probe.json` exists. The result is
invalid for compatibility, answers, quality, performance, or successor
selection; none of the observed allocations is promoted.

## Frozen repair boundary

A separately committed successor may load the same hash-bound 30-task stable
reference map, filter it to the three already-frozen task IDs, and pass that
map to the unchanged E5b HTTP request engine. The runtime, model, task content
and order, f16/f16–q8/q8–q4/q4 sequence, cache settings, requests, gates, and
successor-selection rule do not change.

Artifact `e17a-kv-v-cache-preflight-30855793293-1` (ID `8872425138`, digest
`b818da16…1f39`) retains 82 inventoried files totaling 33,859,512 bytes with
ordered inventory digest `b22bee69…a1268`. The compact
[`manifest`](../manifests/e17a-30855793293.json) hashes to
`64f8fcf9…b0737`.
