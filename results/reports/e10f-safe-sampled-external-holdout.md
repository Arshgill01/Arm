# E10f safe-sampled external quality holdout

Native Arm run
[`30829237582`](https://github.com/Arshgill01/Arm/actions/runs/30829237582)
completes the preselected 300-sample external holdout for both exact Ministral
quantizations with zero scoring failures. This is the valid successor authorized
by E10e; it does not rewrite E10d's failed result or the original 30-task model
admission contract.

## Quality result

Each task contains the 100 sample indices and metric definitions frozen before
E10d. No task or sample was replaced after observing a result.

| Task metric | Q4_K_M | Q4_0 | Q4_K_M − Q4_0 |
| --- | ---: | ---: | ---: |
| ARC Easy accuracy | 73% | 72% | +1 pp |
| ARC Easy normalized accuracy | 59% | 61% | −2 pp |
| HellaSwag accuracy | 49% | 48% | +1 pp |
| HellaSwag normalized accuracy | 72% | 71% | +1 pp |
| WinoGrande accuracy | 57% | 60% | −3 pp |

The two models agree on 90.67% of raw predictions and 91.00% of normalized
predictions. The result is mixed rather than a universal Q4_K_M quality win:
Q4_K_M is one point higher on both raw four-choice tasks and HellaSwag's
normalized metric, while Q4_0 is two points higher on normalized ARC Easy and
three points higher on WinoGrande.

## Mechanism and execution

Each model scores 300 samples, 1,000 candidate continuations, and 14,374 exact
target-token requests through the safe-sampled serial adapter. Both preflights
repeat with zero token or summed-log-probability delta. All 28,748 raw server
responses are retained once, every request succeeds, tokenizer parity holds,
and both cells use the same prepared workload and exact E7c runtime plus E10b
response primitive.

Q4_K_M completes at 0.05032 samples/s versus 0.07100 for Q4_0; process CPU per
token-score request is 1.64123 versus 1.15924 seconds. Maximum process RSS is
7,274,436 versus 7,027,100 KiB, and readiness is 2,430.63 versus 1,820.87 ms.
These are descriptive evaluator costs, not serving-performance gates or a
causal quantization comparison: the contract intentionally applies no minimum
quality threshold and makes no service, energy, PMU, cost, or fleet claim.

## Decision

E10f is admitted as supplemental external robustness evidence. It satisfies
the holdout prerequisite for generated quantization evaluation, but it does not
by itself authorize that frontier: the separately frozen E12a importance matrix
must first complete and be independently retained as valid. The selected Q4_K_M
service remains selected by the original 30-task admission contract.

## Reproducibility

Independent local ingestion reproduces the primary, control, and aggregate
workflow summaries byte for byte at SHA-256 `38801ef1…96af7`,
`6dc7fe47…bb11`, and `c2fd1aef…fad6`. Each cell contains 14,452 inventoried
files; all hashes and the six materialized runtime aliases were revalidated.
The primary and control raw inventories contain 14,374 compressed responses
each. Artifacts `e10f-ministral3_3b_q4_k_m-30829237582-1` (ID `8865212492`,
digest `b055d6b5…98d`), `e10f-ministral3_3b_q4_0-30829237582-1` (ID
`8864346709`, digest `1f77a3ec…d2a6`), and the aggregate (ID `8865220202`,
digest `d3fb6162…b1d`) bind the raw responses, exact binary/dependency closure,
model and dataset provenance, commands, environment, samples, and summaries.
The retained [`manifest`](../manifests/e10f-30829237582.json) has SHA-256
`d328ede5…8dd7`.
