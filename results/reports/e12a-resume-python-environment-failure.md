# E12a checkpoint-resume Python environment failure

Native Arm run
[`30846528784`](https://github.com/Arshgill01/Arm/actions/runs/30846528784)
successfully downloaded and revalidated the exact 24-chunk checkpoint,
reproduced the frozen corpus, rebuilt the pinned tools, and downloaded the exact
6.866 GB BF16 source model. It then failed before the first resumed matrix
operation, so no completed-matrix result exists.

## Exact failure

The workflow used the bare setup-python interpreter for its prerequisite GGUF
metadata dump. `gguf-py` imports NumPy, which was installed in the already
created pinned corpus virtual environment but not in the bare interpreter. The
step therefore raised:

```text
ModuleNotFoundError: No module named 'numpy'
```

`prior-imatrix-metadata.json` is empty, `imatrix-command.json` was never
created, and no `llama-imatrix` continuation process started. This is a
premeasurement environment failure, not evidence about the checkpoint or
model.

## Frozen repair boundary

A successor may invoke both GGUF metadata dumps with the pinned corpus venv's
Python executable. Nothing else may change: checkpoint bytes, model, corpus,
source, patches, `--chunk 24 --chunks 8`, execution order, statistics capture,
metadata requirements, and every acceptance gate remain frozen. This run stays
invalid even if that successor completes.

## Reproducibility

Artifact `e12a-resume-30846528784-1` (ID `8869079859`, digest
`c055436c…8f5090`) retains 62 original regular files totaling 27,161,501
extracted bytes; their ordered inventory hashes to `b78b2279…b44a5`. The run
log hashes to `d57529e3…cac4e1`. The compact
[`manifest`](../manifests/e12a-resume-30846528784.json) hashes to
`071ce129…e5a5e` and records that matrix compute never started.
