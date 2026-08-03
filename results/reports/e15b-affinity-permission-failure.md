# E15b affinity scheduler: retained premeasurement permission failure

Status: **invalid premeasurement runner failure; exact retry allowed**

GitHub run: [30851213422](https://github.com/Arshgill01/Arm/actions/runs/30851213422)

Artifact: `e15b-affinity-split-scheduler-30851213422-1` (ID `8870681540`)

Artifact digest: `sha256:43533c5778be9c3924f99d94fb0a464258e2b5d7a3774aec3693a26e1ea4ed74`

## What happened

The native four-core Neoverse-N2 host, exact retained E9a runtime closure, and
selected model all verified successfully. The frozen affinity rule selected
CPUs 0 and 1 from the available 0–3 mask. The first measurement cell did not
start because `experiments/e15b_affinity_cell.sh` was retained with mode
`100644`; direct execution returned status 126 (`Permission denied`).

The complete 62-file artifact is hashed and retained.

## Evidence boundary

- Measured server processes started: 0
- Measured requests completed: 0
- Scheduler result observed: no
- Promotion permitted: no
- Contract or gate change permitted: no

Because no measured server launched, an exact retry is valid after changing
only the retained executable mode to `100755`. The E15b file content, affinity
rule, confirmatory disclosure, repetitions, and frozen contract SHA-256 remain
unchanged.
