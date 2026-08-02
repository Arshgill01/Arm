# E9a final compounded service comparison

Native run
[`30764802071`](https://github.com/Arshgill01/Arm/actions/runs/30764802071)
compared the exact earliest admitted E5b one-slot service with the exact final
E7c OpenSSL-off service in one `ubuntu-24.04-arm` job. The runner exposed two
Neoverse N2 logical CPUs; all ratios below are same-job comparisons on that
recorded topology, not comparisons with earlier four-core runs.

## Result

The result is `valid_final_service_win`. All eight fresh-process cells returned
23/30, reproduced the exact selected prediction map, and had zero request
failures or mismatches. The four E5b cells observed zero cached tokens; every
E7c request reused at least 25. Throughput CV was 0.062% for E5b and 0.086% for
E7c, below the frozen 5% scheduler-dispersion gate.

| Metric | Exact E5b earliest | Exact E7c final | Final / earliest |
| --- | ---: | ---: | ---: |
| Repeated median throughput | 0.27210 req/s | 0.46713 req/s | **1.71675x** |
| Pooled median HTTP latency | 3,576.09 ms | 2,090.72 ms | **0.58464x** |
| Pooled p95 HTTP latency | 5,251.61 ms | 3,705.49 ms | **0.70559x** |
| Median CPU seconds/request | 7.2725 s | 4.2223 s | **0.58059x** |
| Median readiness | 2,738.11 ms | 2,633.48 ms | 0.96179x |
| Maximum process RSS | 4,649,560 KiB | 4,452,100 KiB | 0.95753x |
| Build-local runtime closure | 20,058,816 bytes | 19,857,448 bytes | 0.98996x |
| Dynamic dependency basenames | 15 | 13 | −2 |

All predeclared gates passed: at least 1.25x throughput, at most 0.85x median
latency, p95 latency, and CPU-time ratios, exact quality/cache mechanisms, final
OpenSSL absence, readiness at most 15 seconds, and RSS below 8 GiB. One E5b
readiness cell took 10,133 ms while its other three took about 2,734–2,741 ms.
That visible outlier remains included and passed the absolute ceiling; the four
E7c readiness measurements were 2,630–2,638 ms.

The E5b binary resolved `libssl.so.3` and `libcrypto.so.3`. The E7c closure
resolved neither, retained eight build-local files, and was 201,368 bytes
smaller. The artifact also preserves both CMake inputs and caches, full build
commands, server hashes and versions, source commits and patch diff, host state,
all 240 measured request records, process counters, metrics, slots, and logs.

## Attribution boundary

E9a is deliberately compounded. It proves the end-product delta between two
historically admitted recipes; it does not assign the full 1.71675x result to
one change. The isolated evidence remains authoritative:

- E5c measured shared-prefix caching at 1.672x throughput with exact answers;
- E5e showed context right-sizing primarily reduced RSS while retaining 99.62%
  throughput;
- E5f measured the 64/64 batch at 1.0226x throughput and lower RSS;
- E6f found the patched runtime essentially neutral at 1.0028x; and
- E7b found OpenSSL pruning performance-neutral at 0.9998x while removing two
  dependency edges.

Those studies explain direction and boundaries, but their effects are not
added or multiplied to recreate E9a.

Python 3.10.20 independently regenerated the uploaded manifest byte for byte at
SHA-256
`39424e7f3a43a3a05b4139609224584945c8da7c1de66a9f224e8c7184de012d`.
The retained [`manifest`](../manifests/e9a-30764802071.json) includes the raw
per-request records; the frozen
[`contract`](../../experiments/e9a_contract.json) and native
[`workflow`](../../.github/workflows/final-service-comparison.yml) reproduce
the comparison.
