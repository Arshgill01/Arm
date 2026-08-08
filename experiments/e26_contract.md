# E26 Arm tiled-FFN fusion pass

Status: frozen before implementation on 2026-08-08.

Implementation note: the initial 64-row gate/up-only candidate failed the
native layer gate, so contract revision 2 follows the mandated fallback in pass
step 5: 1024-row gate/up/SwiGLU tiles are quantized and accumulated directly
through the Q4_K or Q6_K down projection. The retained first result remains a
negative result rather than being rewritten as pack reuse.

## Launch contract

- Run in an isolated worktree from current `origin/main`.
- Require merge commit `1c830dbf6eeb6e9261cbe2613a22ea89b733ea22`
  to be an ancestor of `origin/main`.
- Use branch `codex/e26-tiled-ffn-fusion`; never reuse the E24 feature branch.

## Objective

Make one complete Q4_K FFN materially faster by executing gate, up, activation
and multiplication as a tiled Arm CPU dataflow instead of materializing full
intermediate tensors. The intended user-visible result is lower latency for the
same request on the same four Arm cores. This is graph and kernel fusion, not
activation-pack reuse.

## Starting facts

- Start from `origin/main`, which contains E23/E24 through merged PR #1
  (`1c830db` at contract freeze).
- FFN gate/up projections accounted for 31.43% of `pp512` cycles and 30.74% of
  `tg128` in the retained source profile.
- E20c paired 52 gate/up nodes and reused q8_K activation packing. It produced
  only `1.002614x` service throughput. That exact mechanism is closed.
- E23 and E24 are the required cumulative kernel baseline and must remain
  enabled and unchanged.

## Pass

1. Bind the exact FFN graph roles and dominant Ministral shapes. Measure full
   intermediate bytes, node time and thread scheduling on native Arm.
2. Build a one-layer harness containing gate, up, SiLU/multiply and the down
   projection boundary. Validate it against the unfused graph.
3. Implement a default-off fused CPU operation that computes gate/up tiles and
   applies the post-op before full intermediates are written.
4. Use the existing E23/E24 matrix kernels as black boxes initially. Do not tune
   the Q4_K or Q6_K inner kernels owned by E25/E24.
5. If gate/up-only tiling cannot clear the layer gate, extend the same dataflow
   to accumulate the down projection from tiles. Do not fall back to E20c pack
   reuse and rename it fusion.
6. Prove the real model graph selects only the intended FFN roles and retains a
   safe fallback for every unsupported shape.
7. Run numerical/reference checks before matched layer and whole-model timing.
   Characterize floating-order error and deterministic model behavior.
8. Measure `pp128`, `pp512` and `tg128`; report saved materialization bytes and
   the end-to-end result as one mechanism.
9. After a material result, test an adjacent model and a second Arm CPU.
10. Produce a current-upstream patch and a real-request baseline/candidate demo.

## Gates

- Cheap gate: at least `1.15x` for the complete one-layer FFN before broad graph
  integration.
- Promotion gate: at least `1.08x` in one controlling whole-model phase with
  the other phases non-regressing; `1.10x` or more is the pass target.
- Hold model bytes, core count, affinity, cache policy and output-quality policy
  fixed.
- Do not attribute results to removed matrix computation unless it was actually
  eliminated.
- A graph-only implementation without native execution proof is a failure.

## Ownership boundaries

- Use the `e26` prefix for experiments, workflows, raw results and reports.
- Do not depend on E25 or E27 or cherry-pick them while this pass runs.
- Do not edit `repack.cpp` inner kernels except for a narrow fusion dispatch
  hook. E25 owns Q4_K kernel/layout exploration.
- Do not edit shared README, submission, strategy, index or progress files.
- Store patch artifacts under `patches/llama.cpp/e26/`.

## Delivery and validation

- Preserve logical commits for the contract, profiling, implementation and
  final result.
- Keep the GitHub PR draft until E25 is merged, then merge current
  `origin/main`, rerun affected validation, mark the PR ready and merge it with
  a merge commit.
- Required terminal validation is pass-specific native Arm validation,
  `python3 -m unittest discover -s tests -q`,
  `python3 scripts/verify_submission.py`, and `git diff --check`.
- Check named workflow runs explicitly; an empty `gh pr checks` is not a pass.
- Remove or disable rejected production code while retaining the negative
  report and harness.

## Resources and finish

Paid resources have a hard USD 12 ceiling. Every instance must have a six-hour
or shorter automatic deletion rule and must be explicitly deleted with instance
and disk absence verified at the end.

Finish with the fused operation, reference harness, native execution proof, raw
matched results, bounded report, current-upstream patch and live-request demo.
Completion includes a verified GitHub merge.
