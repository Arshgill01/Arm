# E18a premeasurement patch-path failure

Native GitHub Arm64 run
[`30858644241`](https://github.com/Arshgill01/Arm/actions/runs/30858644241)
failed before any compiler build, PGO training pass, model request, or measured
service process started. It is retained as
`invalid_premeasurement_relative_patch_path_failure` and provides no PGO or
performance result.

The runner verified the exact frozen contract and all 16 hash-bound inputs,
confirmed the native Arm64 host, cloned the pinned b10216 source, and checked out
commit `876a4321163249c43ca4e986818fab5ab081f282`. The first patch hash verified,
but `git -C "$SOURCE_DIR" apply` resolved its repository-relative argument from
inside the cloned source tree. That path did not exist there, so patch application
stopped with `No such file or directory`. Zero patches were applied and the model
download step was never reached.

The separately committed repair resolves the same three frozen patch paths
against `GITHUB_WORKSPACE`. It changes no source revision, patch bytes, model,
service, PGO flags, training workload, comparison order, repetitions, acceptance
gate, or claim boundary.

Artifact `e18a-workload-pgo-30858644241-1` (ID `8873443762`, digest
`sha256:2a3b2f74caa49109db5ded16fb2c07c2fa6126866bdd54f838fc5ed66fa10bb8`)
contains 23 independently hashed regular files. The retained
[manifest](../manifests/e18a-30858644241.json) binds the failure to the exact job,
commit, artifact, log, contract, native platform, and premeasurement boundary.
