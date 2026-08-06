# Plan execution audit — 2026-08-06

This report maps the execution plan in the workspace to retained evidence. It
does not modify or reinterpret any frozen experiment contract. “Achieved” means
the repository or a public external artifact proves the item. “Parked” means a
predeclared stop or failed gate closes the branch without a positive claim.
“Entrant-controlled” means the remaining action requires personal eligibility,
account access, or a legal attestation that cannot be inferred from technical
evidence.

## Executive status

The technical submission is ready. Pareto64 has a unified product command,
native Arm product-path preflight, repeated fixed-memory Google Axion result,
public report and demo, public raw bundles, final gallery, supplemental
walkthrough, and a passing clean-checkout native Arm judge workflow.

The only submission-blocking work is entrant-controlled: confirm eligibility,
team representation and Arm Developer Program membership; enter the personal
survey answers; upload the four gallery images; decide whether to omit the
optional video field or mirror the supplemental MP4 to YouTube, Vimeo or Youku;
and submit through the authenticated Devpost account. The direct GitHub MP4 is
public supplemental evidence but does not satisfy Devpost's optional video-field
hosting rule.

## P0 task board

| Plan item | Status | Authoritative evidence |
| --- | --- | --- |
| Stable Arm performance lane selected and fingerprinted | Achieved | E22b/E22c ran on one `c4a-highcpu-8` Neoverse V2 node with 16,723,460,096 physical bytes, eight cores, no SMT, no swap, and all five frozen PMU events. |
| Sidecar scaling preflight complete | Achieved | E22a run [`31086439785`](https://github.com/Arshgill01/Arm/actions/runs/31086439785) exercised normal/shared `pareto64 deploy` at 1/2/4 workers: 420/420 exact requests and read-only shared-inode proof. |
| Primary Arm-specific claim frozen from valid native evidence | Achieved, narrowed by gate | E22c repeats normal-6/shared-8 four times each: 1.3525x median aggregate throughput, 59.43% lower summed PSS, 1,680 exact requests. Readiness is 2.0817x and fails the frozen 2.0x gate, so only steady-state density is promoted. |
| One coherent product command works cleanly | Achieved | `python3 -m pareto64 deploy` composes verification, normal/shared workers, mapping proof, exact-transition gateway, bounded revalidation/revocation, and a deployment receipt. Product tests and E22a cover the path. |
| Public demo URL filled | Achieved | [`https://pareto64-arm-evidence.arshgill01.chatgpt.site/demo/index.html`](https://pareto64-arm-evidence.arshgill01.chatgpt.site/demo/index.html), anonymously verified. |
| Public video URL filled | Achieved as supplemental evidence | The 76-second direct MP4 is public in the E22 release. The optional Devpost video field remains entrant-controlled because its rules require YouTube, Vimeo or Youku. |
| Devpost draft complete | Achieved locally; account entry remains entrant-controlled | `submission/devpost.md` is paste-ready with source, report, demo, raw evidence, and supplemental walkthrough URLs and no public-URL placeholder. |
| Final submission verifier passes | Achieved | `scripts/verify_submission.py` covers 77 immutable evidence files, final E22 gates, demo, gallery, 296-word script and three publication URLs. Native Arm run [`31096144130`](https://github.com/Arshgill01/Arm/actions/runs/31096144130) passes from a clean checkout. |

## P1 differentiators

| Plan item | Resolution | Evidence and boundary |
| --- | --- | --- |
| Fixed-memory aggregate throughput/density | Achieved | E22b measures the complete 1/2/4/5/6 curve and normal-8 OOM boundary; E22c supplies the repeated final comparison. |
| N-worker cold/warm deployment economics | Partially measured, then parked | E22a/E22b retain construction bytes/time, verification time and command readiness across worker counts; E16e retains a warm-only nine-start estimate. E22c fails the readiness gate. Cold-cache, billing-product, energy and fleet economics remain explicitly unclaimed, so no further paid run is authorized. |
| Certificate-aware live gateway with drift revalidation | Achieved | The product gateway persists identity-bound exact-transition certificates, serves an uncached oracle on unknown routes, periodically revalidates certified routes and revokes successful output drift. Unit/integration coverage and E22a gateway smoke pass. |
| Realistic concurrent workload | Achieved within the declared application envelope | Each multi-worker E22 deployment runs the full 30-task, multi-prompt reference trace concurrently across workers after fixed warmups. Client concurrency is one per worker and total concurrency scales to eight; no arbitrary-traffic or fleet claim is made. |
| PMU-backed mechanism report | Achieved as telemetry, not causality | E22b/E22c retain `cpu_cycles`, `inst_retired`, `l1d_cache`, `l1d_cache_refill` and `l2d_cache` for every valid measured process window. The report refuses a broad kernel-causality claim because counters alone do not prove it. |

## P2 branch resolution

| Plan item | Resolution |
| --- | --- |
| True FFN dual-output prototype or better profile-selected kernel target | Parked after E20b's non-contiguous-output assertion and E20c's guarded successor reached only 1.002614x, below the frozen 1.03x minimum. |
| Valid 2K/4K/8K quantized-KV density ladder | Parked after E17c reached readiness in all nine cells but failed the required timing schema before any valid result; no partial K/V claim is made. |
| Apple SME2 validation | Deferred by the plan itself because no required Apple hardware was available; it is not a submission prerequisite. |
| Upstream-ready sidecar/kernel contribution | The reviewable patch series and validation evidence are retained. Upstream publication is not claimed because E9d's strict sanitizer lane reproduces an upstream diagnostic and fails the publication-readiness gate. |

## Completion criteria

- Strongest valid Arm-specific result: E22c repeated fixed-memory density.
- Clean reproducibility: public source plus native clean-checkout validation;
  exact large model/sidecar inputs remain hash-addressed and reproducible.
- Correctness before speed: every promoted E22 request is exact; the readiness
  failure narrows the claim.
- Raw evidence: public E22b/E22c sealed bundles, compact manifests, commands,
  host state, PMU, memory, response maps, hashes and reports.
- Product/video alignment: the supplemental walkthrough uses the shipped
  `pareto64 deploy`, policy refusal and final E22 evidence paths.
- Public access: repository, license, report, demo, raw bundles and MP4 are
  anonymously reachable.
- Negative evidence: normal-8 OOM, E22c readiness failure, stopped P1/P2 lanes
  and historical invalid runs remain visible.

## Resource and cost closeout

The single paid Axion VM existed for about 1.24 hours. At the frozen published
estimate of US$0.30296/hour, compute is approximately US$0.37 plus a small
prorated disk charge. This is a safety estimate, not a product billing claim.
Read-only post-run checks show no `c4a-highcpu-8` instance, Pareto64-named disk,
or Pareto64 reserved address. The temporary SSH key was removed without
changing the pre-existing key.

## Remaining entrant-controlled actions

1. Confirm legal eligibility and the submitting representative.
2. Confirm Arm Developer Program membership.
3. Confirm the four personal survey responses in `submission/entrant-handoff.md`.
4. Upload the four 1,440x900 gallery images.
5. Either leave the optional video field empty or mirror the 76-second MP4
   publicly to YouTube, Vimeo or Youku.
6. Review the Cloud AI category, entrant identity and contact details; submit
   before 2026-08-14 23:00 UTC; then verify the published entry signed out and
   retain its URL and receipt outside the repository.
