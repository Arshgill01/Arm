# Official-page contradictions and open questions

Last verified: 2026-07-31 UTC.

These are evidence gaps, not permission to ignore a requirement.

## Organizer clarification candidates

1. **Track artifact language conflicts with published track names.** The rules
   call Track 1 “Optimization output,” Track 2 “Migration/adoption value,” and
   Track 3 “Scale + learning completion,” while the dedicated track page defines
   Track 1 Physical AI, Track 2 Cloud AI, and Track 3 Mobile AI. Does that artifact
   taxonomy actually map to the published tracks?
2. **Mobile versus Edge prize name.** The overview offers Best Mobile AI, but the
   detailed prize table says Best in Track: Edge AI.
3. **Required API/SDK is unnamed.** Stage one mentions reasonable application of
   “required APIs/SDKs featured in the Hackathon,” while the public overview and
   track page present tools as examples/learning paths rather than one mandatory
   SDK. Is execution on Arm architecture enough, or must an Arm library/tool be
   integrated?
4. **Start dates conflict.** The schedule page says submissions began June 4,
   while the rules say registration/submission began June 10. For pre-existing
   project updates, we use the conservative June 10 date.
5. **Winner announcement time conflicts.** Rules say on/about September 15 at
   2:00 PM PT; schedule says September 15 at 10:00 AM PT.
6. **Source requirement wording conflicts.** The overview says the repository and
   open-source license are mandatory, then says Track 3 needs proof artifacts.
   We will publish both full source and proof artifacts regardless of track.
7. **Performix scope.** The overview says developers “can” use Arm Performix. Is
   it optional for final benchmark proof, and what devices/metrics are supported
   during this event?
8. **Multiple-prize eligibility.** The rules say a project can win only one
   “grand prize” and up to one blog-post prize, but the listed overall and track
   awards do not use that taxonomy consistently. Can one project win both an
   overall and a best-in-track award?
9. **Unfilled eligibility template.** The eligibility section includes an
   unfinished “Other” placeholder. Confirm that it imposes no additional tool or
   country restriction.

## Working assumptions until clarified

- Select exactly one of Physical, Cloud, or Mobile AI.
- Treat June 10 as the earliest eligible significant-update date.
- Publish all source, setup instructions, and raw benchmark proof regardless of
  selected track.
- Use at least one explicitly Arm-aware runtime, library, compiler setting, or
  upstream code change and show the Arm device/environment.
- Treat Performix as optional until its access and scope are verified.

## Confirmed organizer clarification

Arm Staff Developer Evangelist Avin Zarlez answered in the event discussion that
optimizations for Apple Silicon count. An Apple Silicon Mac is therefore a valid
Mobile AI target even though the track examples emphasize Android, iOS, and
Windows on Arm.
