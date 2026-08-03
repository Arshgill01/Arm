# E11a Q6_K frozen resource-gate failure

The Q6_K cell in native Arm run
[`30847559089`](https://github.com/Arshgill01/Arm/actions/runs/30847559089)
completed the exact pinned 300-sample safe-scored holdout before independent
ingestion rejected it on the unchanged 8 GiB peak-RSS gate.

## Valid scoring, invalid deployable cell

The server reached readiness in 3,132.41 ms and completed all 14,374 token-score
requests with zero request failures. The retained supplemental coordinates are:

| Task | Metric | Q6_K |
|---|---|---:|
| ARC-Easy | `acc_norm` | 0.57 |
| HellaSwag | `acc_norm` | 0.72 |
| Winogrande | `acc` | 0.58 |

Peak RSS was 8,585,348 KiB against the frozen 8,388,608 KiB limit: 196,740
KiB (2.35%) over. The server exited normally, so no rescoring is needed, but
Q6_K is not eligible for the deployable stock frontier. Its quality values may
appear only as a resource-infeasible point; the RSS gate is not raised after
observation.

This terminal outcome also invalidates the earlier recovery contract that was
frozen for seven valid new cells plus only one Q8_0 resource failure. After all
remaining source cells finish, a separate accounting contract must use the
actual outcome set and retain both infeasible models.

Artifact `e11a-successor-ministral3_3b_q6_k-30847559089-1` has ID
`8872868477`, digest `6bbb4aad…beb4`, and compressed size 40,732,032 bytes.
Independent validation hashes all 14,466 extracted files totaling 81,122,426
bytes. The retained [`manifest`](../manifests/e11a-successor-q6-resource-failure-30847559089.json)
hashes to `4756c623…9e4b`.
