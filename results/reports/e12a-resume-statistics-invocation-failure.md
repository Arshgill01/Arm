# E12a completed-matrix inspection failure

Native Arm run
[`30847557186`](https://github.com/Arshgill01/Arm/actions/runs/30847557186)
successfully resumed the exact retained checkpoint from chunk 24 through chunk
31. The matrix process exited zero after 1:16:00 at 398% CPU, with a peak RSS
of 7,162,400 KiB, and wrote a 3,010,048-byte GGUF whose SHA-256 is
`2338867f…a1548`.

## Exact failure

The next, statistics-only invocation used `--in-file` and
`--show-statistics`, but omitted the tool's required `--model` argument. It
failed immediately with:

```text
error: --model is required
```

Consequently, the frozen statistics and metadata gates were not evaluated.
The completed bytes are a candidate matrix, not an accepted result, and this
run remains invalid.

## Inspection-only recovery boundary

A separately frozen recovery may download artifact
`e12a-resume-30847557186-1`, verify its exact identity and full file inventory,
rebuild the same b10216 native Arm tool closure, download the same BF16 model,
and add only the missing `--model` argument to the statistics invocation. It
must keep the matrix read-only, hash it before and after inspection, and apply
the unchanged 32-chunk, 182-entry metadata and statistics gates. It may not
recompute or modify the matrix.

## Reproducibility

Artifact ID `8871558287` has digest `b5590336…94ffc2`. Its 69 extracted files
total 30,215,221 bytes and have ordered inventory digest `9e0bcbc6…fc5e1`.
The full run log hashes to `ee5f3e23…b7198`. The compact
[`manifest`](../manifests/e12a-resume-30847557186.json) hashes to
`3683f835…497aa` and explicitly blocks generated-quant dispatch until the
inspection-only recovery passes.
