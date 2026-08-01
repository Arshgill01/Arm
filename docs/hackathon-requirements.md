# Hackathon requirements dossier

Last verified: 2026-08-01 UTC. Authoritative source links are collected in
[`source-registry.md`](source-registry.md).

## Event identity and schedule

- Event: **Arm Create: AI Optimization Challenge 2026**.
- Sponsor and administrator: Arm, San Jose, California.
- Format: public, online.
- Published submission deadline: **August 14, 2026, 4:00 PM Pacific Daylight
  Time**, which is **August 14, 2026, 23:00 UTC** and **August 15, 2026, 04:30
  IST**.
- Judging: August 17, 9:00 AM PT through September 4, 4:00 PM PT.
- Winners: on/about September 15, 2026; the exact time conflicts across official
  pages and is not submission-critical.

The rules page controls if another hackathon page conflicts with it.

## Core build requirement

Create, migrate, or optimize an AI solution on Arm architecture and select one
published track: Physical AI, Cloud AI, or Mobile AI. The overview explicitly
asks for clear optimization work and measurable improvements where possible.

Optimization fronts named by the organizer:

1. Model size on disk or in memory.
2. Model quality for a given model size.
3. Model speed: tokens/second, time to first token, or relevant latency.
4. Inference-server speed: throughput, latency, tokens/second, or time to first
   token.
5. Developer experience: tooling, workflow, setup, documentation, usability.
6. Arm-specific optimization in a framework, library, model, or application.

The update sent to the prior Arm challenge also names memory usage, energy
efficiency, deployment workflow, developer productivity, and user experience as
valid optimization areas. Those are useful supporting signals, but the six-item
overview list is the safer primary target.

## Mandatory submission artifacts

- A functional project that installs and runs consistently on its intended
  platform.
- A public source repository with all source, assets, instructions, and an MIT
  or Apache-2.0 license visible at repository level.
- A text description covering features and functionality.
- Project overview: purpose, interest, and why it should win.
- Functionality/output: what it does and the final artifact.
- Step-by-step build, run, and validation instructions for the relevant Arm
  device or Arm64 environment.
- Free, unrestricted judge access to a working site, demo, or test build through
  the end of judging. Private sites must include testing credentials.
- English submission materials or English translations.
- Clear disclosure of significant updates made during the submission period if
  the project existed before it.

The detailed rules say Physical and Cloud submissions require source. They use
ambiguous “Track 1 / Track 2 / Track 3” artifact language elsewhere; this
repository will conservatively provide complete source and proof artifacts for
any selected track.

## Optional but strategically important media

A public demonstration video is optional. If included, it should:

- be under three minutes because judges need not watch beyond that;
- show the project working on the intended device;
- be public on YouTube, Vimeo, or Youku; and
- avoid unlicensed trademarks, music, and copyrighted material.

Because judges may use only the write-up, images, and video, the video and visual
before/after evidence are treated as practical requirements for a competitive
entry.

## Eligibility and ownership

- Individuals must be at least the age of majority where they reside.
- Eligible teams and existing legal organizations may enter; teams/organizations
  appoint one representative.
- The exclusion list includes jurisdictions legally barred from participation or
  receiving prizes and specifically lists Brazil, Quebec, Russia, Crimea, Cuba,
  Iran, and North Korea, plus standard conflict-of-interest exclusions.
- One person may join multiple teams and may also enter individually.
- Multiple submissions are permitted only when unique and substantially
  different.
- The submission must be original, solely owned by the entrant, and respect all
  third-party licenses, SDK/API terms, data rights, privacy rights, and IP.
- Open-source foundations are allowed when the submission enhances and builds on
  their features.
- Existing projects are allowed only if significantly updated after the official
  start, with the update explained.
- All submission IP remains with the entrant; Arm receives the stated judging
  and promotional rights.

## Accounts and platform obligations

The entry instructions include:

