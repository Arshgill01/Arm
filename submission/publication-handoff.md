# Repository publication handoff

Checked: 2026-08-03 UTC.

The official rules require a public source repository. GitHub currently reports
`Arshgill01/Arm` as **private**. The repository-level Apache-2.0 license is
detected, but the source, workflow runs, and evidence links are not anonymously
accessible until the entrant changes visibility. This is a mandatory
pre-submission blocker, not a completed requirement.

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
- No repository visibility, hosting, Devpost, video, or upstream-publication
  action was taken by this audit.

## Entrant publication gate

Before changing visibility:

1. Review the complete history and the identities noted above.
2. Confirm that the retained manifests, reports, logs, patches, and screenshots
   are intended to be public.
3. Change repository visibility only through an authenticated GitHub action
   after accepting GitHub's visibility-change warnings.

After changing visibility, verify from an unauthenticated browser or clean
anonymous environment that:

1. the repository root, Apache-2.0 license, README, and source are readable;
2. the workflow-run links in `submission/evidence.md` are readable;
3. an anonymous clone succeeds; and
4. the Devpost source URL points to the public repository.

Only after those checks pass should the public-repository items in
`submission/compliance.md` and `docs/hackathon-requirements.md` be marked
complete. Static demo hosting and public video upload remain separate entrant
actions.
