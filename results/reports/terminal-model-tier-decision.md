# Terminal model-tier decision: keep Q4_K_M

The recovered E11b and E12b frontiers now resolve the model lane. Pareto64 keeps
Ministral 3B Q4_K_M as its only promoted model tier and closes further stock or
generated-quant sweeps.

## Native service evidence

E11b retains 40 native Arm64 fresh-process cells and 1,200 measured requests.
Q4_K_M is the fastest point, scores 23/30 in every repetition, preserves every
anchor answer and has zero failures.

| Candidate | Score | Answer mismatches | Throughput ratio | CPU ratio | RSS ratio | Readiness ratio | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Q3_K_S | 15/30 | 14 | 0.2875x | 3.5000x | 0.4953x | 0.5189x | close |
| Q3_K_M | 17/30 | 6 | 0.3943x | 2.5491x | 0.6720x | 0.6805x | close |
| IQ4_XS | 22/30 | 1 | 0.5561x | 1.8044x | 0.5780x | 0.4910x | close |
| IQ4_NL | 23/30 | 1 | 0.9821x | 1.0180x | 0.9582x | 0.8012x | close |
| Q5_K_M | 22/30 | 1 | 0.7923x | 1.2573x | 1.1428x | 1.0197x | close |

IQ4_NL is the only close tradeoff and its positive evidence is preserved: it is
4.4% smaller, uses 4.2% less maximum RSS and reaches readiness 19.9% sooner.
It also changes one answer and regresses throughput, median/p95 latency and CPU
per request. Those modest benefits do not create a distinct portfolio role:
the already validated Q4_K_M no-repack profile preserves the selected model for
the memory lane, while the exact identity-bound sidecar reduces same-job Q4_K_M
readiness to 0.3797x without a throughput regression.

This is a portfolio decision, not a new post-result benchmark gate. The complete
non-dominated E11b frontier remains available for inspection.

## Generated-quant evidence

E12b's nine generated recipes remain a mixed quality/size map. The most
interesting unconfirmed points are the smaller no-imatrix IQ4_XS control and
the edge-layer-Q6 Q4_K_S recipe, but neither has matched 30-task native service
evidence. The former also belongs to a quantization family whose retained stock
service point reaches only 0.5561x Q4_K_M throughput; that is context, not a
causal claim about the generated file. The latter is larger than Q4_K_M and
trades one external quality coordinate down for two up.

No generated recipe is promoted or regenerated. Their negative and mixed
results remain preserved, and the original admission contract is unchanged.

## Decision

The machine-readable
[terminal manifest](../manifests/model-tier-terminal-decision.json) derives the
selection from the exact retained E11b, E12b, E6i and E16b manifests. It records
an empty follow-up candidate set and authorizes no new native model experiment.

This decision makes no energy, PMU, local-device, cost, fleet, other-runtime or
general model claim.
