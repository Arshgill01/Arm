# E12a metadata-inspection dependency failure

Native Arm run
[`30854613238`](https://github.com/Arshgill01/Arm/actions/runs/30854613238)
verified the exact completed matrix artifact, rebuilt the frozen b10216 native
inspector, downloaded the exact BF16 model, and successfully ran the corrected
statistics command without changing the matrix bytes.

## Evidence established before failure

The statistics process exited zero in 0.02 seconds and reported all 182 frozen
tensors. Its output hashes to `64aa1fa9…bc66`. The matrix remained exactly
3,010,048 bytes at SHA-256 `2338867f…a1548` before and after inspection.

## Exact failure

The following GGUF metadata dump imported NumPy successfully but failed while
importing gguf-py's metadata module:

```text
ModuleNotFoundError: No module named 'yaml'
```

The inspection venv pinned `numpy==2.2.6` but omitted the already-known
`pyyaml==6.0.3` dependency. `imatrix-metadata.json` is empty, so the original
32-chunk metadata gate remains unevaluated and the matrix is not yet accepted.

## Metadata-only recovery boundary

A separately frozen successor may download the exact artifact, check out the
same gguf-py source, install only `numpy==2.2.6` and `pyyaml==6.0.3`, and dump
the read-only matrix metadata. It may not rebuild the native tool, download the
model, repeat statistics, recompute the matrix, or mutate its bytes.

Artifact `e12a-inspection-recovery-30854613238-1` (ID `8872135870`, digest
`8575c071…a92b2`) retains 111 files totaling 42,411,274 bytes with ordered
inventory digest `5bcb388c…15fa7`. The compact
[`manifest`](../manifests/e12a-inspection-recovery-30854613238.json) hashes to
`577b4756…7fa4e`.
