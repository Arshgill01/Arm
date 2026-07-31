# Final submission checklist

Last technical review: 2026-07-31 UTC. The submission deadline is August 14,
2026 at 23:00 UTC.

## Completed in the repository

- [x] One published track is used consistently: **Cloud AI**.
- [x] Public source repository exists.
- [x] Repository-level Apache-2.0 license exists and GitHub recognizes it.
- [x] Functional planner, HTTP API, and selected-runtime launcher are included.
- [x] Step-by-step local verification and native reproduction commands exist.
- [x] Model, runtime, task, patch, and source provenance is recorded.
- [x] Selected model and GGUF producer are Apache-2.0 at immutable revisions.
- [x] Native Arm before/after and quality results are repeated and retained.
- [x] Quality/correctness gates reject regressions and near-misses.
- [x] Significant challenge-period updates are disclosed in `CHANGELOG.md` and
      the Devpost draft.
- [x] English project overview, functionality, implementation, challenges,
      accomplishments, learning, and future work are drafted.
- [x] Interactive no-dependency demo is implemented and browser-tested.
- [x] Video script is under three minutes (2m50s).
- [x] Clean-checkout native Arm validation passes in public workflow run
      [`30663277762`](https://github.com/Arshgill01/Arm/actions/runs/30663277762).

The demo, favicon, and screenshots are first-party assets created for this
repository. They use no third-party imagery, fonts, music, or footage.

## Entrant actions still required

- [ ] Confirm personal/team eligibility and appoint the submitting representative.
- [ ] Join the Devpost event with the submission account.
- [ ] Join/confirm the Arm Developer Program with an Arm ID.
- [ ] Host the static `demo/` directory at a free public URL.
- [ ] Verify that URL works without credentials and will remain available through
      September 4, 2026.
- [ ] Replace `<ADD PUBLIC DEMO URL>` in `submission/devpost.md`.
- [ ] Record the 2m50s script on the intended native Arm evidence path.
- [ ] Upload the video publicly to YouTube, Vimeo, or Youku.
- [ ] Replace `<ADD PUBLIC VIDEO URL>` in `submission/devpost.md`.
- [ ] Add screenshots from `output/playwright/` to the Devpost gallery.
- [ ] Confirm all required Devpost fields and the **Cloud AI** category.
- [ ] Review the final text for entrant name/team and contact information.
- [ ] Submit before August 14, 2026 at 23:00 UTC.

## Final verification commands

```bash
python3 scripts/verify_submission.py
python3 -m unittest discover -s tests -v
python3 -m http.server 4174 --directory demo
```

The hosting and account steps require the entrant's external accounts and are
intentionally not automated by this repository.
