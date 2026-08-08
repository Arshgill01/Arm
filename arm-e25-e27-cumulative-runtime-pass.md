# E28 cumulative Arm runtime integration pass

Status: ready for execution in an isolated worktree. No E28 implementation or
paid run has started.

## Launch contract

- Launch this task from the Codex app with **Worktree** selected and `main` as
  the starting branch. Do not run it in the shared Local checkout.
- Attach or point the task to this file even if it is not yet tracked on
  `main`.
- Fetch `origin/main` before editing and require merge commit
  `d06b28b4a4eb7743804cf8981e1249da9c15d6d5` to be its ancestor.
- Require a clean worktree, then create branch
  `codex/e28-cumulative-arm-runtime` from `origin/main`.
- Read the repository `AGENTS.md` and preserve every raw command, environment,
  model hash and result needed to reproduce a claim.

## Objective

Produce and validate one current-upstream llama.cpp runtime containing the
accepted E24 Q6_K, E25 Q4_K decoded-metadata and E27 Flash Attention Arm paths.
Measure their interaction directly and publish one honest stock-versus-combined
result. Do not multiply ratios from separate experiments.

E26 is a retained negative result and must not enter the runtime.

## Starting facts

- E25 and E27 were measured as sibling variants against the cumulative E24
  baseline; no measured binary currently contains both.
- On four Axion V2 cores, E25 improved Ministral Q4_K_M `tg128` from
  `26.102599` to `29.111489` tok/s (`1.115272x`) while `pp512` was
  `0.985378x`. Its sidecar adds `11.11%` of packed Q4 weight bytes and increased
  median process RSS by `159,744 KiB`.
- On the same model and cores, E27 improved `pp512`, `pp2048` and `pp4096` by
  `1.623492x`, `2.910144x` and `4.086359x`; `tg128` was `0.999073x`. The live
  8K-prompt TTFT ratio was `5.316355x` with byte-identical output.
- E27's post-patch `pp2048` profile still assigns `59.01%` to Q4_K GEMM,
  `17.51%` to Flash Attention and `12.04%` to Q6_K GEMM, but that profile does
  not contain E25.
- `patches/llama.cpp/current/` currently contains E24 and E25. E27 remains in
  `patches/llama.cpp/e27/` and has not been promoted into a tested combined
  current-upstream series.

## Frozen experiment

1. Create `experiments/e28_contract.json` before timing. Pin source commits,
   patch hashes, model bytes, compiler, flags, CPU features, cores `0-3`, four
   threads, batch/ubatch, prompts, seeds, repetitions, execution order and all
   gates below.
2. Reconstruct the pinned `b10216` cumulative E24 base and build this 2x2
   matrix from clean source trees:

   - `A`: E24 base (including its retained E23 dependency)
   - `B`: `A + E25`
   - `C`: `A + E27`
   - `D`: `A + E25 + E27`

3. Prove patch application, build features and real-model dispatch separately
   for E24 Q6_K, E25 Q4_K decoded metadata and E27's SVE-build NEON Flash
   Attention GEMM. A compiled symbol alone is not dispatch proof.
4. Run the existing Q4_K GEMV/GEMM, Q6_K and Flash Attention references before
   performance. Extend Flash Attention correctness to the actual timed
   `q512/kv512`, `q512/kv2048` and `q512/kv4096` shapes. Keep its predeclared
   maximum NMSE at `5e-4`.
5. Isolate semantic effects with the matrix: `A` versus `C` and `B` versus `D`
   must produce byte-identical deterministic long-prompt output. E25 may change
   greedy tokens, so `A` versus `B` and `C` versus `D` require the frozen
   30-task suite, two stable repetitions, no loss from the stock score, and a
   fixed-corpus perplexity delta no worse than `0.1%`. Do not use kernel NMSE as
   the only full-model quality argument.
6. Run reverse-balanced fresh-process measurements for all four variants on
   `pp512`, `pp2048`, `pp4096` and `tg128`. Use six processes per variant per
   case and identical model, prompt, Flash Attention, K/V type, affinity and
   output policy.
7. Treat the following as composition gates, not guaranteed results:

   - `B/A tg128 >= 1.10`
   - `D/C tg128 >= 1.10`
   - `C/A pp512 >= 1.50`, `pp2048 >= 2.70`, `pp4096 >= 3.75`
   - `D/B pp512 >= 1.50`, `pp2048 >= 2.70`, `pp4096 >= 3.75`
   - every non-target workload ratio must be at least `0.98`

