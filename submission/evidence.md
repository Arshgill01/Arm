# Judge evidence index

All performance claims below come from native `aarch64` GitHub-hosted Neoverse
N2 runners. Each manifest records its exact CPU topology; E0–E7c used four
logical CPUs, while E9a's same-job final comparison used two. No absolute rate
is compared across those topologies. Each compact manifest is generated from
raw evidence by a fail-closed ingester. Raw artifacts are retained for 90 days
by the linked public workflow run; compact manifests and reports are committed
permanently.

| Claim | Native run | Compact evidence | SHA-256 |
| --- | --- | --- | --- |
| Native host and repeatability | [E0 `30630496081`](https://github.com/Arshgill01/Arm/actions/runs/30630496081) | [`e0` manifest](../results/manifests/e0-30630496081.json) · [`report`](../results/reports/e0-native-arm.md) | `b9e97153…78361` |
| Sponsor LLM-Runner end-to-end smoke | [E1 `30631789118`](https://github.com/Arshgill01/Arm/actions/runs/30631789118) | [`e1` manifest](../results/manifests/e1-30631789118.json) · [`report`](../results/reports/e1-llm-runner-smoke.md) | `121034d9…3cc8` |
| Paired KleidiAI ablation | [E2 `30632406883`](https://github.com/Arshgill01/Arm/actions/runs/30632406883) | [`e2` manifest](../results/manifests/e2-30632406883.json) · [`report`](../results/reports/e2-kleidiai-ablation.md) | `c9733b47…f88c` |
| 7B quality near-miss: 73.33% | [E3b `30643977955`](https://github.com/Arshgill01/Arm/actions/runs/30643977955) | [`e3b` manifest](../results/manifests/e3b-30643977955.json) · [`report`](../results/reports/e3b-quality-anchor.md) | `8fd89b9e…b628` |
| Selected Ministral frontier: 76.67% | [E3f `30656151957`](https://github.com/Arshgill01/Arm/actions/runs/30656151957) | [`e3f` manifest](../results/manifests/e3f-30656151957.json) · [`report`](../results/reports/e3f-ministral-frontier.md) | `54adb3d4…aff9c` |
| E3f clean end-to-end reproduction | [`30657209779`](https://github.com/Arshgill01/Arm/actions/runs/30657209779) | Uploaded summary matched independently at `268cc0ec…6932` | byte-identical |
| Planner API concurrency | [E5a `30638049776`](https://github.com/Arshgill01/Arm/actions/runs/30638049776) | [`e5a` manifest](../results/manifests/e5a-30638049776.json) · [`report`](../results/reports/e5a-planner-api.md) | `637bd829…b7ae` |
| Backlog 64 removes observed admission failures/tails | [E4a `30638730535`](https://github.com/Arshgill01/Arm/actions/runs/30638730535) | [`e4a` manifest](../results/manifests/e4a-30638730535.json) · [`report`](../results/reports/e4a-backlog-tuner.md) | `fdaf1064…8f4e` |
| Exact selected-model serving; two slots not promoted | [E5b `30659829983`](https://github.com/Arshgill01/Arm/actions/runs/30659829983) | [`e5b` manifest](../results/manifests/e5b-30659829983.json) · [`report`](../results/reports/e5b-selected-inference.md) | `aa529b16…f66c` |
| Shared-prefix cache: 1.672x serving throughput | [E5c `30662037235`](https://github.com/Arshgill01/Arm/actions/runs/30662037235) | [`e5c` manifest](../results/manifests/e5c-30662037235.json) · [`report`](../results/reports/e5c-prompt-cache.md) | `27a426dd…bfa7` |
| E5c promoted-default reproduction: 1.681x | [`30663285866`](https://github.com/Arshgill01/Arm/actions/runs/30663285866) | 120 exact responses; cache-on exercised through launcher default | `036a65d2…1747` byte-identical ingest |
| Cached two-slot interaction rejected at 1.0619x | [E5d `30664666945`](https://github.com/Arshgill01/Arm/actions/runs/30664666945) | [`e5d` manifest](../results/manifests/e5d-30664666945.json) · [`report`](../results/reports/e5d-cached-concurrency.md) | `a844e58e…6d76e5` |
| Context right-sizing saves 183.36 MiB without drift | [E5e `30667019678`](https://github.com/Arshgill01/Arm/actions/runs/30667019678) | [`e5e` manifest](../results/manifests/e5e-30667019678.json) · [`report`](../results/reports/e5e-kv-context-profile.md) | `6312dc78…5ed2c` |
| E5e promoted-default reproduction | [`30668306694`](https://github.com/Arshgill01/Arm/actions/runs/30668306694) | 23/30 twice; unflagged f16/256 cells; 187,468 KiB saved | `51f1e704…96e8ac` byte-identical ingest |
| Prompt batch 64/64 cuts compute buffer 75% | [E5f `30669700602`](https://github.com/Arshgill01/Arm/actions/runs/30669700602) | [`e5f` manifest](../results/manifests/e5f-30669700602.json) · [`report`](../results/reports/e5f-prompt-batch-profile.md) | `396222dd…f92d4b` |
| E5f promoted-default reproduction | [`30670972497`](https://github.com/Arshgill01/Arm/actions/runs/30670972497) | 180 exact responses; unflagged 64/64 cells; 17,264 KiB saved | `4b0e4632…42135a` byte-identical ingest |
| Marginal batch floor retains 64/64 | [E5g `30671733556`](https://github.com/Arshgill01/Arm/actions/runs/30671733556) | [`e5g` manifest](../results/manifests/e5g-30671733556.json) · [`report`](../results/reports/e5g-prompt-batch-floor.md) | `374e5af3…984b6` |
| No-repack memory tier saves 2,072,268 KiB RSS | [E5h `30672633366`](https://github.com/Arshgill01/Arm/actions/runs/30672633366) | [`e5h` manifest](../results/manifests/e5h-30672633366.json) · [`report`](../results/reports/e5h-weight-repack-boundary.md) | `e048f3e2…90faa` |
| Measured policies route fast and ≤3-GiB tiers | [`30674971776`](https://github.com/Arshgill01/Arm/actions/runs/30674971776) | [`throughput plan`](../results/plans/e5h-service-throughput.json) · [`memory plan`](../results/plans/e5h-service-memory.json) · [`report`](../results/reports/service-tier-planner.md) | `6e00839f…e4b4` · `15a6fac8…27d` |
| Flash Attention ablation: valid 1.0322x no-win | [E5i `30674023380`](https://github.com/Arshgill01/Arm/actions/runs/30674023380) | [`e5i` manifest](../results/manifests/e5i-30674023380.json) · [`report`](../results/reports/e5i-flash-attention-ablation.md) | `ca41dd4c…a46ba2` |
| Thread profile retains four-thread default | [E5j `30677332825`](https://github.com/Arshgill01/Arm/actions/runs/30677332825) | [`e5j` manifest](../results/manifests/e5j-30677332825.json) · [`report`](../results/reports/e5j-thread-efficiency-profile.md) | `747b6795…c4ff7` |
| KleidiAI native feature-selection fix | [E6a `30636911078`](https://github.com/Arshgill01/Arm/actions/runs/30636911078) | [`e6a` manifest](../results/manifests/e6a-30636911078.json) · [`report`](../results/reports/e6a-native-feature-fix.md) | `9a5951ae…24ae` |
| NEON Q8_0 vector-store patch: 2.029x | [E6b `30640282768`](https://github.com/Arshgill01/Arm/actions/runs/30640282768) | [`e6b` manifest](../results/manifests/e6b-30640282768.json) · [`report`](../results/reports/e6b-q8-vector-store.md) | `e870ad9c…e210` |
| Reasoning-budget source fix/app rejection | [E6c `30654805236`](https://github.com/Arshgill01/Arm/actions/runs/30654805236) | [`report`](../results/reports/e6c-reasoning-budget-fix.md) | mixed result; no deployment manifest |
| Current-upstream three-patch revalidation | [E6d `30675654688`](https://github.com/Arshgill01/Arm/actions/runs/30675654688) | [`e6d` manifest](../results/manifests/e6d-30675654688.json) · [`report`](../results/reports/e6d-current-upstream-patches.md) | `32e01c0b…c9767fa` |
| Upstream-equivalent native Arm CPU lane | [E6e `30676413765`](https://github.com/Arshgill01/Arm/actions/runs/30676413765) | [`e6e` manifest](../results/manifests/e6e-30676413765.json) · [`report`](../results/reports/e6e-upstream-arm-cpu-lane.md) | `63c0e450…63c27f1` |
| Current patched selected service passes upgrade gates | [E6f `30678703184`](https://github.com/Arshgill01/Arm/actions/runs/30678703184) | [`e6f` manifest](../results/manifests/e6f-30678703184.json) · [`report`](../results/reports/e6f-current-runtime-service.md) | `da95b831…470ace` |
| Exact current-runtime adapter launch | [E6g `30679814341`](https://github.com/Arshgill01/Arm/actions/runs/30679814341) | [`e6g` manifest](../results/manifests/e6g-30679814341.json) · [`report`](../results/reports/e6g-current-runtime-launch.md) | `13496b5e…404ac9` |
| Current no-repack tier passes upgrade gates | [E6h `30690331795`](https://github.com/Arshgill01/Arm/actions/runs/30690331795) | [`e6h` manifest](../results/manifests/e6h-30690331795.json) · [`report`](../results/reports/e6h-current-runtime-memory-service.md) | `7b112b38…53b27f` |
| Exact current no-repack adapter launch | [E6i `30691254831`](https://github.com/Arshgill01/Arm/actions/runs/30691254831) | [`e6i` manifest](../results/manifests/e6i-30691254831.json) · [`report`](../results/reports/e6i-current-runtime-memory-launch.md) | `2bcbd7e1…06d2` |
| Whole-program LTO compiler/build no-win | [E7a `30692292700`](https://github.com/Arshgill01/Arm/actions/runs/30692292700) | [`e7a` manifest](../results/manifests/e7a-30692292700.json) · [`report`](../results/reports/e7a-lto-service.md) | `b48e6c12…b46839` |
| HTTP-only OpenSSL dependency pruning | [E7b `30695349303`](https://github.com/Arshgill01/Arm/actions/runs/30695349303) | [`e7b` manifest](../results/manifests/e7b-30695349303.json) · [`report`](../results/reports/e7b-openssl-service.md) | `8dffd667…7ffd9b` |
| Exact HTTP-only dependency-pruned launch | [E7c `30696606993`](https://github.com/Arshgill01/Arm/actions/runs/30696606993) | [`e7c` manifest](../results/manifests/e7c-30696606993.json) · [`report`](../results/reports/e7c-http-runtime-launch.md) | `f4e73971…e1857cf` |
| Earliest-versus-final compounded service | [E9a `30764802071`](https://github.com/Arshgill01/Arm/actions/runs/30764802071) | [`e9a` manifest](../results/manifests/e9a-30764802071.json) · [`report`](../results/reports/e9a-final-service-comparison.md) | `39424e7f…012d` |
| External-holdout exact-server API blocker | [E9b preflight `30766707967`](https://github.com/Arshgill01/Arm/actions/runs/30766707967) | [`blocker` manifest](../results/manifests/e9b-preflight-30766707967.json) · [`report`](../results/reports/e9b-holdout-preflight-blocker.md) | `9f654a9f…5162` |
| Public clean-checkout package validation | [`30766148919`](https://github.com/Arshgill01/Arm/actions/runs/30766148919) | 148 tests, 37 hashes including E9a, exact runtime/plan checks, demo smoke test | passed on native `aarch64` |

## Final selected package

- Model: `mistralai/Ministral-3-3B-Instruct-2512`
- Source revision: `b35d4dfe56c142746f54dbd64f579faab2744308`
- GGUF producer: `unsloth/Ministral-3-3B-Instruct-2512-GGUF`
- Producer revision: `7564922f37fa5bbb62b87f09a55c12f1f91d7a6a`
- File: `Ministral-3-3B-Instruct-2512-Q4_K_M.gguf`
- Size: `2,146,497,824` bytes
- SHA-256: `fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4`
- License: Apache-2.0
- Runtime: historical default llama.cpp `b10208`, commit
  `9d9a6d29f6b981cc7f41983d26e56485c6af1811`; exact-service opt-in patched
  `b10216`, commit `876a4321163249c43ca4e986818fab5ab081f282`, through
  [`runtime-b10216-selected-service.json`](../configs/runtime-b10216-selected-service.json)
- Serving profile: one slot, shared-prefix cache enabled, 256-token context,
  four inference/prompt threads, f16 K/V cache, explicit `auto`
  flash-attention mode, and 64/64 prompt batch
  enabled by default; weight repacking is the fast default, with a separately
  validated `--no-weight-repack` tier for constrained-memory hosts. Supplying a
  service policy binds and applies the measured tier automatically on the
  historical runtime. E6g validates the current-runtime opt-in for only the exact
  repacked E6f profile. E6h qualifies the same patched source for the exact
  no-repack tier, and E6i separately validates that tier's evidence-bound
  adapter launch. E7a rejects LTO for the fast tier after it misses both frozen
  benefit branches. E7b separately qualifies OpenSSL-off for the exact loopback
  HTTP service after removing two dependencies with no quality/performance
  regression; E7c binds that evidence and executes the exact dependency-pruned
  service through the adapter. HTTPS and every other current-runtime profile
  remain unchanged.
- Final same-job comparison: E9a runs the exact earliest E5b and exact E7c
  recipes four times each. All 240 measured answers match; final throughput is
  1.7168x, median/p95 latency ratios are 0.5846x/0.7056x, and CPU
  seconds/request is 0.5806x. This is a compounded product result; E5c, E5e,
  E5f, E6f, and E7b remain the mechanism evidence.

## Recompute locally

```bash
python3 scripts/verify_submission.py
python3 -m unittest discover -s tests -v
python3 -m pareto64 plan \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json
python3 -m pareto64 service-plan \
  --manifest results/manifests/e5h-30672633366.json \
  --constraints configs/service-memory.json
```

The compact package check downloads nothing and uses only Python's standard
library. Exact model/runtime reproduction is defined by
[`selected-inference.yml`](../.github/workflows/selected-inference.yml).
