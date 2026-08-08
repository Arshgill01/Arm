# E27 Arm long-context Flash Attention pass

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
  `codex/e27-arm-flash-attention` from `origin/main`. Never reuse the merged E24
  feature branch.

## Objective

Reduce time to first token for medium and long prompts through an Arm-specific
CPU Flash Attention kernel/dataflow change.

The artifact must improve the fused attention implementation itself. Merely
enabling llama.cpp's existing `--flash-attn` mode is not new work.

## Starting facts

- Start from current `origin/main`, which contains E23/E24 through merged PR #1
  (`1c830db` at plan creation).
- Flash Attention owned 36.52% of `pp512` cycles after E23 and 75.86% of the
  retained `pp4096` profile. It is only about 1% of ordinary decode.
- The old E5i auto-versus-off service ablation produced 1.0322x throughput and
  a p95 regression. It tested an existing toggle, not a new kernel.
- The prior 14.5K-token E17b service contract timed out. Do not repeat that
  oversized workflow as the first experiment.

## Pass

1. Profile cumulative E24 at `pp512`, `pp2048` and `pp4096`. Bind the exact
   Flash Attention path, K/V types, tile selection, shapes, PMU shares and
   whole-model ceilings.
2. Build a direct Flash Attention correctness/timing harness for the selected
   head dimensions and context lengths, including the existing reference and
   tiled paths.
3. Inspect the current generic tiled implementation and its Arm SIMD helpers.
   Rank the cost of K/V conversion and packing, QK work, online softmax, V
   accumulation, tile geometry and thread partitioning.
4. Implement one AArch64-specialized NEON/SVE2 path at the measured bottleneck.
   Keep the exact mechanism profile-led; do not restrict the pass to compiler
   flags or generic tile constants.
5. Prove real inference dispatches to the new path and retains the generic
   fallback for unsupported types, vector lengths and shapes.
6. Validate attention output against the reference before performance. Then
   run reverse-balanced whole-model A/B tests with identical prompts, batches,
   K/V policy, cores and affinity.
7. Preserve E23 prefill-kernel and E24 decode gains. `tg128` is a regression
   guard, not this pass's headline.
8. If one narrow source change cannot clear the direct gate, try one different
   measured Flash Attention stage. Do not broaden into unrelated attention
   graph work.
9. After a material primary result, test another model/head shape and a second
   Arm CPU.
10. Produce a current-upstream patch and a side-by-side long-prompt
    time-to-first-token demo.

## Gates

- Direct admission: at least `1.20x` on a controlling medium/long-context
  attention shape.
- Promotion: at least `1.10x` whole-model at `pp2048` or `1.15x` at `pp4096`,
  with no material `pp512` or decode regression.
- Target: an observable same-request time-to-first-token reduction, not a
  throughput result created by concurrency or caching.
- Same model, prompt tokens, quality policy, K/V representation, CPU and core
  budget.
- Numerical tolerance must be declared before timing; deterministic generated
  output and a bounded quality check are required after integration.

## Parallel-worktree boundary

- Use the `e27` prefix for experiments, workflows, raw results and reports.
- Do not depend on E25 or E26 and do not cherry-pick them while this pass runs.
- Keep changes inside Flash Attention/Arm SIMD dispatch and E27-owned patch
  files. Do not tune Q4_K/Q6_K repack kernels or FFN graph fusion.
- Do not edit shared README, submission, strategy, index or progress files.
- Store parallel patch artifacts under `patches/llama.cpp/e27/`; do not assign
  the next number in a shared patch series.

## Autonomous GitHub delivery

The executing agent owns delivery; do not hand commit, push, PR or merge work
back to the user.

1. Make an initial checkpoint containing this brief and the frozen E27
   contract. Commit only E27-owned files.
2. Invoke the `github:yeet` workflow to push the named branch and open a draft
   PR against `main`. Use an `E27:` title and keep the PR updated while working.
3. Use only E27-prefixed workflows and artifact paths. Never edit or stage the
   user's unrelated files from another checkout.
4. Make logical checkpoint commits for profiling, implementation and the final
   result. Never commit credentials, models, build trees or unbounded raw data.
5. Before completing the PR, run the pass-specific native Arm validation,
   `python3 -m unittest discover -s tests -q`,
   `python3 scripts/verify_submission.py`, and `git diff --check`.
6. Keep the PR draft until the E25 and E26 PRs from their named branches are
   merged. Continue technical work while waiting; do not merge out of order.
7. After E26 merges, fetch `origin/main`, merge it into this branch without
   rewriting published history, resolve any in-scope conflict, and rerun all
   affected validation against the combined tree.
8. Remove or disable rejected production code even when the negative report
   and harness are retained. State the result and limits plainly in the PR.
9. Mark the PR ready only when required native runs succeeded, resources were
   deleted, the diff is scoped and the branch contains current `origin/main`.
10. The repository has no protected-branch or automatic-merge safety net.
    Check named workflow runs explicitly; an empty `gh pr checks` result is not
    a pass.
11. Merge the ready PR with a merge commit using `gh`, then verify the PR state
    is `MERGED` and `origin/main` contains its merge commit. Do not ask the user
    to click Merge.

E27 is merge-queue position 3. E26's terminal merge is its integration gate.

## Resources and finish

Paid resources for this pass have a hard USD 12 ceiling. Every instance must
have a six-hour-or-shorter automatic deletion rule; explicitly delete it and
verify instance and disk absence at the end.

Finish with the Arm source patch, direct harness, execution proof, raw matched
results, bounded report, current-upstream validation and live long-prompt demo.
Do not stop after profiling or direct-kernel timing. Completion includes the
verified GitHub merge described above.
