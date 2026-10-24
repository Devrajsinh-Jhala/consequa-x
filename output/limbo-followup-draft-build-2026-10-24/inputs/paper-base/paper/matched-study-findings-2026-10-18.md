# Closed matched local-model study

The frozen 18 October 2026 collection finished normally at 17:30 IST, before
its 18:32 IST new-dispatch cutoff. All 504 slots started: 503 completed and one
retained a strict-JSON policy failure, with no interrupted or unstarted slots.
There were 896 attempted/received local model calls against a 1,512-call cap
and no transport failures. No failed sample was replaced.

## Design and interpretation

Three small local checkpoints (Qwen3 4B, Llama 3.2 3B and Gemma 3 1B), two
unchanged prompt profiles, two new wording families, seven exposed mechanisms
and six repetitions give 504 planned episodes. These are fourteen fixed
case/wording cells, not 504 independently sampled tasks. Model size, family and
quantization are confounded. The earlier held-out reserve remains unused.
The [frozen protocol](protocol-matched-local-2026-10-18.md) and source revision
`bcd733d8f8c5712e4413afe030b6a20bf7080de1` precede study generation.
This is an internally timestamped protocol, not an external preregistration.

Five offline factual auditors use the same completed episodes without new
model calls. Their information budgets differ: last response, final structured
assessment, readback without provenance, independent contract/provenance
reference, and Consequa-X. Simulator-ledger gold is computed separately.
The same-information reference is a correctness control, not a state-of-the-art
causal-method reproduction. No verify-before-retry controller, LLM judge or
counterfactual attribution comparison was evaluated.

## Exact aggregate fractions

| Auditor | State claims/503 | State wrong/claims | State correct/504 planned | Linked claims/503 | Linked wrong/claims | Linked correct/504 planned |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Response only | 201/503 | 53/201 | 148/504 | 201/503 | 53/201 | 148/504 |
| Structured self-report | 252/503 | 148/252 | 104/504 | 252/503 | 136/252 | 116/504 |
| Readback without provenance | 431/503 | 0/431 | 431/504 | 0/503 | undefined (0/0) | 0/504 |
| Independent public reference | 431/503 | 0/431 | 431/504 | 385/503 | 0/385 | 385/504 |
| Consequa-X | 431/503 | 0/431 | 431/504 | 385/503 | 0/385 | 385/504 |

Reference and Consequa-X predictions, including abstentions, agree on all
503 state and all 503 action-linked outputs. Their origin outputs make 216
definite, correct claims among 310 origin-assessable episodes, with no wrong
definite claims. Other methods abstain on origin. A zero claim denominator is
undefined, not zero error; abstention is not a correct claim. Full target,
condition, model/profile and repetition fractions are retained in the analysis.

## Execution must remain visible

| Model/profile | Completed/planned | Dispatched/completed | Retry attempts |
| --- | ---: | ---: | ---: |
| Gemma / v1 | 84/84 | 0/84 | 0 |
| Gemma / v2 | 84/84 | 0/84 | 0 |
| Llama / v1 | 84/84 | 84/84 | 0 |
| Llama / v2 | 83/84 | 82/83 | 0 |
| Qwen / v1 | 84/84 | 84/84 | 47 |
| Qwen / v2 | 84/84 | 84/84 | 11 |

Across completed episodes, 334/503 dispatched an agent action, with 392 tool
attempts and 58 retries. Gemma dispatched none of its 168 completed episodes;
external-actor effects can still exist. Correctly observing an empty ledger
does not demonstrate refund execution or handling of a dispatched fault.
Execution and realized-exposure diagnostics were added descriptively after the
first-six no-action audit, without changing generation, primary metrics or
stopping rules. This timing is disclosed rather than called confirmatory.

## Evidence and remaining limits

- [Sealed analysis](../output/matched-local-analysis-2026-10-18/analysis.md),
  [final disposition](../output/matched-local-analysis-2026-10-18/final-disposition.json)
  and [hash-bound receipt](../output/matched-local-analysis-2026-10-18/finalization-receipt.json).
- [Execution diagnostics](../output/matched-local-analysis-2026-10-18/execution/execution-summary.md).
- [Two vector figures and source fractions](../output/matched-local-figures-2026-10-18/README.md).

The one failure is Llama v2 slot 109, missing-provenance desk wording, whose
first response was not strict JSON. It remains in the full planned denominator.
No pooled independent-task confidence interval, significance, model ranking,
novel superiority, causal identification, real-service transfer or independent
human validation follows from these fixed simulator results. The information
ablation comparison supports evidence requirements in this setting; exact
parity with the equally informed reference limits any advantage claim.