8. Report `D/A` from its matched samples as the cumulative result. Never infer
   it by multiplying E25 and E27 summaries. Include confidence intervals,
   dispersion, readiness time, peak RSS and sidecar bytes.
9. Repeat stock-versus-combined `pp512`, `pp2048`, `pp4096`, `tg128` and direct
   correctness on a second Arm generation and the frozen Qwen Q4_K_M model.
   This is a portability result; do not silently substitute it for the primary
   model.
10. Run the same 8K live TTFT demo for `A`, `B`, `C` and `D`. Record prompt
    tokens, generated text, wall time, first-token time, CPU/core policy and
    complete commands.

## Current-upstream deliverable

1. Fetch llama.cpp immediately before the lane and pin the exact tested master
   commit. Build stock and combined trees from that same commit.
2. Audit whether E23 is already upstream, superseded or still required; do not
   blindly apply the old b10216 patch. Apply only mechanisms still absent from
   the pinned source.
3. Rebase conflicts as source patches, then rerun correctness and native
   dispatch proof. A clean `git apply --check` is necessary but not sufficient.
4. Preserve an ordered, hash-manifested E28 series under
   `patches/llama.cpp/e28/current/`. After native success, promote the exact
   tested E27 patch as `patches/llama.cpp/current/0003-...` and add a manifest
   describing the upstream commit and application order. Do not overwrite E25
   or E27 historical artifacts.
5. On current upstream, run matched stock-versus-combined `pp2048`, `tg128`,
   the 30-task quality gate and the direct correctness suites. These are the
   portable release claims; pinned-b10216 results remain comparability evidence.
6. Profile combined current-upstream `pp2048` and `tg128` with symbols and PMU
   counters. Rank the next kernel by measured whole-model ceiling after both
   mechanisms are active.

## Failure rules

- If E25 and E27 conflict, diagnose the source/data-layout interaction and fix
  only that integration. Do not relax correctness, quality or workload gates.
- If E25 fails quality or destroys E27's retained prefill effect, promote E27
  without E25 as the current runtime and retain the complete negative
  composition result.
- If E27 changes output when added to the same decode variant, stop performance
  promotion until the cause is resolved.
- If a current-upstream mechanism is already present, prove that from source
  and omit the duplicate patch; do not claim upstream code as ours.
- Do not begin a new Q4_K/Q6_K optimization in E28. The combined profile chooses
  that next pass.

## Owned outputs

- `experiments/e28_contract.json` and E28 reproducer/ingest tests
- `patches/llama.cpp/e28/` and the verified current-series manifest
- `results/raw/e28-*`, machine-readable summaries and SHA-256 inventories
- `results/reports/e28-cumulative-arm-runtime.md`
- one stock-versus-combined live demo command

Do not edit Devpost copy, submission hardening, broad strategy documents or
unrelated experiment history. Recompute the E27 full-archive SHA-256 if that
archive is locally available; correct its report only when the archive and
manifest agree.

## Autonomous GitHub delivery

The executing agent owns the worktree, branch, commits, pull request and merge.
Do not hand those steps back to the user.

1. Make an initial checkpoint containing this brief and the frozen E28
   contract. Commit only E28-owned files.
2. Invoke the `github:yeet` workflow to push
   `codex/e28-cumulative-arm-runtime` and open a draft PR against `main` with an
   `E28:` title.
3. Make logical checkpoint commits for composition, native evidence,
   current-upstream release and final report. Never commit credentials, model
   files, build trees, `perf.data` or unbounded archives.
4. Before making the PR ready, fetch and merge current `origin/main` without
   rewriting published history. Rerun every affected check after conflicts.
5. Run the pass-specific tests, `python3 -m unittest discover -s tests -q`,
   `python3 scripts/verify_submission.py` and `git diff --check`.
6. Explicitly require all named GitHub workflow runs to pass; an empty
   `gh pr checks` result is not a pass.
7. Mark the PR ready, merge it with a merge commit using `gh`, then verify the
   PR is `MERGED` and `origin/main` contains the merge commit. Do not ask the
   user to click Merge.

## Resources and finish

Paid resources have a hard USD 12 ceiling for E28. Every instance must have a
six-hour-or-shorter automatic deletion rule. Explicitly delete instances and
disks, then preserve an empty exact-name inventory before completion.

Finish only after one combined current-upstream runtime is runnable from a
clean checkout, native correctness and quality have passed, cumulative numbers
come from matched samples, the next hot path is measured, resources are absent
and the E28 PR is merged.
