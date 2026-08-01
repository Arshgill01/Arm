# E7b loopback HTTP OpenSSL dependency-pruning ablation

Native run [`30695349303`](https://github.com/Arshgill01/Arm/actions/runs/30695349303)
completed the frozen `LLAMA_OPENSSL=ON` versus `OFF` comparison on a four-core
Neoverse N2. Both profiles used exact three-patch llama.cpp `b10216`, GCC 13.3,
LTO-off native/KleidiAI Release settings, the selected Ministral Q4_K_M model,
and the same repacked f16/256/64 cached four-thread one-slot loopback HTTP
service. Four fresh servers ran in on–off–off–on order.

## Result

This is a valid dependency-pruning candidate. OpenSSL-off removed exactly the
two frozen HTTPS library edges, added no replacement dependency, reproduced
exact quality, and passed every service and resource guardrail. It is selected
for a future evidence-bound loopback HTTP launch integration; HTTPS deployments
must keep OpenSSL enabled.

| Profile | Dynamic dependencies | Median throughput | Pooled median / p95 HTTP | Median server CPU seconds/request | Median readiness | Max RSS | Local runtime closure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| OpenSSL on | 15 | 0.93267 req/s | 1,046.58 / 1,852.19 ms | 4.24350 s | 2,392.54 ms | 4,453,488 KiB | 20,058,904 bytes |
| OpenSSL off | 13 | 0.93249 req/s | 1,045.96 / 1,855.58 ms | 4.24783 s | 2,480.59 ms | 4,451,944 KiB | 19,857,648 bytes |

The candidate retained 0.999811x throughput against the frozen 0.98x floor.
Median latency improved 0.060%; p95 increased 0.183%; measured server CPU
seconds/request increased 0.102%; readiness was 1.0368x baseline; and maximum
RSS decreased 1,544 KiB. Both repetitions of each profile reproduced the
selected 23/30 prediction map with stable predictions, zero reference
mismatches or request failures, and prefix reuse in every measured request.

## Dependency and build proof

The OpenSSL-on CMake cache and Ninja commands contain the enabled option and
`CPPHTTPLIB_OPENSSL_SUPPORT`; the OpenSSL-off evidence contains neither support
marker. Independent `ldd` inventory validation shows that the baseline resolves
`libssl.so.3` and `libcrypto.so.3`, while the candidate resolves neither and
adds no new library. The inventory falls from 15 to 13 dependency basenames.

Both build-local closures contain the same eight logical runtime files, but the
candidate bytes are smaller: 19,857,648 versus 20,058,904 bytes, a reduction of
201,256 bytes or 1.003%. Every server and build-local shared library is copied
into the raw artifact and checked by path, size, and SHA-256 against the raw
dependency inventory. System libraries are inventoried but are not counted in
that byte total.

OpenSSL-on and OpenSSL-off builds took 203.62 and 193.08 seconds respectively,
a 0.9482x ratio. Their build-process peak RSS values were 2,943,064 and
2,718,396 KiB. Build time and compiler memory are supporting promotion costs,
not headline optimization claims.

## Validation boundary

E7b establishes only that HTTPS support is an unnecessary dependency for this
exact patched native Arm loopback HTTP fast service. It does not establish a
security-vulnerability reduction, installed-package or container-image
savings, energy savings, another model/service/backend, or support for HTTPS
without OpenSSL. The result permits a separate fail-closed product integration;
it does not modify the launcher automatically.

Python 3.10 independent re-ingestion reproduced the uploaded summary byte for
byte at SHA-256
`8dffd667e8517a1b628c147f22f5e74755ab7d7d693e8eff1e1704ae387ffd9b`.

See the frozen [`E7b contract`](../../experiments/e7b_contract.json), retained
[`manifest`](../manifests/e7b-30695349303.json), and native
[`workflow`](../../.github/workflows/openssl-service.yml).
