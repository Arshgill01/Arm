# Pareto64 submission package

This directory converts the repository's native Arm evidence into the fields
and media needed for the Arm Create: AI Optimization Challenge 2026 entry.

- [`devpost.md`](devpost.md): paste-ready English project description.
- [`evidence.md`](evidence.md): compact claim-to-run index with immutable hashes.
- [`demo-script.md`](demo-script.md): public video script under three minutes.
- [`compliance.md`](compliance.md): final technical and account checklist.
- [`publication-handoff.md`](publication-handoff.md): mandatory repository
  visibility and anonymous-access gate.
- [`entrant-handoff.md`](entrant-handoff.md): exact field, gallery, survey, and
  final signed-out review packet.

The ready-to-upload 1,440×900 gallery assets are in
[`../output/playwright/`](../output/playwright/): project overview, interactive
policy, the final service plus online-cache lifecycle, and the persistent
Arm-packed-weight lifecycle.

The interactive static demo is in [`../demo/index.html`](../demo/index.html).
From the repository root:

```bash
python3 -m http.server 4174 --directory demo
```

Then open <http://127.0.0.1:4174>. Run the complete no-dependency package check
with:

```bash
python3 scripts/verify_submission.py
python3 -m unittest discover -s tests -v
```

The latest native Arm judge-package clean-checkout run is
[`30991082053`](https://github.com/Arshgill01/Arm/actions/runs/30991082053),
covering 468 tests (20 expected artifact/environment skips), 71 immutable
evidence hashes through E16e and E21b, exact planner replay, and the dependency-
free demo smoke test at commit `f12b4a1`. It also validates all four gallery
assets and the enforced 327/390-word video-script ceiling.

The GitHub repository and the
[HTML evidence report](https://pareto64-arm-evidence.arshgill01.chatgpt.site)
are public, and anonymous HTTP checks pass. The interactive static `demo/`
directory is not yet hosted. The entrant must put it at a public URL that
remains available through September 4, 2026, upload or omit the optional video,
and resolve the URL placeholders in `devpost.md` and `compliance.md`.
