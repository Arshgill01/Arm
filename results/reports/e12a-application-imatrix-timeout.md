# E12a application-conditioned imatrix timeout

Native Arm run
[`30822632328`](https://github.com/Arshgill01/Arm/actions/runs/30822632328)
used the exact frozen 32×512-token application-conditioned calibration contract.
Source, patches, OpenSSL-off build, 6,866,220,032-byte BF16 model, 309,892-byte
corpus, and native `aarch64` environment all validated before generation. The
job then reached its unchanged 300-minute ceiling, so E12a is invalid and the
original E12b dispatch remains forbidden.

## Retained failure evidence

The first pass took 569.39 seconds and projected 5h03m40s for generation alone.
After 4h46m55s in the generation step, GitHub cancelled the job with `The
operation was canceled.` The post-timeout `always()` upload succeeded, while
the independent full-matrix validator correctly remained skipped.

The periodic output contains a structurally valid last-complete checkpoint:

| Evidence | Retained value |
| --- | ---: |
| Complete chunks | 24 / 32 (75%) |
| Chunk size | 512 tokens |
| Activation entries | 182 paired sum/count entries |
| GGUF tensors | 364 |
| Checkpoint bytes | 3,009,952 |
| Checkpoint SHA-256 | `b95f4dca…e4b48f` |
| Frozen corpus SHA-256 | `8c4c6ed6…4ee2b5` |
| Frozen BF16 SHA-256 | `413b0d1f…bc266` |

No activation statistics, quantized model, quality score, or service result was
observed. Work after the last periodic save is not claimed or reused.

## Frozen successor boundary

The only authorized successor is an exact continuation from chunk 24. It may
load this checkpoint and process chunks 24–31 in order. It may not change the
model, corpus bytes or order, source and patches, context or batch sizes,
threads, total chunk count, output format, no-PPL policy, or any validation
gate. The timeout remains a negative result regardless of whether that
separately frozen continuation succeeds.

## Reproducibility

Artifact `e12a-imatrix-30822632328-1` (ID `8868581019`, digest
`120665a1…dec05d`) retains 55 original regular files totaling 27,100,215
extracted bytes; their ordered inventory hashes to `a57373b0…9c3c`. The native
run log hashes to `95675b03…50d4d`. The compact
[`manifest`](../manifests/e12a-30822632328.json) hashes to
`d1fa4b74…3c994` and explicitly forbids a completed-imatrix or generated-quant
claim.