- joining the event with a Devpost account;
- joining the Arm Developer Program using an Arm ID; and
- completing all required Devpost submission fields.

The authenticated Devpost account was verified as already registered for this
challenge on July 31, 2026. The current machine cannot prove Arm Developer
Program membership or the entrant's eligibility declarations.

## Judging

Stage one is pass/fail for theme fit and reasonable use of required featured
APIs/SDKs. The event pages do not name one universally required API/SDK, so an
explicit Arm architecture and Arm-optimized runtime/toolchain path is the safest
interpretation.

Stage two totals 100 points:

| Criterion | Points | What evidence should prove it |
| --- | ---: | --- |
| Technological implementation | 40 | Correct, robust software; real Arm execution; strong benchmark methodology; technically sound Arm-specific changes |
| WOW factor | 25 | Immediate live before/after story; a surprising technique or scope; memorable demo |
| Potential impact | 20 | Reusable patches, models, harnesses, migration templates, or learning artifacts |
| User/developer experience | 15 | Fast setup, clear validation, useful output, documentation, automation |

Tie-breaking starts with technological implementation, making verified technical
depth the dominant optimization target.

## Prizes

- Overall winner: USD 3,000 and Arm Community Blog feature.
- Overall runner-up: USD 2,000 and feature.
- Best Physical AI: USD 1,000 and feature.
- Best Cloud AI: USD 1,000 and feature.
- Best Mobile AI: USD 1,000 and feature.

The detailed rules mistakenly call the final category “Edge AI.” The overview
and track page consistently say Mobile AI. See `open-questions.md`.

## Late organizer guidance

The July 17 office-hours recap and July 24 “Strengthen Your Optimization Story”
update remove an important strategic ambiguity: merely running AI on Arm is not
enough. Arm asks entrants to expose the baseline, technical changes, measured
improvement, and why it matters. The organizer explicitly names latency,
throughput, memory, model size, power, deployment time, developer workflow, and
setup complexity as acceptable evidence.

The July 24 update also says judges will look beyond the pitch to the actual
implementation and artifacts. Reusable optimized models, scripts, tools,
migration notes, templates, benchmarks, and lessons are specifically encouraged.

Rechecking the live update on August 1 confirms the organizer's requested
evaluation chain: make the baseline, technical change, measured improvement,
and practical meaning easy to find in the README. Pareto64's judge summary now
uses that exact structure and keeps rejected optimizations in the same map.

An official July 31 session reviews concepts and the judging criteria at 09:00
PDT (16:00 UTC), followed by judge office hours on August 3 at 10:00 PDT (17:00
UTC) in the Arm Developer Program Discord. These are the best channels to resolve
the rule defects in `open-questions.md`.

## Conservative compliance checklist

- [ ] User confirms eligibility and chosen entrant/team representative.
- [x] Authenticated user is registered for the Devpost event (live check,
      2026-07-31).
- [ ] User joins/confirms Arm Developer Program account.
- [x] One and only one published track is selected on the submission: Cloud AI.
- [x] Work performed during the submission period is identified by commits and
      a changelog.
- [x] Public GitHub repository exists.
- [x] Apache-2.0 license is present in the local project.
- [x] GitHub detects the repository license as Apache-2.0 after push.
- [x] All dependencies, models, datasets, and generated assets have provenance
      and compatible rights.
- [x] Clean-checkout setup/run/validation succeeds on the intended Arm target
      ([native run `30677849517`](https://github.com/Arshgill01/Arm/actions/runs/30677849517)).
- [x] Repeated before/after results and raw evidence are published.
- [x] Correctness or quality guardrails show optimization did not silently break
      the workload.
- [ ] Working demo remains freely accessible through September 4, 2026.
- [x] English Devpost write-up is complete.
- [ ] Public demo video is under three minutes and shows the intended device.
- [ ] Submission is finalized before August 14, 2026, 23:00 UTC.
