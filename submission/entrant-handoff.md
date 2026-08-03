# Entrant submission handoff

Checked: 2026-08-03 UTC. This is a preparation packet, not authorization to
publish or submit anything.

## Stop gates

Do not submit while any of these are true:

- `Arshgill01/Arm` is private or cannot be cloned anonymously;
- the Apache-2.0 license, source, or linked workflow evidence is unavailable to
  an unauthenticated judge;
- `<ADD PUBLIC DEMO URL>` remains in `devpost.md`;
- `<ADD PUBLIC VIDEO URL>` remains instead of being replaced or removed;
- a supplied demo or video URL requires credentials;
- the selected category is not **Cloud AI**; or
- the entrant has not confirmed eligibility, team representation, and Arm
  Developer Program membership.

The public repository procedure and identity review are in
[`publication-handoff.md`](publication-handoff.md).

## Paste-ready identity

- **Project name:** Pareto64
- **Tagline:** Quality-constrained Arm64 inference: measure every tradeoff,
  reject broken speedups, launch only the proven deployment.
- **Track/category:** Cloud AI
- **Source:** <https://github.com/Arshgill01/Arm>
- **Suggested technology tags:** Python, Arm64, llama.cpp, KleidiAI, GGUF,
  Ministral 3, CMake, GitHub Actions, OpenAI-compatible API
- **Long-form project text:** [`devpost.md`](devpost.md), after replacing the
  demo URL and either replacing or removing the optional video URL

The video is optional under the official rules. If no public video is ready,
remove the placeholder instead of submitting placeholder text. The static demo
and source remain mandatory judge-access paths under this package's conservative
interpretation.

## Gallery upload order

Upload the four 1,440×900 PNGs in this order so the compounded result appears
before supporting detail:

1. [`pareto64-overview.png`](../output/playwright/pareto64-overview.png) —
   quality-first hook and 1.717× final-service result.
2. [`pareto64-final-service.png`](../output/playwright/pareto64-final-service.png)
   — exact E5b-versus-E7c recipes and same-job metrics.
3. [`pareto64-policy-lab.png`](../output/playwright/pareto64-policy-lab.png) —
   measured deployment-envelope routing and refusal behavior.
4. [`pareto64-serving-boundary.png`](../output/playwright/pareto64-serving-boundary.png)
   — negative cache-generalization boundary.

Suggested first-image caption: **Pareto64 rejects a faster model that misses
quality, then launches only an evidence-bound Arm64 service. The exact final
service delivers 1.7168× throughput with 41.5% lower median latency in a
same-job native Neoverse N2 comparison.**

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
