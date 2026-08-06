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
[`../output/playwright/`](../output/playwright/): final Axion density overview,
six-plane product deployment, interactive policy/refusal behavior, and the E22c
density/readiness boundary.

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

The native Arm
[`submission-validation.yml`](https://github.com/Arshgill01/Arm/actions/workflows/submission-validation.yml)
workflow validates the current package from a clean checkout. The local suite
currently runs 500 tests with two toolchain-gated skips; the verifier pins 76
immutable evidence files through E22c, exact planner replay, all four gallery
assets, the dependency-free demo, publication URLs, and the enforced 296/390-
word video-script ceiling.

The GitHub repository, the
[HTML evidence report](https://pareto64-arm-evidence.arshgill01.chatgpt.site),
the hosted
[interactive demo](https://pareto64-arm-evidence.arshgill01.chatgpt.site/demo/index.html),
the [raw E22 release](https://github.com/Arshgill01/Arm/releases/tag/e22-axion-evidence-20260806),
and the [76-second walkthrough](https://github.com/Arshgill01/Arm/releases/download/e22-axion-evidence-20260806/pareto64-demo.mp4)
are public, and anonymous HTTP checks pass. Entrant identity, eligibility,
survey answers, gallery upload, category review, and final Devpost submission
remain outside the repository.
