# Repository publication record

Checked: 2026-08-03 UTC.

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
  publication was performed by this audit.

## Completed publication checks

The visibility change was completed after the retained history and audit were
reviewed. The following anonymous checks now pass:

1. the repository root and raw Apache-2.0 license are readable;
2. the current linked workflow run is readable;
3. an anonymous HTTPS clone succeeds with credential helpers disabled; and
4. `gh repo view` reports `PUBLIC`.

The Devpost source field still needs entrant review. Static demo hosting and
public video upload remain separate entrant actions.
