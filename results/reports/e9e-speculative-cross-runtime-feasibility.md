# E9e — speculative decoding / cross-runtime feasibility

## Decision

No measured experiment was launched. The required license and provenance gate
passed, but the exact-runtime mechanism, exact-model comparability, and
quality-workload gates did not. Launching a benchmark after those failures
would create a number without a defensible end-to-end comparison.

The machine-readable stop record is
[`e9e-feasibility.json`](../manifests/e9e-feasibility.json). This is a bounded
feasibility result, not native performance evidence.

## Exact service held fixed

- llama.cpp `b10216`, commit `876a4321163249c43ca4e986818fab5ab081f282`,
  plus retained patch-series hash `e11cdd41…a9893`;
- `Ministral-3-3B-Instruct-2512-Q4_K_M.gguf`, 2,146,497,824 bytes,
  SHA-256 `fd46fc37…397f4`, from pinned producer revision `7564922f…7a6a`;
- the unchanged 30-task admission contract: 23/30, maximum eight output tokens;
  and
- E9a's 240 retained final-comparison responses, all of which generated exactly
  two tokens.

No model was downloaded and no Arm runner was consumed for E9e. A storage
preflight found 20 GiB free; the two inspected source trees used about 223 MiB.

## Speculative-decoding lane

The exact b10216 source documents draft-model and model-free n-gram mechanisms
in its [speculative-decoding guide](https://github.com/ggml-org/llama.cpp/blob/876a4321163249c43ca4e986818fab5ab081f282/docs/speculative.md).
The inspected documentation did not identify an official Ministral 3 3B
EAGLE/MTP/draft artifact, and the 3B model is already the smallest tier in the
[official Ministral 3 GGUF family](https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF).
That fails the compatible-draft gate without claiming that no third-party draft
could ever exist.

More decisively, the exact runtime's draft initializer stores and logs
`params.speculative.draft.mparams.path`, but its load call uses the target
`params.model.path` instead. The relevant
[b10216 source lines](https://github.com/ggml-org/llama.cpp/blob/876a4321163249c43ca4e986818fab5ab081f282/common/speculative.cpp#L2331-L2338)
are outside all three retained patches. A draft-model experiment on this exact
source therefore fails its mechanism gate before measurement.

The n-gram path avoids a second model, but it is not meaningful for the frozen
workload: all 240 E9a completions stop after exactly two generated tokens. The
mechanism is intended to draft and verify repeated multi-token continuations.
Introducing a long-form workload now would replace or extend the frozen
quality contract, and E9b already established that the exact server cannot
support the pinned external holdout's prompt-logprob API. The workload was not
changed to manufacture a benchmark.

## LLM-Runner cross-runtime lane

[Arm LLM-Runner at `8ba39e40`](https://github.com/Arm-Examples/LLM-Runner/tree/8ba39e40fa754b87deb99a998c31de3b850094d5)
offers one selected backend behind a common API. Its nine checked-in model
configurations cover Llama 3.2 1B, Phi-2/Phi-4, Qwen2-VL 2B, Qwen2.5 3B, and
Qwen3.5 2B; none covers Ministral. Its pinned backends are llama.cpp `b7870`,
ONNX Runtime `v1.24.2` plus GenAI `v0.12.0`, MNN `3.6.0`, and ExecuTorch
`v1.2.0`.

The official [Ministral ONNX repository](https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-ONNX)
is public and Apache-2.0, but its FP16/Q4 exports are not the selected GGUF
Q4_K_M byte stream or quantization. Comparing it with the selected service
would compound runtime, format, and quantization changes without proven output
equivalence. Conversely, overriding LLM-Runner's llama backend to b10216 would
exercise the same llama.cpp runtime through a wrapper, not an independent
cross-runtime mechanism.

License review passed: the selected model and official model repositories are
Apache-2.0; LLM-Runner retains Apache-2.0 and BSD-3-Clause license texts; and
llama.cpp is MIT. License compatibility alone is insufficient to override the
failed mechanism and equivalence gates.

## Claim boundary

E9e adds no speed, latency, energy, PMU, cost, model-equivalence, or runtime
portability claim. It preserves a reproducible reason to stop. A future study
must first bind a corrected runtime mechanism or independent backend, an exact
or separately quality-qualified artifact, and a predeclared workload with a
meaningful multi-token verification window.
