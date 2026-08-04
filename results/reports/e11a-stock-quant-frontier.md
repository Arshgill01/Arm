# E11a terminal stock-quant quality/size frontier

Native source run
[`30847559089`](https://github.com/Arshgill01/Arm/actions/runs/30847559089)
completed the exact pinned 300-sample holdout for all eight new stock
quantizations. Two cells completed scoring but failed the unchanged 8 GiB RSS
gate, so the source workflow correctly did not aggregate. Inspection-only
recovery run
[`30868725586`](https://github.com/Arshgill01/Arm/actions/runs/30868725586)
then accounted for the terminal set without repeating model inference.

## Result

Six new cells are deployable under the frozen resource contract; Q6_K and Q8_0
remain scored but resource-infeasible. Together with the retained Q4_K_M anchor,
the deployable points are:

| Model | Size | ARC-E norm | HellaSwag norm | Winogrande | Peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Q3_K_S | 1.639 GB | 0.52 | 0.68 | 0.59 | 4,911 MiB |
| Q3_K_M | 1.796 GB | 0.57 | 0.69 | **0.62** | 5,679 MiB |
| IQ4_XS | 1.959 GB | 0.58 | **0.73** | 0.59 | 5,270 MiB |
| IQ4_NL | 2.051 GB | 0.56 | 0.72 | 0.60 | 6,922 MiB |
| Q4_K_S | 2.053 GB | 0.58 | 0.70 | 0.58 | 6,926 MiB |
| Q4_K_M anchor | 2.146 GB | **0.59** | 0.72 | 0.57 | 7,104 MiB |
| Q5_K_M | 2.474 GB | 0.58 | **0.74** | 0.60 | 7,725 MiB |

Q4_K_S is dominated on the frozen quality/size coordinates and stops here.
The mechanical non-dominated shortlist is Q3_K_S, Q3_K_M, IQ4_XS, IQ4_NL,
Q4_K_M, and Q5_K_M. The five alternatives to the anchor advance unchanged to
the matched E11b service frontier; quality alone cannot promote a new default.

Q6_K scored 0.57/0.72/0.58 but reached 8,585,348 KiB RSS, exceeding the gate by
196,740 KiB. Q8_0 scored 0.54/0.73/0.59 but reached 10,003,620 KiB, exceeding
it by 1,615,012 KiB. Neither point enters the deployable frontier and the gate
was not raised after observation.

## Evidence boundary

The [retained manifest](../manifests/e11a-actual-recovery-30868725586.json)
is byte-identical to an independent local replay from all six valid cell
summaries, both retained resource failures, the E10f anchor, and live source
artifact metadata. It binds compact recovery artifact ID `8877077273`, digest
`sha256:4888d442dabfe3abde05be13752fadca3f06a61dd848b8981fa01c17979b0d83`,
and its complete 11-file inventory. This is an exploratory quality/size
frontier, not a service-performance, product-promotion, energy, PMU, device,
fleet, or cost claim.
