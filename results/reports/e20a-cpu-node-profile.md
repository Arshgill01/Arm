# E20a software graph-node target profile

Native GitHub Arm64 source run
[`30863505489`](https://github.com/Arshgill01/Arm/actions/runs/30863505489)
completed all six frozen control and software-timed benchmark cases and the
exact selected-service quality pass. Its workflow-level ingester failed, so
the source run remains invalid. Inspection-only recovery run
[`30865578508`](https://github.com/Arshgill01/Arm/actions/runs/30865578508)
then verified the exact 90-file source artifact and replayed only the corrected
deterministic selector under Python 3.12.13. It did not rebuild, download a
model, launch a server or benchmark, or repeat a quality request.

## Result

The recovered profile preserves 23/30 exact selected answers with zero request
failures and zero reference mismatches. The predeclared selector admits only
the FFN gate/up family for a separately frozen feasibility study:

| Family | pp512 share | pp4096 share | Shared-activation layers | Geometric mean | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| FFN gate/up | **31.43%** | **10.85%** | 26 / 26 | **18.47%** | Eligible |
| Attention Q/K/V | 11.52% | 4.00% | 26 / 26 | 6.79% | Reject: long-prompt share below 10% |

This authorizes source inspection and a separate fail-closed implementation
contract for the FFN gate/up family. It does not automatically authorize a
source change or promote an optimization. Any candidate must still pass exact
correctness and same-job end-to-end service gates.

## Diagnostic boundary

The profiler records software wall-clock time around graph nodes and therefore
adds logging and timing overhead. The corresponding control/timed values—39.60
versus 39.42 tok/s at pp512, 13.79 versus 13.79 tok/s at pp4096, and 15.70
versus 15.40 tok/s at tg128—are descriptive mechanism checks, not speed
comparisons. They support only target selection, not a performance, PMU, cache,
energy, fleet, or cost claim.

The [retained manifest](../manifests/e20a-30865578508.json) binds both GitHub
runs, source/job/artifact identities, the 90-file source inventory, corrected
summary SHA-256, exact quality replay, profile records, binary and dependency
closures, and the compact recovery artifact. That artifact is
`e20a-ingestion-recovery-30865578508-1` (ID `8875955378`, digest
`sha256:5307636546fefb9506afce3b1aac3dd80e9448d77c4094768773d455f80e4fc3`).
