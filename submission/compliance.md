# Final submission checklist

Last technical review: 2026-08-05 UTC. The submission deadline is August 14,
2026 at 23:00 UTC.

## Completed in the repository

- [x] One published track is used consistently: **Cloud AI**.
- [x] Repository-level Apache-2.0 license exists and GitHub recognizes it.
- [x] Functional planner, HTTP API, and selected-runtime launcher are included.
- [x] Exact patched-current-runtime fast and memory launch paths are exercised
      end to end on native Arm with source/build/binary/model/service provenance
      bound through separate contracts.
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
- [x] Video script is under three minutes (2m45s; 327 spoken words).
- [x] The final judge package passes clean-checkout native Arm validation in
      GitHub Actions workflow run
      [`30991082053`](https://github.com/Arshgill01/Arm/actions/runs/30991082053):
      468 tests with 20 expected artifact/environment skips, 71 immutable
      evidence hashes, exact planner replay, four gallery assets, the E21/E16
      demo smoke checks, and the 327/390-word ceiling at commit `f12b4a1`.

The demo, favicon, and four 1,440×900 screenshots are first-party assets created
for this repository. They use no third-party imagery, fonts, music, or footage.
All four gallery images were re-rendered from the E9a, E21b, and E16e demo on
August 5 and visually inspected at their final resolution.

## Entrant actions still required

- [x] `Arshgill01/Arm` is public.
- [x] The public HTML evidence report is available without credentials at
      <https://pareto64-arm-evidence.arshgill01.chatgpt.site>.
- [x] Anonymous HTTP access to the source, Apache-2.0 license, and linked E10b
      workflow evidence was verified on August 3, 2026.
- [ ] Confirm personal/team eligibility and appoint the submitting representative.
- [x] Devpost account is registered for the event (live check, July 31, 2026).
- [ ] Join/confirm the Arm Developer Program with an Arm ID.
- [ ] Host the static `demo/` directory at a free public URL.
- [ ] Verify that URL works without credentials and will remain available through
      September 4, 2026.
- [ ] Replace `<ADD PUBLIC DEMO URL>` in `submission/devpost.md`.
- [ ] Record the 2m45s script on the intended native Arm evidence path.
- [ ] Upload the video publicly to YouTube, Vimeo, or Youku.
- [ ] Replace `<ADD PUBLIC VIDEO URL>` in `submission/devpost.md`.
- [ ] Add screenshots from `output/playwright/` to the Devpost gallery.
- [ ] Confirm all required Devpost fields and the **Cloud AI** category.
- [ ] Answer the four entrant-only survey fields about build difficulty,
      missing support, future Arm use, and plans to continue the project using
      the exact prompts and recommended answers in
      [`entrant-handoff.md`](entrant-handoff.md).
- [ ] Review the final text for entrant name/team and contact information.
- [ ] Submit before August 14, 2026 at 23:00 UTC.

## Final verification commands

```bash
python3 scripts/verify_submission.py
python3 -m unittest discover -s tests -v
python3 -m http.server 4174 --directory demo
```

Repository publication, hosting, and account steps require the entrant's
external accounts and are intentionally not automated by this repository. The
ordered final procedure is in [`entrant-handoff.md`](entrant-handoff.md).
