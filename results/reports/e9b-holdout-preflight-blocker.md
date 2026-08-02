# E9b external-holdout API blocker

Native run
[`30766707967`](https://github.com/Arshgill01/Arm/actions/runs/30766707967)
preserved a negative E9b preflight before any external benchmark result was
observed. The exact patched b10216 E7c server built on a two-logical-CPU
Neoverse N2 runner, matched the selected Q4_K_M model, launched with the frozen
service arguments, and retained the 13-name OpenSSL-free dependency closure.

The corrected Transformers 5.14.1 tokenizer loaded from the exact Mistral
revision passed every predefined comparison with llama.cpp `/tokenize` and
saved/reloaded before the script reached the completion check. The synthetic
12-token request itself completed. The preflight then failed because the exact
`/v1/completions` response did not contain the echoed prompt-token logprob shape
that lm-evaluation-harness v0.4.12 uses to slice continuation likelihood at the
context boundary.

This is a server API boundary, not a task or score failure. In pinned b10216,
`oaicompat_completion_params_parse` explicitly rejects `echo=true`. The harness
requires echo and reads `choices[].logprobs.token_logprobs[ctxlen:-1]` for
multiple-choice tasks. Patching that behavior, proxying a different response,
or changing runtimes would no longer evaluate the exact E7c server required by
the frozen plan.

Therefore the full ARC Easy, HellaSwag, and WinoGrande job did not start; no
external task score or sample was observed, and Q4_0 was not run. The selected
tasks, licenses, revisions, and 300-index map remain retained rather than being
replaced after the failure. The original 30-task admission contract is
unchanged.

The 90-day artifact `e9b-preflight-30766707967-1` preserves the plan, exact
sample map, host capture, dependency freeze, source diff, CMake cache, build
commands and logs, runtime closure, server binary set, launch arguments, model
hash, server properties, and server log. The compact
[`manifest`](../manifests/e9b-preflight-30766707967.json) records their hashes.
Per the frozen fallback order, work proceeds to the native prompt-cache
generalization experiment.
