# E12a complete application-conditioned importance matrix

Native Arm run
[`30855550027`](https://github.com/Arshgill01/Arm/actions/runs/30855550027)
closed E12a's last unevaluated gate without repeating matrix computation or
statistics. It used the exact retained matrix and exact retained 182-tensor
statistics, added the frozen `pyyaml==6.0.3` metadata dependency, and parsed the
GGUF through the pinned b10216 gguf-py source.

## Accepted matrix

| Field | Accepted value |
| --- | ---: |
| SHA-256 | `2338867f…a1548` |
| Size | 3,010,048 bytes |
| Completed chunks | 32 × 512 tokens |
| Importance entries | 182 |
| GGUF tensors | 364 |
| Statistics tensors | 182 |

The ordered dataset metadata binds the original 24-chunk corpus path followed
by the exact eight-chunk continuation path. Final entry names match the retained
checkpoint exactly. The matrix hash is identical before and after the metadata
read.

## No hidden repetition

This final successor did not rebuild `llama-imatrix`, download the BF16 model,
repeat the 182-tensor statistics command, recompute any chunk, or modify the
matrix. It only checked out the exact parser source, installed
`numpy==2.2.6` plus `pyyaml==6.0.3`, and performed the frozen JSON metadata
dump. The original timeout and three failed continuations remain invalid; this
separately frozen success does not rehabilitate them.

## Reproducibility and decision

Artifact `e12a-metadata-recovery-30855550027-1` (ID `8872307191`, digest
`876755a4…88c22`) retains the nested source evidence and final dump. Local
archive-mode rehydration followed by independent ingestion reproduced the
workflow summary byte for byte at SHA-256 `acd97619…b109d`; all 131 runner-
inventoried files were rehashed.

The retained [`manifest`](../manifests/e12a-metadata-recovery-30855550027.json)
hashes to `12cb3e00…5476d`. E12a now authorizes the separately frozen generated-
quant successor, subject independently to E11a's stock-frontier prerequisite.
It makes no generated-model, quality, service, energy, PMU, device, fleet, or
cost claim by itself.
