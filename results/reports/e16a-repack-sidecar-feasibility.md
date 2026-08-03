# E16a persistent Arm-repack sidecar feasibility

Native Arm run
[`30837796757`](https://github.com/Arshgill01/Arm/actions/runs/30837796757)
passes every frozen serialization and quality gate. Two fresh processes produce
the same complete packed-weight sidecar byte for byte despite different runtime
allocation addresses. This authorizes a separately frozen mmap-loader
experiment; E16a itself does not provide or benchmark that loader.

## Deterministic packed arena

| Evidence | Repetition 1 | Repetition 2 |
| --- | ---: | ---: |
| Repacked tensors | 183 | 183 |
| Packed tensor / arena bytes | 2,137,964,544 | 2,137,964,544 |
| Arena coverage | 100% | 100% |
| Complete sidecar bytes | 2,139,013,120 | 2,139,013,120 |
| Complete sidecar SHA-256 | `95a34727…9951d` | `95a34727…9951d` |
| Runtime buffer base | `0xff89ac913040` | `0xffcca0913040` |

Every tensor's name, source type, repack parameter type, four dimensions, byte
count, buffer-relative offset, column group, interleave, and SHA-256 match. The
canonical sidecar writes the packed bytes at their original arena-relative
offsets behind a fixed 1 MiB header. Its binding includes the selected model
hash, b10216 commit, aggregate four-patch diff, format versions, complete tensor
metadata, and the native CPU identity. The two distinct absolute buffer bases
are retained separately and neither appears in the sidecar.

The host is four-core Neoverse N2 (`0xd49`) AArch64. The shared feature-mask
hash is `4162bfdb…6f92`, and the detected SVE vector length is 16 bytes. Both
containers are reread before deletion: magic, canonical header, complete file
hash, and every embedded tensor region all verify.

## Quality and bounded storage

Both fresh E7c-derived processes reproduce 23/30, zero reference-prediction
mismatches, zero request failures, and the same complete prediction map. This
is quality proof for the instrumented construction path, not a performance
comparison; dumping and hashing multi-gigabyte arenas deliberately contaminate
startup and resource measurements.

After verification, each repetition deletes exactly 183 generated tensor files
(2,137,964,544 bytes) and its generated sidecar (2,139,013,120 bytes). Across
the job, 8,553,955,328 temporary bytes are removed. The uploaded artifact
contains hashes, indexes, inventories, runtime addresses, source/build/binary
provenance, quality results, logs, and cleanup records, but no raw tensor dump,
model GGUF, or deployable sidecar.

## Decision

E16a establishes that the exact Q4_K_M Arm representation is deterministic,
serializable, arena-relative, and quality-preserving for the retained model,
source diff, Neoverse N2 feature identity, and SVE length. It authorizes only a
separately frozen, fail-closed, read-only mmap loader comparison. It makes no
startup, RSS, PSS, throughput, sharing, portability, energy, or deployability
claim.

## Reproducibility

Independent local ingestion reproduces the 360,102-byte workflow summary byte
for byte at SHA-256 `0a06f2ea…63d4`. All 83 runner-inventoried files were
rehashed; the inventory SHA-256 is `8f77183b…ac5`. Artifact
`e16a-repack-sidecar-feasibility-30837796757-1` (ID `8865689364`, digest
`a9a4c7a2…3019`) is bound to frozen commit `baf7319`. The retained
[`manifest`](../manifests/e16a-30837796757.json) has SHA-256
`cd3ed3ce…c686`.
