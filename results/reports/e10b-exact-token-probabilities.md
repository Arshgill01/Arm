# E10b exact-token probability primitive

Native Arm run
[`30797568757`](https://github.com/Arshgill01/Arm/actions/runs/30797568757)
passes the frozen E10b parity, response-size, and latency contract. The result
promotes one bounded server primitive for a separately frozen multi-token
evaluator. It does not claim that such an evaluator or an external holdout has
already been completed.

## What changed

Exact llama.cpp b10216 already computes a full pre-sampling softmax when the
completion API returns probabilities. Its existing `n_probs` interface can
return the score of a known continuation token only by serializing a top-N list
large enough to contain that token. The retained source patch adds a bounded
`probability_ids` field. It accepts at most 256 unique in-vocabulary token IDs
and returns their pre-sampling log probabilities in request order as
`selected_logprobs`. It rejects post-sampling mode and disables backend
sampling for this request shape so the raw logits used by the existing path
remain available. It changes neither logits nor the sampled token.

The patch is applied after the exact retained three-patch b10216 E7c series.
The combined diff hash is
`8ab4ea8e4a7412ec24f0fa4ebf49a23745c58cf66b8cfb2e99ac0ca53c69be12`.
The service remains the one-slot, four-thread, 256-context, 64/64-batch,
repacked, OpenSSL-off profile with the selected Ministral 3B Q4_K_M model.

## Frozen experiment

The same four-logical-CPU Neoverse N2 job ran four fresh servers in
full-vocabulary, selected, selected, full-vocabulary order. Each cell used one
warmup and three measured cache-disabled requests. The prompt was the already
exposed E10a `logic-02` shape with a 64-token shared prefix; no new holdout task
was consumed. A, B, C, and D tokenized to IDs 1065–1068. The model vocabulary
contained 131,072 entries. All 12 measured responses were retained as gzip
files with compressed and uncompressed sizes and hashes.

Promotion was frozen before execution: maximum log-probability error `1e-6`,
exact selected-ID order and candidate ranking, identical sampled output, at
least 100,000 observed full-vocabulary entries, at most four selected entries,
selected payload at most 1% of full vocabulary, median selected HTTP latency at
most 1.05x full vocabulary, and zero failures.

## Result

| Metric | Full vocabulary | Four selected IDs | Ratio |
| --- | ---: | ---: | ---: |
| Median HTTP latency | 3,591.65 ms | 2,925.14 ms | 0.8144x |
| p95 HTTP latency | 3,617.81 ms | 2,929.87 ms | 0.8099x |
| Median response | 12,565,398 bytes | 2,778.5 bytes | 0.000221x |
| Median cell throughput | 0.22160 req/s | 0.34169 req/s | 1.5419x |
| Median CPU seconds/request | 12.0883 s | 11.6300 s | 0.9621x |
| Maximum RSS | 4,691,508 KiB | 4,277,688 KiB | 0.9118x |
| Median readiness | 2,682.75 ms | 2,684.36 ms | 1.0006x |

The maximum A/B/C/D log-probability delta was
`3.5762786865234375e-7`, below the frozen `1e-6` tolerance. All six pairs kept
the exact ranking B, D, A, C and identical sampled content/token output. There
were zero request failures. The response shrank 99.9779%, and median HTTP
latency improved 18.56%; both gates pass.

The latency result should be interpreted narrowly. Prompt evaluation timings
were almost unchanged, while returning 131,072 JSON entries imposed substantial
sorting, serialization, memory, compression-retention, and loopback transfer
work. E10b demonstrates removal of that response-path waste. It is not a claim
that the model's matrix computation became 1.54x faster. CPU seconds/request
fell only 3.79%, which is consistent with much of the model work remaining.

## Reproducibility and failures

The first native attempt
[`30797017450`](https://github.com/Arshgill01/Arm/actions/runs/30797017450)
failed before warmup because the probe passed a frozen path string to a loader
requiring `pathlib.Path`. That attempt is retained in its own
[`manifest`](../manifests/e10b-preflight-30797017450.json) and
[`report`](e10b-preflight-failure.md). The repair added a regression test and
changed no workload, source primitive, order, repetition, or gate.

The successful 90-day artifact
`e10b-exact-token-probabilities-30797568757-1` contains the contract, source
diff, patches, source revision, full CMake cache and build commands, compiler,
binary/runtime closure, model hash, commands, host capture, server logs,
process counters, all raw HTTP responses, and the generated summary. Local
independent ingestion reproduced the artifact summary byte for byte at SHA-256
`b4222f2b8284829dc93285be1612134f63ecdcb635f2956422dd22cd44e5c2eb`.
The committed compact
[`manifest`](../manifests/e10b-30797568757.json) records the result and claim
boundary.
