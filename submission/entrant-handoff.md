# Entrant submission handoff

Checked: 2026-08-06 UTC. This is a preparation packet, not authorization to
publish or submit anything.

## Stop gates

Do not submit while any of these are true:

- `Arshgill01/Arm` is private or cannot be cloned anonymously;
- the Apache-2.0 license, source, or linked workflow evidence is unavailable to
  an unauthenticated judge;
- an `<ADD PUBLIC ...>` placeholder remains in `devpost.md`;
- a supplied demo or video URL requires credentials;
- the selected category is not **Cloud AI**; or
- the entrant has not confirmed eligibility, team representation, and Arm
  Developer Program membership.

The public repository procedure and identity review are in
[`publication-handoff.md`](publication-handoff.md).

## Paste-ready identity

- **Project name:** Pareto64
- **Tagline:** Proof-carrying Arm64 inference: eight exact shared workers where
  the private representation could sustain six.
- **Track/category:** Cloud AI
- **Source:** <https://github.com/Arshgill01/Arm>
- **Suggested technology tags:** Python, Arm64, llama.cpp, KleidiAI, GGUF,
  Ministral 3, CMake, GitHub Actions, OpenAI-compatible API
- **Long-form project text:** [`devpost.md`](devpost.md)

The video is optional under the official rules. A 76-second, silent annotated
walkthrough is public as a direct MP4 asset, and the interactive demo and source
are available without credentials. The rules require a video entered in the
optional Devpost field to be publicly hosted on YouTube, Vimeo, or Youku.
Therefore either mirror the same file to one of those services or leave that
optional field empty. Keep the direct MP4 labeled as supplemental evidence in
the project text; do not present it as a compliant video-field URL.

## Gallery upload order

Upload the four 1,440×900 PNGs in this order so the repeated density result
appears before supporting detail:

1. [`pareto64-overview.png`](../output/playwright/pareto64-overview.png) —
   final Axion headline, 1.3525× fixed-memory throughput-density result, and
   the failed readiness gate.
2. [`pareto64-final-service.png`](../output/playwright/pareto64-final-service.png)
   — the six product planes from policy through receipt, plus E22a's exact
   one-command deployment preflight.
3. [`pareto64-policy-lab.png`](../output/playwright/pareto64-policy-lab.png) —
   measured deployment-envelope routing and refusal behavior.
4. [`pareto64-serving-boundary.png`](../output/playwright/pareto64-serving-boundary.png)
   — E22c normal-6 versus shared-8 distributions, 59.43% lower summed PSS, and
   the 2.0817× readiness boundary.

Suggested first-image caption: **On one 16.72 GB Google Axion host, Pareto64's
verified read-only Arm-packed representation served eight exact workers where
the private representation sustained six: 1.3525× median aggregate throughput
and 59.43% lower summed PSS across 1,680 exact requests. Readiness was 2.0817×
and failed its frozen ≤2.0 gate, so the claim stops at steady-state density.**

## Entrant survey choices to confirm

The unpublished [project gallery](https://arm-ai-optimization-challenge.devpost.com/project-gallery)
exposed these exact custom prompts and options on August 3. The selections below
are evidence-backed recommendations, not answers supplied on the entrant's
behalf.

### What was the hardest part of building or optimizing your project? Select all that apply

Recommended selections:

- Finding compatible hardware or cloud instances
- Measuring performance
- Improving inference server performance
- Debugging runtime or compatibility issues

These map directly to ephemeral Arm runner variance, the balanced measurement
harnesses, the E5/E7 service work, and the retained E6/E9 compatibility
failures. Add other options only if they reflect the entrant's experience.

### What would have made it easier to complete your project? Select all that apply.

Recommended selections:

- More Arm-specific optimization guidance
- More benchmarking examples
- Easier access to Arm-based hardware or cloud instances
- Better documentation

### Did this challenge change your likelihood of building on Arm in the future?

Suggested personal answer to confirm: **Yes, significantly more likely**.

### How likely are you to continue developing, optimizing, or deploying this project after the challenge?

Suggested personal answer to confirm: **Very likely**.

## Final anonymous review

Use a signed-out browser or clean anonymous environment and verify:

1. repository root, source, license, README, and workflow-run links;
2. interactive demo load, all controls, and mobile/desktop layout;
3. video playback, public visibility, and duration under three minutes if used;
4. all four gallery images at full resolution;
5. no `<ADD ...>` placeholder remains in the submitted text;
6. project title, tagline, source URL, and Cloud AI category;
7. entrant/team identity and contact information; and
8. final submission before **2026-08-14 23:00 UTC**
   (**2026-08-15 04:30 IST**).

After submission, open the published entry once more while signed out and retain
the final entry URL and confirmation receipt outside the repository.
