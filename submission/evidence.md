# Judge evidence index

All performance claims below come from native `aarch64` GitHub-hosted runners
with four Neoverse N2 cores. Each compact manifest is generated from raw evidence
by a fail-closed ingester. Raw artifacts are retained for 90 days by the linked
public workflow run; compact manifests and reports are committed permanently.

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
| KleidiAI native feature-selection fix | [E6a `30636911078`](https://github.com/Arshgill01/Arm/actions/runs/30636911078) | [`e6a` manifest](../results/manifests/e6a-30636911078.json) · [`report`](../results/reports/e6a-native-feature-fix.md) | `9a5951ae…24ae` |
| NEON Q8_0 vector-store patch: 2.029x | [E6b `30640282768`](https://github.com/Arshgill01/Arm/actions/runs/30640282768) | [`e6b` manifest](../results/manifests/e6b-30640282768.json) · [`report`](../results/reports/e6b-q8-vector-store.md) | `e870ad9c…e210` |
| Reasoning-budget source fix/app rejection | [E6c `30654805236`](https://github.com/Arshgill01/Arm/actions/runs/30654805236) | [`report`](../results/reports/e6c-reasoning-budget-fix.md) | mixed result; no deployment manifest |
| Public clean-checkout package validation | [`30672258413`](https://github.com/Arshgill01/Arm/actions/runs/30672258413) | 89 tests, all nine evidence hashes, exact plan, demo smoke test | passed on native `aarch64` |

## Final selected package

- Model: `mistralai/Ministral-3-3B-Instruct-2512`
- Source revision: `b35d4dfe56c142746f54dbd64f579faab2744308`
- GGUF producer: `unsloth/Ministral-3-3B-Instruct-2512-GGUF`
- Producer revision: `7564922f37fa5bbb62b87f09a55c12f1f91d7a6a`
- File: `Ministral-3-3B-Instruct-2512-Q4_K_M.gguf`
- Size: `2,146,497,824` bytes
- SHA-256: `fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4`
- License: Apache-2.0
- Runtime: llama.cpp `b10208`, commit
  `9d9a6d29f6b981cc7f41983d26e56485c6af1811`
- Serving profile: one slot, shared-prefix cache enabled, 256-token context,
  f16 K/V cache, explicit `auto` flash-attention mode, and 64/64 prompt batch
  enabled by default; weight repacking is the fast default, with a separately
  validated `--no-weight-repack` tier for constrained-memory hosts

## Recompute locally

```bash
python3 scripts/verify_submission.py
python3 -m unittest discover -s tests -v
python3 -m pareto64 plan \
  --manifest results/manifests/e3f-30656151957.json \
  --constraints configs/cloud-quality.json
```

The compact package check downloads nothing and uses only Python's standard
library. Exact model/runtime reproduction is defined by
[`selected-inference.yml`](../.github/workflows/selected-inference.yml).
