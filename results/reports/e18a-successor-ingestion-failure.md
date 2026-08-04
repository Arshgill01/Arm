# E18a successor post-measurement ingestion failure

Native GitHub Arm64 run
[`30861416953`](https://github.com/Arshgill01/Arm/actions/runs/30861416953)
completed the corrected 30-task instrumented training pass, generated 305 GCC
profile files, built the PGO-use binary, and completed all twelve frozen
fresh-process service cells. The workflow is nevertheless **invalid** because
its independent-ingestion step failed before writing a summary or inventory.

## Exact failure

The successor ingester temporarily replaced the base training validator with
its 180-second timeout adapter. The adapter then called that replaced symbol,
recursing into itself until the successor-only guard rejected the adjusted
contract. A second output-only defect—assigning into a missing `decision`
object—was found while developing the deterministic recovery. Both defects are
now covered by focused tests.

The source artifact
`e18a-workload-pgo-30861416953-1` (ID `8875533121`, digest
`sha256:eaa2f669b7a208e6b9ac0a4b16fd5b79411f8314baee0aa98f719c99d27110fd`)
contains 501 independently hashed files and 48,316,208 uncompressed bytes. The
[failure manifest](../manifests/e18a-successor-ingestion-failure-30861416953.json)
binds the exact failed run, native job, artifact, contract, 305-file profile,
twelve completed cells, traceback, and extracted-file inventory.

## Frozen recovery boundary

A local Python 3.10 replay of only the corrected ingester deterministically
produced SHA-256
`cc12c4a910c42b0e9477e4655cec2d49ca0c1c16fe8fdb4299bc4184fd8d48c3`.
It exposed an unchanged no-win: quality passed, but PGO reached 0.99243x
throughput, 1.00822x median latency, 1.00754x CPU seconds/request, and a
1.06885x runtime closure. Release remained selected. Those values are a replay
preview, not accepted product evidence from the failed workflow.

The separately frozen
[recovery contract](../../experiments/e18a_ingestion_recovery_contract.json)
may only download that exact artifact, verify all 501 files and live GitHub
identities, run the corrected deterministic ingester under Python 3.10.20, and
retain a compact result. It forbids source builds, model downloads, profile
training, server launches, service-cell reruns, and gate changes. The failed
workflow remains invalid regardless of the recovery outcome.
