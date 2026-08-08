# E25 Arm Q4_K decode-layout pass

Status: ready for execution in an isolated worktree. No implementation has
started.

## Launch contract

- Launch this task from the Codex app with **Worktree** selected and `main` as
  the starting branch. Do not run it in the shared Local checkout.
- Attach or point the task to this file even if it is not yet tracked on
  `main`.
- Fetch `origin/main` before editing and require merge commit
  `1c830dbf6eeb6e9261cbe2613a22ea89b733ea22` to be its ancestor.
- Require a clean worktree, then create branch
  `codex/e25-q4-k-decode-layout` from `origin/main`. Never reuse the merged E24
  feature branch.

## Objective

Make the same Q4_K model generate tokens at least 10% faster than the completed
E24 baseline on the same Arm CPU and four-core budget.

The distinctive artifact is a decode-oriented Q4_K packed representation and
AArch64 GEMV path, not another instruction-order cleanup of the existing 8x8
kernel.

## Starting facts

- Start from current `origin/main`, which contains E23/E24 through merged PR #1
  (`1c830db` at plan creation).
- E24's baseline already includes the retained E23 Q4_K prefill patch and E24
  Q6_K decode patch.
- Before E24, `ggml_gemv_q4_K_8x8_q8_K` owned 55.78% of `tg128` cycles on
  Axion and 48.16% of the live request.
- The corrected I8MM rewrite regressed, forced unrolling reached only
  1.0385--1.0417x directly, and the shared scale decoder regressed decode.
  Do not repeat those candidates.

## Pass

1. Re-profile the cumulative E24 baseline and bind the exact Q4_K share,
   shapes, dispatch, instruction mix and memory traffic.
2. Extend the existing direct Q4_K harness to compare packed formats as well
   as inner loops.
3. Prototype a decode-specific representation that moves repeated unpacking,
   scale/min preparation or column rearrangement out of token generation.
4. Write the matching AArch64 NEON/I8MM GEMV kernel. Keep the design space open:
   layout, tile shape, metadata placement and reduction schedule may all move.
5. Prove the real model selects the new representation and kernel. Measure
   representation size, preparation time and readiness impact.
6. Require reference-kernel correctness before timing. Then run matched direct
   shapes and reverse-balanced whole-model `tg128` A/B tests.
7. Preserve E23 prefill and E24 Q6_K results as regression guards.
8. If the first layout family misses the direct gate, try one materially
   different layout/dataflow family. Do not spend the pass polishing assembly
   noise.
9. After a primary win, test Q4_K_S, Qwen Q4_K_M and a second Arm CPU.
10. Produce a current-upstream patch and a streamed baseline/candidate demo.

## Gates

- Target: at least `1.10x` whole-model `tg128` over E24; `1.15x` remains the
  desired visible result.
- Direct admission: at least `1.20x` on both principal decode shapes, or a
  measured Amdahl projection above `1.08x` whole-model.
- No prompt caching, model swap, extra cores, speculative decoding or relaxed
  output policy.
- No hidden second full model copy. Any packed-size or startup tradeoff must be
  measured and exposed.
- A smaller positive patch may be retained, but it does not make this pass a
  success.

## Parallel-worktree boundary

- Use the `e25` prefix for experiments, workflows, raw results and reports.
- Do not depend on E26 or E27 and do not cherry-pick them while this pass runs.
- Do not edit `README.md`, submission files, strategy documents,
  `experiments/README.md`, `patches/README.md` or shared progress logs.
- Keep source work as E25-owned patch files so later integration can compose
  the three results deliberately.
- Store parallel patch artifacts under `patches/llama.cpp/e25/`; do not assign
  the next number in a shared patch series.

## Autonomous GitHub delivery

The executing agent owns delivery; do not hand commit, push, PR or merge work
back to the user.

1. Make an initial checkpoint containing this brief and the frozen E25
   contract. Commit only E25-owned files.
2. Invoke the `github:yeet` workflow to push the named branch and open a draft
   PR against `main`. Use an `E25:` title and keep the PR updated while working.
3. Use only E25-prefixed workflows and artifact paths. Never edit or stage the
   user's unrelated files from another checkout.
4. Make logical checkpoint commits for profiling, implementation and the final
   result. Never commit credentials, models, build trees or unbounded raw data.
5. Before completing the PR, run the pass-specific native Arm validation,
   `python3 -m unittest discover -s tests -q`,
   `python3 scripts/verify_submission.py`, and `git diff --check`.
6. Fetch `origin/main`, merge it into this branch without rewriting published
   history, resolve any in-scope conflict, and rerun affected validation.
7. Remove or disable rejected production code even when the negative report
   and harness are retained. State the result and limits plainly in the PR.
8. Mark the PR ready only when required native runs succeeded, resources were
   deleted, the diff is scoped and the branch contains current `origin/main`.
9. The repository has no protected-branch or automatic-merge safety net. Check
   the named workflow runs explicitly; an empty `gh pr checks` result is not a
   pass.
10. Merge the ready PR with a merge commit using `gh`, then verify the PR state
    is `MERGED` and `origin/main` contains its merge commit. Do not ask the user
    to click Merge.

E25 is merge-queue position 1. It may merge as soon as its own gates pass.

## Resources and finish

Paid resources for this pass have a hard USD 12 ceiling. Every instance must
have a six-hour-or-shorter automatic deletion rule; explicitly delete it and
verify instance and disk absence at the end.

Finish with the source patch, reproducer, correctness output, raw matched
measurements, bounded report, current-upstream check and live decode demo. Do
not stop after profiling or a microbenchmark. Completion includes the verified
GitHub merge described above.
