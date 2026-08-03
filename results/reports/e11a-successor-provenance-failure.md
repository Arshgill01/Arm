# E11a safe-sampled stock frontier provenance failure

Native Arm run
[`30846943310`](https://github.com/Arshgill01/Arm/actions/runs/30846943310)
stopped all eight stock-quant cells in their shared prerequisite-validation
step. No model download, server start, inference request, quality score, or
frontier result occurred.

## Exact failure

The successor correctly verified its own contract and all earlier E10f input
hashes until it reached `tests/test_e10f.py`. E10f froze that file at
`78ac5c15…1a66acf`; after E10f was retained, commit `a7df4dd` legitimately added
tests for the retained result, producing current hash `69248894…4b421`. The
workflow incorrectly required a historical E10f working tree to equal the
current checkout instead of verifying the retained artifact and historical
commit blob.

The same mismatch appears in all eight logs. The aggregate is skipped, and the
failed upload steps correctly report that no per-model evidence directory had
yet been created. The run therefore has no model-level negative result.

## Frozen repair boundary

A successor may validate:

- the exact E10f retained manifest and aggregate;
- E10f's copied adapter inputs against their frozen hashes; and
- the historical `tests/test_e10f.py` blob at E10f commit `bb74269`.

It may not change the eight stock candidates, Q4_K_M anchor, safe-sampled
scorer, 300-sample workload, task versions, raw-response policy, quality
coordinates, dominance rule, or any acceptance gate. This first run remains
invalid regardless of the repaired successor.

## Reproducibility

The complete run log hashes to `efde1b80…ce692` and contains eight identical
`tests/test_e10f.py: FAILED` records. GitHub reports zero artifacts. The compact
[`manifest`](../manifests/e11a-successor-30846943310.json) hashes to
`c4f40aeb…6a372f` and explicitly records that zero model results were observed.
