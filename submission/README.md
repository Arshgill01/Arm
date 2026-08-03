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
policy, final E5b-versus-E7c service comparison, and cache-generalization
boundary.

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

The final E9a–E9e native Arm clean-checkout run is
[`30775565670`](https://github.com/Arshgill01/Arm/actions/runs/30775565670),
covering 163 tests, 49 immutable evidence hashes, planner replay, and the demo
smoke test at commit `70ceae6`.

The GitHub repository is currently private and must pass the explicit
[`publication-handoff.md`](publication-handoff.md) gate before submission. It
also does not publish or configure a hosted site automatically. The entrant must
put the static `demo/` directory at a public URL that remains available through
September 4, 2026, upload the video, and replace the URL placeholders in
`devpost.md` and `compliance.md`.
