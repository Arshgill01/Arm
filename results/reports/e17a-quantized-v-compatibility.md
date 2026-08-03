# E17a bounded quantized-V compatibility preflight

Native Arm run
[`30856539977`](https://github.com/Arshgill01/Arm/actions/runs/30856539977)
passes the unchanged bounded preflight after two retained premeasurement
failures. It uses the exact E9a OpenSSL-off `b10216` service, selected Q4_K_M
model, one 1,024-token slot, Flash Attention, fresh processes, disabled prompt
cache, and the three tasks selected before observation.

## Result

| K/V cache | Allocation | Reduction vs f16/f16 | Diagnostic answers | Requests |
|---|---:|---:|---:|---:|
| f16/f16 | 104.00 MiB | — | 3/3 exact | 3/3 successful |
| q8_0/q8_0 | 55.25 MiB | 46.88% | 3/3 exact | 3/3 successful |
| q4_0/q4_0 | 29.25 MiB | 71.88% | 3/3 exact | 3/3 successful |

Every server reached readiness, logged Flash Attention and exactly one KV
allocation, returned zero request failures, and reproduced `C`, `C`, `B` for
`arithmetic-02`, `logic-01`, and `systems-04`. Both quantized pairs are
therefore structurally eligible for the separately frozen long-context
successor. Neither is promoted as a service configuration from this preflight.

The reported request rates and CPU/latency diagnostics are retained but are
not a performance comparison: each cell contains only three requests in one
unbalanced order. E17a makes no long-context, serving-density, general quality,
energy, PMU, device, fleet, or cost claim.

## Provenance and independent replay

The successful artifact `e17a-kv-v-cache-preflight-30856539977-1` has ID
`8872697322`, digest `a1aeb6c2…74bc`, and compressed size 13,915,578 bytes.
Independent ingestion reproduces its workflow summary byte for byte. All 105
workflow-inventoried files verify with inventory digest `425c8aa1…92d`.

The retained [`manifest`](../manifests/e17a-30856539977.json) includes exact
answers, latencies, CPU seconds/request, readiness, allocation logs, recipes,
runtime/model closure, both earlier failures, runner identity, and artifact
provenance.
