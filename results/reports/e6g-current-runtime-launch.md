# E6g current-runtime launch integration

Native run [`30679814341`](https://github.com/Arshgill01/Arm/actions/runs/30679814341)
reproduced the accepted E6f service through the actual fail-closed Pareto64
launch adapter on a four-core Neoverse N2. The job rebuilt the exact patched
llama.cpp `b10216` source, downloaded the selected Ministral Q4_K_M model, and
started the service with `python -m pareto64 launch` rather than reconstructing
the server command in the workflow.

## Result

The adapter verified and launched the one exact current-runtime service it is
allowed to admit. All 30 measured requests returned successfully, reproduced
the selected 23/30 prediction map without drift, and observed cached-prefix
reuse. Readiness was 3.980 seconds, maximum RSS was 4,453,376 KiB, throughput
was 0.93038 requests/s, and measured server CPU time was 4.2467 seconds per
request. The single-slot and metrics endpoints also passed their frozen gates.

The recipe bound the recomputed model selection, E6f manifest, launch contract,
four-file full-index source diff, three patch hashes, exact git commit, CMake
source/build relationship and cache, server version/location/binary, model
bytes, service arguments, live server PID, and timed invocation. The retained
binary SHA-256 is
`4bcccf12020b24dd7ce404ad6436dfaf136d0924c1236a8d094f4dc93725977d`.

Python 3.10 independent re-ingestion reproduced the uploaded summary byte for
byte at SHA-256
`13496b5e62e50bc3e617e6a80631c87ac6bc29015ea83499cb2ff885ec404ac9`.

## Validation boundary

This result validates the explicit Pareto64 launch integration for the exact
repacked f16/256/64 cached, four-thread, one-slot patched-`b10216` service. It is
not a new optimization comparison, an energy claim, a full upstream-platform
validation, or permission to promote no-repack, lower-thread, concurrency,
alternate-cache, batch, context, Flash, or other model profiles.

The earlier attempt `30679759732` stopped before model download or build because
its source capture omitted E6f's `--full-index` diff option. The corrected run
uses the exact retained source-proof format; no model, source, patch, service,
measurement, or acceptance gate changed.

See the frozen [`E6g contract`](../../experiments/e6g_contract.json), retained
[`manifest`](../manifests/e6g-30679814341.json), and native
[`workflow`](../../.github/workflows/current-runtime-launch.yml).
