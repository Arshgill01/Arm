# Repository publication record

Checked: 2026-08-06 UTC.

The official rules require a public source repository. GitHub reports
`Arshgill01/Arm` as **public**. On August 3, 2026, unauthenticated HTTP checks
returned 200 for the repository root, raw Apache-2.0 license, and current E10b
workflow evidence. A fresh HTTPS clone with credential helpers disabled also
succeeded and contained the license. Repository visibility is no longer a
pre-submission blocker.

## Pre-publication audit

- Pinned Gitleaks `v8.28.0` scanned the complete history. Its four initial
  findings were SHA-256 values in retained evidence manifests, not credentials.
  `.gitleaksignore` permits only those exact fingerprints; the resulting
  full-history scan passes at this checkpoint. Reproduce it with:

  ```bash
  go run github.com/zricethezav/gitleaks/v8@v8.28.0 \
    --redact --no-banner --no-color --verbose git .
  ```
- No tracked filename matched the audit's credential/private-key patterns.
- The Git object store reported 14.77 MiB of loose objects and no garbage. The
  largest blob reachable from history is 617,514 bytes, so there is no large
  repository artifact blocker.
- Publishing exposes the full commit history, author identity and email, and
  the `Signed-off-by` identity in the retained unpublished patch series. The
  entrant must confirm that those identities and all retained evidence are
  intended for public release.
- No static-site hosting, Devpost submission, video upload, or upstream patch
  publication was performed by the original repository audit. Hosting and the
  optional video were completed separately on August 6; Devpost submission and
  upstream patch publication were not.

## Completed publication checks

The visibility change was completed after the retained history and audit were
reviewed. The following anonymous checks now pass:

1. the repository root and raw Apache-2.0 license are readable;
2. the current linked workflow run is readable;
3. an anonymous HTTPS clone succeeds with credential helpers disabled; and
4. `gh repo view` reports `PUBLIC`.

The Devpost source field still needs entrant review. The public demo and direct
MP4 recording are complete; adding the four gallery images and completing the
entrant-only fields remain entrant actions.

## Public evidence report

The evidence-ledger site is published at
[`https://pareto64-arm-evidence.arshgill01.chatgpt.site`](https://pareto64-arm-evidence.arshgill01.chatgpt.site).
Sites reports public access. Unauthenticated HTTP checks on August 6 returned
200 for the report, its interactive
[`/demo/index.html`](https://pareto64-arm-evidence.arshgill01.chatgpt.site/demo/index.html)
route, and the final E22 fixed-memory density evidence. The raw E22b/E22c
bundles and 76-second MP4 walkthrough are public in the
[`e22-axion-evidence-20260806`](https://github.com/Arshgill01/Arm/releases/tag/e22-axion-evidence-20260806)
release. These are public evidence assets, not a Devpost submission or a
published upstream patch.
