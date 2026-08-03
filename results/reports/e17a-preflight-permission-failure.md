# E17a quantized-V preflight permission failure

Native Arm run
[`30855155720`](https://github.com/Arshgill01/Arm/actions/runs/30855155720)
verified the frozen contract, exact E9a OpenSSL-off runtime closure, and exact
selected Q4_K_M model. It failed before launching the first cache
configuration or issuing a model request.

## Exact failure

The new cell runner was stored without an executable mode, so direct shell
invocation returned:

```text
experiments/e17a_kv_preflight_cell.sh: Permission denied
```

The wrapper then attempted to record that status before the cell directory
existed. No `cells/` directory or summary exists; all three cache results are
unobserved.

## Frozen repair boundary

A separately committed successor may create the already-specified cell
directory and invoke the exact hash-bound script through `bash`. The runtime,
model, f16/f16–q8/q8–q4/q4 order, flash-attention setting, tasks, requests,
gates, and successor-selection rule remain unchanged.

Artifact `e17a-kv-v-cache-preflight-30855155720-1` (ID `8872171485`, digest
`a3c09e97…fd487`) retains 51 files totaling 33,768,238 bytes with ordered
inventory digest `becc9b3d…8c95`. The compact
[`manifest`](../manifests/e17a-30855155720.json) hashes to
`f1a9d291…94190`.
